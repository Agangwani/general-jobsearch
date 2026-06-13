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

def discover_companies(root: Path, limit: int = 0, dry_run: bool = False) -> int:
    from .http import make_session
    from .resume import extract_keywords, load_resume_text
    from .sources import SOURCES, SourceSkip

    settings = load_settings(root / "config" / "settings.yaml")
    discovery = settings.get("discovery", {}) or {}
    companies, manual = load_companies(root / "config" / "companies.yaml")

    resume_text, is_sample = load_resume_text(root, settings)
    if is_sample:
        print("NOTE: no resume at data/resume.txt — discovering companies for "
              "the bundled sample resume. Upload yours first for a registry "
              "tailored to you.", file=sys.stderr)

    query = settings.get("search", {}).get("query", "software engineer")
    categories = discovery.get("categories") or infer_categories(
        extract_keywords(resume_text), query)
    ctx = {
        "query": query,
        "location": discovery.get("location", "New York, NY"),
        "location_subs": [loc.lower() for loc in
                          settings.get("search", {}).get("locations") or DEFAULT_LOCATIONS],
        "categories": categories,
        "max_pages": int(discovery.get("max_pages", 8)),
    }
    print(f"Mining boards for companies hiring '{query}' near {ctx['location']} "
          f"(categories: {', '.join(categories)})")

    timeout = settings.get("fetch", {}).get("timeout_seconds", 30)
    session = make_session(timeout)
    leads: list[CompanyLead] = []
    for name in discovery.get("sources") or list(SOURCES):
        fetch = SOURCES.get(name)
        if not fetch:
            print(f"  {name}: unknown source (available: {', '.join(SOURCES)})")
            continue
        try:
            batch = fetch(session, ctx)
            print(f"  {name}: {len(batch)} location-matching postings")
            leads.extend(batch)
        except SourceSkip as exc:
            print(f"  {name}: skipped — {exc}")
        except Exception as exc:  # noqa: BLE001 — one dead source must not sink the run
            print(f"  {name}: ERROR {type(exc).__name__}: {exc}")

    merged = merge_leads(leads)
    known = {normalize_company_name(c.name) for c in companies}
    known |= {normalize_company_name(str(entry.get("name", ""))) for entry in manual}
    exclude = {normalize_company_name(x)
               for x in discovery.get("exclude_companies") or []}
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
        return 0
    out_path = root / discovery.get("output_file", "data/companies.discovered.yaml")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(f"\nWrote {out_path} — {len(resolved)} boards, "
          f"{len(unresolved)} manual-check entries.")
    print("Next: python -m jobsearch verify   (catch wrong/dead boards)")
    print("      python -m jobsearch run      (they're merged into the daily run)")
    return 0
