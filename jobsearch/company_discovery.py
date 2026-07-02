"""Dynamic company discovery: `python -m jobsearch discover-companies`.

config/companies.yaml was hand-built around one resume; a designer or data
scientist needs a different set of employers. This module builds that set
automatically:

1. **Mine generalized boards** (jobsearch/sources/) — The Muse, the HN
   "Who is hiring?" thread, Adzuna — for postings in the configured location,
   and reduce them to CompanyLead records (name + role/URL evidence).
2. **Merge + dedupe** leads across sources by normalized company name, and
   drop companies already in the registry or on `discovery.exclude_companies`
   (your current employer, …).
3. **Rank against the resume** — lead evidence (titles, description
   snippets) is embedded in a TF-IDF space with the resume; relevance =
   cosine similarity with a small multi-mention bonus. The same resume that
   ranks postings decides which companies are worth tracking.
4. **Resolve each top lead to its own ATS board** with discover.py: classify
   any ATS URLs the lead already carries (HN comments link boards directly),
   else probe name-derived slugs against the public Greenhouse/Lever/Ashby/
   SmartRecruiters APIs.
5. **Write the generated registry** (data/companies.discovered.yaml,
   gitignored — it's derived from your resume). config.load_registry merges
   it under the curated companies.yaml at load time; curated entries win,
   so pinning/fixing an entry = move it into companies.yaml.

Probe-resolved slugs can collide on common names (a "Mercury" lead could
match a different Mercury's board); entries record how they were resolved in
`discovered_via` so `(probe)` ones are auditable, and `python -m jobsearch
verify` plus the report's per-company funnel make wrong boards visible.

Everything except `resolve` and the source fetches is pure and offline-tested.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import load_companies, load_settings
from .discover import probe_slugs, survey_urls
from .filters import DEFAULT_LOCATIONS
from .models import CompanyLead
from .utils import normalize_company_name

# How many of each evidence kind a merged lead keeps (across all sources).
_EVIDENCE_CAPS = {"sources": 6, "titles": 20, "locations": 10, "urls": 12, "snippets": 8}

MENTION_BONUS = 0.08  # relevance multiplier step per doubling of mentions


def merge_leads(leads: list[CompanyLead]) -> list[CompanyLead]:
    """Collapse per-posting leads into one per company (normalized name),
    summing mentions and unioning evidence. First-seen spelling wins."""
    from .startups import merge_meta

    merged: dict[str, CompanyLead] = {}
    for lead in leads:
        key = normalize_company_name(lead.name)
        if not key:
            continue
        target = merged.setdefault(key, CompanyLead(name=lead.name, sources=[], mentions=0))
        target.mentions += lead.mentions
        for attr, cap in _EVIDENCE_CAPS.items():
            values = getattr(target, attr)
            seen = set(values)
            for value in getattr(lead, attr):
                if value and value not in seen and len(values) < cap:
                    values.append(value)
                    seen.add(value)
        if lead.meta:
            target.meta = merge_meta(target.meta, lead.meta)
    return list(merged.values())


def filter_known(
    leads: list[CompanyLead], known: set[str], exclude: set[str]
) -> list[CompanyLead]:
    """Drop leads already in the registry (curated or manual_check) and the
    never-add list. `known`/`exclude` hold normalized names."""
    return [
        lead for lead in leads
        if normalize_company_name(lead.name) not in known
        and normalize_company_name(lead.name) not in exclude
    ]


def filter_oversized(
    leads: list[CompanyLead], max_employees: int
) -> tuple[list[CompanyLead], list[CompanyLead]]:
    """Split leads into (kept, dropped) by a headcount ceiling. A lead is dropped
    only when its metadata carries a *known* team size above `max_employees` —
    unknown-size leads (e.g. themuse, which exposes no size) are always kept and
    left to the name blocklist. `max_employees <= 0` disables the guard."""
    from .startups import parse_employee_count

    if max_employees <= 0:
        return list(leads), []
    kept, dropped = [], []
    for lead in leads:
        count = parse_employee_count((lead.meta or {}).get("employees"))
        (dropped if count is not None and count > max_employees else kept).append(lead)
    return kept, dropped


def filter_funding(
    leads: list[CompanyLead], max_raised: float
) -> tuple[list[CompanyLead], list[CompanyLead]]:
    """Split leads into (kept, dropped) by a total-raised ceiling (USD). A lead is
    dropped only when it carries a *known* funding figure above `max_raised` —
    leads with no funding data are always kept (mirroring filter_oversized's
    unknown-is-kept contract). Falls back to the most-recent-round amount when
    total_raised is blank, since the free text sources mine `last_round_amount`
    far more often than a cumulative `total_raised`. `max_raised <= 0` disables."""
    from .startups import parse_money

    if max_raised <= 0:
        return list(leads), []
    kept, dropped = [], []
    for lead in leads:
        meta = lead.meta or {}
        # Fall back to last_round_amount when total_raised doesn't yield a number
        # — not merely when it's empty. A truthy-but-unparseable total_raised
        # ("Undisclosed", "N/A", "Series A") must not mask a real round figure.
        amount = parse_money(meta.get("total_raised"))
        if amount is None:
            amount = parse_money(meta.get("last_round_amount"))
        (dropped if amount is not None and amount > max_raised else kept).append(lead)
    return kept, dropped


def _own_name_re(name: str) -> re.Pattern | None:
    """The lead's own name must not score as evidence (same defense as
    scoring._company_name_re for postings)."""
    tokens = [re.escape(t) for t in re.findall(r"[A-Za-z0-9]+", name) if len(t) >= 3]
    return re.compile(r"\b(" + "|".join(tokens) + r")\b", re.I) if tokens else None


def rank_leads(leads: list[CompanyLead], resume_text: str) -> list[CompanyLead]:
    """Assign relevance (0–100, best lead = 100) in place and sort. Relevance
    = TF-IDF cosine(resume, lead evidence) × a small bonus for companies seen
    posting many matching roles. Falls back to mention counts when evidence is
    too thin to vectorize (degenerate but possible)."""
    import numpy as np
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
    from sklearn.preprocessing import normalize

    from .scoring import EXTRA_STOP_WORDS

    if not leads:
        return leads
    docs = []
    for lead in leads:
        text = "\n".join(lead.titles + lead.snippets)
        name_re = _own_name_re(lead.name)
        docs.append(name_re.sub(" ", text) if name_re else text)

    try:
        vectorizer = TfidfVectorizer(
            stop_words=list(ENGLISH_STOP_WORDS | EXTRA_STOP_WORDS),
            ngram_range=(1, 2),
            max_features=20000,
            sublinear_tf=True,
        )
        X = normalize(vectorizer.fit_transform(docs))
        resume_vec = normalize(vectorizer.transform([resume_text]))
        cosine = np.asarray(X @ resume_vec.T.toarray().ravel()).ravel()
    except ValueError:  # empty vocabulary — every lead was evidence-free
        cosine = np.zeros(len(leads))

    raw = [
        float(c) * (1.0 + MENTION_BONUS * np.log2(1 + lead.mentions))
        for c, lead in zip(cosine, leads)
    ]
    if not any(raw):  # no textual signal at all: most-mentioned first
        raw = [float(lead.mentions) for lead in leads]
    top = max(raw)
    scale = 100.0 / top if top > 0 else 0.0
    for lead, score in zip(leads, raw):
        lead.relevance = round(score * scale, 1)
    leads.sort(key=lambda lead: (-lead.relevance, -lead.mentions, lead.name))
    return leads


# --------------------------------------------------------------- categories ---
# The Muse requires its own category names; infer them from what the resume
# (and the configured search query) is actually about. `discovery.categories`
# in settings.yaml overrides the inference entirely.
_MUSE_CATEGORY_HINTS: dict[str, frozenset] = {
    "Software Engineering": frozenset({
        "software", "engineer", "engineering", "backend", "frontend", "developer",
        "fullstack", "stack", "api", "apis", "microservices", "distributed",
        "infrastructure", "cloud", "kubernetes", "devops", "java", "python",
        "golang", "typescript", "systems",
    }),
    "Data Science": frozenset({
        "machine", "learning", "ml", "ai", "scientist", "pytorch", "tensorflow",
        "nlp", "llm", "llms", "models", "modeling", "statistics",
    }),
    "Data and Analytics": frozenset({
        "analytics", "analyst", "sql", "tableau", "etl", "warehouse", "dbt",
        "looker", "bi", "dashboards",
    }),
    "Design and UX": frozenset({
        "designer", "ux", "ui", "figma", "prototyping", "wireframes", "usability",
    }),
    "Product Management": frozenset({
        "product", "roadmap", "stakeholder", "stakeholders", "prioritization",
    }),
    "Sales": frozenset({"sales", "quota", "crm", "prospecting", "deals"}),
    "Marketing": frozenset({"marketing", "seo", "sem", "campaigns", "brand"}),
    "Finance": frozenset({"finance", "financial", "accounting", "audit", "fp&a"}),
    "HR": frozenset({"recruiting", "recruiter", "talent", "hr", "onboarding"}),
}
_QUERY_WEIGHT = 3  # the query is explicit intent; resume keywords are inferred


def infer_categories(keywords: list[str], query: str, max_categories: int = 2) -> list[str]:
    """Muse category names ranked by hint-term hits across the resume's
    extracted keywords (+ the search query, weighted). A second category is
    only included when it scores at least half the best one — 'product' in a
    SWE resume must not drag in all of Product Management."""
    terms: Counter[str] = Counter()
    for keyword in keywords:
        for word in keyword.lower().split():
            terms[word] += 1
    for word in re.findall(r"[a-z0-9&+]+", (query or "").lower()):
        terms[word] += _QUERY_WEIGHT

    scores = {
        category: sum(terms[hint] for hint in hints)
        for category, hints in _MUSE_CATEGORY_HINTS.items()
    }
    ranked = sorted(
        ((score, category) for category, score in scores.items() if score > 0),
        key=lambda pair: (-pair[0], pair[1]),
    )
    if not ranked:
        return ["Software Engineering"]
    best = ranked[0][0]
    picked = [category for score, category in ranked[:max_categories]
              if score >= max(2, best / 2)]
    return picked or [ranked[0][1]]


# --------------------------------------------------------------- resolution ---
_HOSTED_BOARD = {
    "greenhouse": "https://job-boards.greenhouse.io/{board}",
    "lever": "https://jobs.lever.co/{org}",
    "ashby": "https://jobs.ashbyhq.com/{org}",
    "smartrecruiters": "https://careers.smartrecruiters.com/{org}",
}


def hosted_board_url(detection: dict) -> str:
    """The human-facing board URL for a detection — becomes careers_url."""
    template = _HOSTED_BOARD.get(detection.get("ats", ""))
    if template:
        return template.format(**detection)
    if detection.get("ats") == "workday":
        return f"https://{detection['host']}/{detection['site']}"
    if detection.get("ats") == "eightfold":
        return f"{detection['base_url']}/careers"
    return ""


def resolve_lead(lead: CompanyLead, session) -> tuple[dict | None, str]:
    """(detection, how) — 'url' when an ATS link in the lead's own evidence
    gives it away (trustworthy: the company posted it), 'probe' when a
    name-derived slug answered on a public ATS API (audit these)."""
    detections = survey_urls(lead.urls)
    if detections:
        return detections[0], "url"
    detections = probe_slugs(lead.name, session)
    if detections:
        return max(detections, key=lambda d: d.get("_postings", 0)), "probe"
    return None, ""


# ------------------------------------------------------------------ output ---

def emit_registry(
    resolved: list[tuple[CompanyLead, dict, str]],
    unresolved: list[CompanyLead],
    now: datetime | None = None,
) -> str:
    """The generated registry file: same shape as companies.yaml (so
    load_companies reads it unchanged) plus a `discovered_via` audit field
    per entry. Unresolved leads land in manual_check so the report keeps
    surfacing them instead of silently dropping them."""
    now = now or datetime.now(timezone.utc)
    header = (
        f"# GENERATED by `python -m jobsearch discover-companies` on {now:%Y-%m-%d}.\n"
        "# Companies mined from generalized job boards and ranked against your\n"
        "# resume. Merged on top of config/companies.yaml at load time — the\n"
        "# curated file wins on conflicts, and discovery.exclude_companies is\n"
        "# enforced on every load. Regenerating overwrites this file; to pin or\n"
        "# hand-fix an entry, move it into config/companies.yaml.\n"
        "# Entries resolved by slug probe (discovered_via: \"… (probe)\") can\n"
        "# collide on common company names — spot-check their careers_url.\n\n"
    )
    entries = []
    for lead, detection, how in resolved:
        entry = {"name": lead.name, "tags": ["discovered"], "ats": detection["ats"]}
        entry.update({k: v for k, v in detection.items() if k not in ("ats", "_postings")})
        url = hosted_board_url(detection)
        if url:
            entry["careers_url"] = url
        entry["discovered_via"] = f"{'+'.join(lead.sources)} ({how})"
        entries.append(entry)
    manual = [
        {
            "name": lead.name,
            "careers_url": next(iter(lead.urls), ""),
            "note": (f"no public ATS detected (sources: {'+'.join(lead.sources)}; "
                     f"{lead.mentions} matching posting(s) seen)"),
        }
        for lead in unresolved
    ]
    body = yaml.safe_dump(
        {"companies": entries, "manual_check": manual},
        sort_keys=False, allow_unicode=True, width=100,
    )
    return header + body


# --------------------------------------------------------------- CLI entry ---

def _build_edgar_enricher(discovery: dict, session):
    """A `name -> {"total_raised": …}` callable when startups.enrich.edgar is on,
    else None. Bound to the discovery HTTP session and the configured SEC contact
    User-Agent."""
    enrich = discovery.get("enrich") or {}
    if not enrich.get("edgar"):
        return None
    from .funding_edgar import DEFAULT_SEC_CONTACT_UA, edgar_total_raised

    contact_ua = enrich.get("sec_user_agent") or DEFAULT_SEC_CONTACT_UA
    return lambda name: edgar_total_raised(session, name, contact_ua=contact_ua)


def enrich_meta(lead: CompanyLead, edgar=None) -> dict:
    """The metadata record for one lead: whatever a structured source supplied
    (`lead.meta`, e.g. Y Combinator) folded together with funding/people facts
    mined from its free-text evidence (HN blurbs, descriptions). Always carries
    a name and a source so the UI has something to show. When `edgar` is given
    (a callable name -> {"total_raised": …}) it backfills a real total-raised
    from SEC Form D; merge_meta only fills empty scalars, so it never clobbers a
    figure a structured source or the user already supplied."""
    from .startups import extract_funding, extract_people, merge_meta

    blurb = "\n".join(lead.titles + lead.snippets)
    text_meta: dict = {"name": lead.name, "source": "+".join(lead.sources)}
    text_meta.update(extract_funding(blurb))
    people = extract_people(blurb)
    if people:
        text_meta["notable_people"] = people
    meta = merge_meta(lead.meta, text_meta)
    if edgar is not None and not meta.get("total_raised"):
        try:
            meta = merge_meta(meta, edgar(lead.name) or {})
        except Exception:  # noqa: BLE001 — enrichment must never sink discovery
            pass
    meta.setdefault("name", lead.name)
    if not meta.get("source"):
        meta["source"] = "+".join(lead.sources)
    return meta


def write_meta_sidecar(path: Path, leads: list[CompanyLead], now: datetime | None = None,
                       edgar=None) -> None:
    """Write data/startup_meta.json: normalized company name → metadata, read by
    the tracker ingest to populate the startup_companies table. `edgar` is an
    optional total-raised enricher passed through to enrich_meta."""
    import json

    now = now or datetime.now(timezone.utc)
    companies = {}
    for lead in leads:
        key = normalize_company_name(lead.name)
        if key:
            companies[key] = enrich_meta(lead, edgar=edgar)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"generated": now.isoformat(), "companies": companies}, indent=2) + "\n")


def _registry_company_count(text: str | None) -> int:
    """Number of companies in a generated registry's YAML text (0 for
    missing/empty/malformed — treated as 'nothing to protect')."""
    if not text:
        return 0
    try:
        raw = yaml.safe_load(text) or {}
        return len(raw.get("companies") or [])
    except yaml.YAMLError:
        return 0


def maybe_run_discovery(root: Path, settings: dict, track, now: float | None = None) -> bool:
    """Refresh a track's discovered registry at the start of a run, so each run
    searches for fresh companies rather than only the curated list plus the last
    generated registry. The curated companies.yaml is always searched (the
    exploit watchlist); discovery adds freshly-surfaced companies (explore).

    Controlled per track by ``<track>.on_run`` (default False in code so the
    offline test suite and ad-hoc CLI runs never hit the network unless opted in
    via config/settings.yaml) and throttled by ``<track>.min_interval_minutes``
    (skip if the registry was regenerated within that window — 0 = every run).

    Degradation guard: ``discover_companies`` regenerates the registry from
    scratch and overwrites it whenever it finds >=1 fresh lead, so a partial
    source outage (some aggregators down) would replace a healthy registry with
    a tiny one and — under the mtime throttle — lock that shrunken set in until
    the window elapses. To prevent silent coverage loss, if the refreshed
    registry has fewer than ``min_registry_fraction`` (default 0.5) of the prior
    company count, the prior registry's content AND mtime are restored so the
    next run retries instead of running a degraded search.

    Best-effort: any discovery failure is logged and the run proceeds with the
    existing registry (mirrors the pipeline's per-board graceful degradation).
    Returns True iff a fresh registry was accepted."""
    import os
    import time

    cfg = track.discovery or {}
    if not cfg.get("on_run", False):
        return False
    reg = track.registry_file
    interval = cfg.get("min_interval_minutes", 0) or 0
    if interval > 0 and reg.exists():
        now = time.time() if now is None else now
        age_min = (now - reg.stat().st_mtime) / 60.0
        if age_min < interval:
            print(f"Discovery skipped for {track.name}: registry refreshed "
                  f"{age_min:.0f}m ago (< {interval}m throttle).", file=sys.stderr)
            return False

    prior_text = reg.read_text() if reg.exists() else None
    prior_count = _registry_company_count(prior_text)
    prior_mtime = reg.stat().st_mtime if reg.exists() else None

    print(f"Refreshing {track.name} company registry (discovery on run)...",
          file=sys.stderr)
    try:
        discover_companies(root, track_name=track.name,
                           user_id=getattr(track, "user_id", "local"))
    except Exception as exc:  # noqa: BLE001 - discovery must never abort the run
        print(f"Discovery failed for {track.name} ({exc}); using the existing "
              "registry.", file=sys.stderr)
        return False

    # Reject a degraded refresh: keep the healthier prior registry (content +
    # mtime) so the throttle doesn't lock a shrunken set in and the next run
    # retries. Only guards when there was a prior registry to protect.
    new_count = _registry_company_count(reg.read_text() if reg.exists() else None)
    fraction = cfg.get("min_registry_fraction", 0.5)
    floor = max(1, int(prior_count * fraction))
    if prior_text is not None and prior_count > 0 and new_count < floor:
        reg.write_text(prior_text)
        if prior_mtime is not None:
            os.utime(reg, (prior_mtime, prior_mtime))
        print(f"Discovery for {track.name} yielded {new_count} companies vs "
              f"{prior_count} previously (< {floor}) — likely a transient source "
              "outage; kept the prior registry and will retry next run.",
              file=sys.stderr)
        return False
    return True


def discover_companies(root: Path, limit: int = 0, dry_run: bool = False,
                       track_name: str = "main", user_id: str = "local") -> int:
    from .http import make_session
    from .resume import extract_keywords, load_resume_text
    from .sources import SOURCES, SourceSkip
    from .tracks import build_track

    settings = load_settings(root / "config" / "settings.yaml")
    track = build_track(root, settings, track_name, user_id)
    discovery = track.discovery
    # Dedupe new leads against this track's curated seed (companies.yaml for the
    # main track, the optional config/startups.yaml for the startup track).
    if track.curated_file and track.curated_file.exists():
        companies, manual = load_companies(track.curated_file)
    else:
        companies, manual = [], []

    resume_text, is_sample = load_resume_text(root, settings, user_id)
    if is_sample:
        print("NOTE: no resume at data/resume.txt — discovering companies for "
              "the bundled sample resume. Upload yours first for a registry "
              "tailored to you.", file=sys.stderr)

    # The role profile (resume → occupation) decides what to search for; it
    # supplies both the aggregator query and the Muse categories, so discovery
    # re-targets per resume exactly like the daily run does. infer_categories
    # remains the fallback when role targeting is off or unmatched.
    from .role_profile import resolve_profile
    profile = resolve_profile(root, settings, resume_text)
    if profile:
        query = profile.query
        categories = discovery.get("categories") or profile.categories
        print(f"Role profile [{profile.matched_via}]: {', '.join(profile.occupations)} "
              f"({profile.seniority})", file=sys.stderr)
    else:
        query = settings.get("search", {}).get("query", "software engineer")
        categories = discovery.get("categories") or infer_categories(
            extract_keywords(resume_text), query)
    # ats_boards seed = the curated config list + any boards Common Crawl
    # discovered (data/ats_boards.discovered.yaml, via `discover-ats-boards`),
    # deduped (config wins) and capped so a large crawl doesn't fan out into
    # thousands of board fetches per run.
    from .sources.commoncrawl import DISCOVERED_FILE, load_discovered_boards
    ats_seed = [b for b in (discovery.get("ats_boards") or [])
                if isinstance(b, dict) and b.get("ats") and b.get("token")]
    seen_boards = {(b["ats"], str(b["token"]).lower()) for b in ats_seed}
    for board in load_discovered_boards(root / DISCOVERED_FILE):
        key = (board["ats"], str(board["token"]).lower())
        if key not in seen_boards:
            seen_boards.add(key)
            ats_seed.append(board)
    ats_max = int(discovery.get("ats_boards_max", 150) or 0)
    if ats_max > 0:
        ats_seed = ats_seed[:ats_max]

    ctx = {
        "query": query,
        "location": track.location,
        "location_subs": track.locations or [loc.lower() for loc in DEFAULT_LOCATIONS],
        "categories": categories,
        "max_pages": int(discovery.get("max_pages", 8)),
        "ycombinator": discovery.get("ycombinator", {}) or {},
        "ats_boards": ats_seed,   # curated seed + Common Crawl discovered, capped
    }
    universe = "startup companies" if track.is_startup else "companies"
    default_sources = (["ycombinator", "hn_hiring", "themuse"]
                       if track.is_startup else list(SOURCES))
    print(f"Mining sources for {universe} hiring '{query}' near {ctx['location']} "
          f"(categories: {', '.join(categories)})")

    timeout = settings.get("fetch", {}).get("timeout_seconds", 30)
    session = make_session(timeout)
    leads: list[CompanyLead] = []
    for name in discovery.get("sources") or default_sources:
        fetch = SOURCES.get(name)
        if not fetch:
            print(f"  {name}: unknown source (available: {', '.join(SOURCES)})")
            continue
        try:
            batch = fetch(session, ctx)
            print(f"  {name}: {len(batch)} location-matching leads")
            leads.extend(batch)
        except SourceSkip as exc:
            print(f"  {name}: skipped — {exc}")
        except Exception as exc:  # noqa: BLE001 — one dead source must not sink the run
            print(f"  {name}: ERROR {type(exc).__name__}: {exc}")

    merged = merge_leads(leads)
    if track.is_startup:
        max_employees = int(discovery.get("max_employees", 0) or 0)
        merged, oversized = filter_oversized(merged, max_employees)
        if oversized:
            names = ", ".join(sorted(l.name for l in oversized))
            print(f"Dropped {len(oversized)} companies over {max_employees} "
                  f"employees (not startups): {names}")
        max_raised = float(discovery.get("max_raised", 0) or 0)
        merged, overfunded = filter_funding(merged, max_raised)
        if overfunded:
            names = ", ".join(sorted(l.name for l in overfunded))
            print(f"Dropped {len(overfunded)} companies over ${max_raised:,.0f} "
                  f"raised (too late-stage): {names}")
    known = {normalize_company_name(c.name) for c in companies}
    known |= {normalize_company_name(str(entry.get("name", ""))) for entry in manual}
    exclude = {normalize_company_name(x) for x in track.exclude}
    fresh = filter_known(merged, known, exclude)
    print(f"{len(merged)} distinct companies seen; "
          f"{len(fresh)} not already in the registry")
    if not fresh:
        print("Nothing new to add. Try more max_pages, another source, or an "
              "Adzuna key (ADZUNA_APP_ID/ADZUNA_APP_KEY).")
        return 1

    rank_leads(fresh, resume_text)
    top = fresh[: limit or int(discovery.get("max_companies", 25))]
    print(f"Resolving ATS boards for the top {len(top)} by resume relevance…")
    resolved, unresolved = [], []
    for lead in top:
        detection, how = resolve_lead(lead, session)
        if detection:
            resolved.append((lead, detection, how))
            print(f"  + {lead.name} (relevance {lead.relevance}): "
                  f"{detection['ats']} via {how}")
        else:
            unresolved.append(lead)
            print(f"  ? {lead.name} (relevance {lead.relevance}): "
                  "no public ATS found → manual_check")

    text = emit_registry(resolved, unresolved)
    if dry_run:
        print("\n--- generated registry (dry run, not written) ---\n")
        print(text)
        if track.is_startup:
            print("(startup metadata sidecar would be written to "
                  f"{track.meta_file})")
        return 0
    out_path = track.registry_file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(f"\nWrote {out_path} — {len(resolved)} boards, "
          f"{len(unresolved)} manual-check entries.")
    if track.is_startup and track.meta_file:
        edgar = _build_edgar_enricher(discovery, session)
        if edgar is not None:
            print(f"Enriching {len(top)} startups with SEC Form D total-raised "
                  "(best-effort; most tiny/SAFE/non-US startups won't have a filing)…")
        write_meta_sidecar(track.meta_file, top, edgar=edgar)
        print(f"Wrote {track.meta_file} — metadata for {len(top)} startups.")
        print("Next: python -m jobsearch verify --startups   (catch wrong/dead boards)")
        print("      python -m jobsearch run-startups          (fetch + score them)")
    else:
        print("Next: python -m jobsearch verify   (catch wrong/dead boards)")
        print("      python -m jobsearch run      (they're merged into the daily run)")
    return 0
