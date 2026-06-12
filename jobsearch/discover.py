"""ATS slug auto-discovery: `python -m jobsearch discover <company>`.

Board slugs rot — companies migrate ATS vendors and the daily report's
"needs attention" section fills up (Citadel, Warby Parker, Superhuman,
Plaid…). Hand-researching each slug doesn't scale, so this tool does it:

1. **Slug probe** (no browser): derive candidate slugs from the company name
   and hit the public Greenhouse/Lever/Ashby/SmartRecruiters board APIs
   directly. A 200 with postings is a confirmed board.
2. **Browser XHR survey**: load the company's careers page in headless
   Chromium and capture every request URL its frontend makes; any URL that
   hits a known ATS domain reveals the vendor and the slug — including
   Greenhouse iframe embeds and Workday tenant/site pairs.

Output is a ready-to-paste companies.yaml stanza. Nothing is written to the
config — review, paste, then `python -m jobsearch verify`.

URL classification is pure (`classify_ats_url`) and offline-tested.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# (regex on the full URL) → builder(match) -> detection dict.
# A detection is {"ats": ..., **fetcher params}.
_URL_RULES: list[tuple[re.Pattern, callable]] = [
    # Greenhouse: API, hosted boards (legacy + next-gen), and iframe embeds.
    (re.compile(r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)", re.I),
     lambda m: {"ats": "greenhouse", "board": m.group(1)}),
    (re.compile(r"(?:job-)?boards\.greenhouse\.io/embed/job_board\?*.*for=([\w-]+)", re.I),
     lambda m: {"ats": "greenhouse", "board": m.group(1)}),
    (re.compile(r"(?:job-)?boards\.greenhouse\.io/([\w-]+)", re.I),
     lambda m: None if m.group(1) in ("embed", "v1") else {"ats": "greenhouse", "board": m.group(1)}),
    # Lever: posting API and hosted board.
    (re.compile(r"api\.lever\.co/v\d/postings/([\w-]+)", re.I),
     lambda m: {"ats": "lever", "org": m.group(1)}),
    (re.compile(r"jobs\.lever\.co/([\w-]+)", re.I),
     lambda m: {"ats": "lever", "org": m.group(1)}),
    # Ashby: posting API and hosted board.
    (re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([\w.-]+)", re.I),
     lambda m: {"ats": "ashby", "org": m.group(1)}),
    (re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)", re.I),
     lambda m: None if m.group(1) == "api" else {"ats": "ashby", "org": m.group(1)}),
    # SmartRecruiters.
    (re.compile(r"api\.smartrecruiters\.com/v1/companies/([\w-]+)", re.I),
     lambda m: {"ats": "smartrecruiters", "org": m.group(1)}),
    (re.compile(r"careers\.smartrecruiters\.com/([\w-]+)", re.I),
     lambda m: {"ats": "smartrecruiters", "org": m.group(1)}),
    # Workday: the cxs XHR carries tenant + site; career-site URLs carry both too.
    (re.compile(r"https?://([\w-]+)(\.wd\d+\.myworkdayjobs\.com)/wday/cxs/([\w-]+)/([\w-]+)", re.I),
     lambda m: {"ats": "workday", "tenant": m.group(3), "host": m.group(1) + m.group(2),
                "site": m.group(4)}),
    (re.compile(r"https?://([\w-]+)(\.wd\d+\.myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)", re.I),
     lambda m: {"ats": "workday", "tenant": m.group(1), "host": m.group(1) + m.group(2),
                "site": m.group(3)}),
    # Eightfold.
    (re.compile(r"https?://([\w.-]+\.eightfold\.ai)/", re.I),
     lambda m: {"ats": "eightfold", "base_url": f"https://{m.group(1)}"}),
]


def classify_ats_url(url: str) -> dict | None:
    """Map one URL to an ATS detection ({'ats': ..., **params}) or None."""
    for pattern, build in _URL_RULES:
        match = pattern.search(url)
        if match:
            detection = build(match)
            if detection:
                return detection
    return None


def survey_urls(urls: list[str]) -> list[dict]:
    """Classify many URLs, deduped, most specific (API hits) first."""
    seen: set[tuple] = set()
    detections = []
    for url in urls:
        detection = classify_ats_url(url)
        if not detection:
            continue
        key = tuple(sorted(detection.items()))
        if key in seen:
            continue
        seen.add(key)
        detections.append(detection)
    return detections


def slug_candidates(company_name: str) -> list[str]:
    """'Warby Parker' → warbyparker, warby-parker, warby — the slug spellings
    ATS vendors actually use."""
    words = re.findall(r"[A-Za-z0-9]+", company_name.lower())
    if not words:
        return []
    candidates = ["".join(words)]
    if len(words) > 1:
        candidates += ["-".join(words), words[0]]
    return candidates


# Probe endpoints that confirm a slug with one unauthenticated GET.
_PROBES = [
    ("greenhouse", "board", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
    ("lever", "org", "https://api.lever.co/v0/postings/{slug}?mode=json&limit=1"),
    ("ashby", "org", "https://api.ashbyhq.com/posting-api/job-board/{slug}"),
    ("smartrecruiters", "org", "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1"),
]


def probe_slugs(company_name: str, session) -> list[dict]:
    """Try name-derived slugs against every probeable ATS API. Returns
    confirmed detections (HTTP 200 with at least one posting)."""
    detections = []
    for slug in slug_candidates(company_name):
        for ats, param, template in _PROBES:
            try:
                resp = session.get(template.format(slug=slug), timeout=10)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                count = len(data.get("jobs") or data.get("postings")
                            or data.get("content") or (data if isinstance(data, list) else []))
                if count:
                    detections.append({"ats": ats, param: slug, "_postings": count})
            except Exception:  # noqa: BLE001 — probes are best-effort by nature
                continue
    return detections


_SURVEY_ASSET_RE = re.compile(
    r"\.(js|css|png|jpe?g|gif|svg|woff2?|ttf|ico|mp4|webp)(\?|$)", re.I)


_HOP_HINT_RE = re.compile(
    r"(open[-_ ]?(roles?|positions?)|/jobs\b|/job-?listings?|careers?/"
    r"|join[-_ ]?us|vacanc|openings)", re.I)


def _site(netloc: str) -> str:
    return netloc.lower().split(":")[0].removeprefix("www.")


def hop_candidates(hrefs: list[str], current_url: str) -> list[str]:
    """Anchor targets worth one more survey hop: job-listing-ish links,
    deduped, same-site first. Marketing careers pages routinely keep the
    actual listings (and their ATS traffic) one click away — Grammarly's
    superhuman.com/company/careers landing is the motivating case."""
    def norm(url: str) -> str:
        return url.split("#", 1)[0].rstrip("/").replace("://www.", "://", 1)

    current_site = _site(urlparse(current_url).netloc)
    same, other, seen = [], [], {norm(current_url)}
    for href in hrefs:
        if not href or not href.startswith("http"):
            continue
        clean = href.split("#", 1)[0].rstrip("/")
        if not clean or norm(clean) in seen or _SURVEY_ASSET_RE.search(clean):
            continue
        if not _HOP_HINT_RE.search(clean):
            continue
        seen.add(norm(clean))
        bucket = same if _site(urlparse(clean).netloc) == current_site else other
        bucket.append(clean)
    return same + other


def browser_survey(careers_url: str, runtime, max_hops: int = 2) -> tuple[list[dict], list[str]]:
    """Load the careers page and classify every URL its frontend touches:
    the XHRs it fires, the iframes it embeds, where it redirects to, and the
    anchor links in its DOM (hosted boards are often plain links). When the
    landing page yields nothing, follows up to `max_hops` job-listing-ish
    links one level deeper. Also returns the deduped non-asset URLs seen, so
    a 'no ATS detected' outcome still leaves something to classify by hand."""
    page = runtime._context.new_page()  # noqa: SLF001 — shared runtime owns lifecycle
    urls: list[str] = []
    page.on("request", lambda req: urls.append(req.url))

    def visit(target: str) -> list[str]:
        page.goto(target, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:  # noqa: BLE001 — busy pages never go idle
            pass
        urls.append(page.url)  # redirect target often IS the hosted board
        urls.extend(frame.url for frame in page.frames)
        try:
            return page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        except Exception:  # noqa: BLE001
            return []

    try:
        hrefs = visit(careers_url)
        urls.extend(hrefs)
        detections = survey_urls(urls)
        for hop in hop_candidates(hrefs, page.url)[:max_hops]:
            if detections:
                break
            urls.extend(visit(hop))
            detections = survey_urls(urls)
    finally:
        page.close()
    interesting, seen = [], set()
    for url in urls:
        if url in seen or _SURVEY_ASSET_RE.search(url):
            continue
        seen.add(url)
        interesting.append(url)
    return detections, interesting


def emit_stanza(name: str, detection: dict, careers_url: str = "") -> str:
    """Render a detection as a ready-to-paste companies.yaml entry."""
    lines = [f"  - name: {name}", "    tags: [top50]", f"    ats: {detection['ats']}"]
    for key, value in detection.items():
        if key in ("ats", "_postings"):
            continue
        lines.append(f"    {key}: {value}")
    if detection["ats"] == "eightfold":
        domain = urlparse(careers_url or "").netloc or "<company-domain.com>"
        lines.append(f"    domain: {domain}  # verify: the Eightfold 'domain' param")
    if careers_url:
        lines.append(f"    careers_url: {careers_url}")
    return "\n".join(lines)


def _careers_url_from_config(root: Path, company_name: str) -> str:
    from .config import load_companies
    companies, manual = load_companies(root / "config" / "companies.yaml")
    wanted = company_name.lower()
    for company in companies:
        if company.name.lower() == wanted:
            return company.careers_url
    for entry in manual:
        if str(entry.get("name", "")).lower() == wanted:
            return entry.get("careers_url", "")
    return ""


def discover(root: Path, company_name: str, careers_url: str = "") -> int:
    """CLI entry point: probe APIs, then (if needed) survey the careers page."""
    import requests

    careers_url = careers_url or _careers_url_from_config(root, company_name)
    print(f"Discovering ATS for {company_name}"
          + (f" (careers page: {careers_url})" if careers_url else ""))

    detections = []
    if careers_url:  # the careers URL itself may already give it away
        detections = survey_urls([careers_url])

    if not detections:
        print("· probing name-derived slugs against Greenhouse/Lever/Ashby/SmartRecruiters…")
        session = requests.Session()
        detections = probe_slugs(company_name, session)

    surveyed_urls: list[str] = []
    if not detections and careers_url:
        print("· no API probe hit — surveying the careers page in headless Chromium…")
        from .browser import BrowserRuntime, BrowserUnavailable
        try:
            with BrowserRuntime() as runtime:
                detections, surveyed_urls = browser_survey(careers_url, runtime)
        except BrowserUnavailable as exc:
            print(f"  browser unavailable: {exc}", file=sys.stderr)

    if not detections:
        print(f"\nNo ATS detected for {company_name}. The board may be custom "
              "or behind bot protection — keep it in manual_check.")
        if surveyed_urls:
            print("URLs the page touched (for manual classification — the jobs "
                  "API is often recognizable here):")
            for url in surveyed_urls[:15]:
                print(f"  - {url[:160]}")
        elif not careers_url:
            print("Tip: pass --url <careers page> to enable the browser survey.")
        return 1

    print(f"\nDetected {len(detections)} board(s). Paste into config/companies.yaml:\n")
    for detection in detections:
        postings = detection.get("_postings")
        if postings:
            print(f"  # confirmed live — {postings}+ postings via API probe")
        print(emit_stanza(company_name, detection, careers_url))
        print()
    print("Then run: python -m jobsearch verify")
    return 0
