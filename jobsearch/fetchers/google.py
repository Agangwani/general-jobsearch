"""Google careers public search API (careers.google.com/api/v3/search)."""

from __future__ import annotations

import re

from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html

BASE = "https://careers.google.com/api/v3/search/"
MAX_PAGES = 3


def parse_job(raw: dict, company_name: str) -> JobPosting:
    locations = ", ".join(
        loc.get("display", "") for loc in raw.get("locations") or [] if isinstance(loc, dict)
    )
    job_id = str(raw.get("id", "")).rsplit("/", 1)[-1]
    description = " ".join(
        strip_html(raw.get(field, "") or "")
        for field in ("summary", "description", "qualifications", "responsibilities")
    )
    url = raw.get("apply_url") or (
        f"https://www.google.com/about/careers/applications/jobs/results/{job_id}"
    )
    return JobPosting(
        company=company_name,
        title=raw.get("title", ""),
        location=locations,
        url=url,
        job_id=job_id,
        description=description.strip(),
        posted_at=parse_when(raw.get("publish_date") or raw.get("created")),
        source="google",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    query = settings.get("search", {}).get("query", "senior software engineer")
    jobs: list[JobPosting] = []
    for page in range(1, MAX_PAGES + 1):
        params = {
            "q": query,
            "location": "New York, NY, USA",
            "page": page,
            "sort_by": "date",
        }
        data = get_json(session, BASE, params=params)
        page_jobs = data.get("jobs", [])
        jobs.extend(parse_job(raw, company.name) for raw in page_jobs)
        if not page_jobs or len(jobs) >= data.get("count", 0):
            break
    if not jobs:
        raise RuntimeError("Google careers API returned no jobs — endpoint may have moved")
    return jobs


def fetch_browser(company: Company, runtime, settings: dict) -> list[JobPosting]:
    """Fallback: the careers frontend moved to google.com/about/careers/applications
    and the old api/v3 endpoint 404s. Load the search page in Chromium and
    capture whatever jobs JSON the new frontend fetches."""
    from ..utils import walk_collect

    from . import _generic

    url = (
        "https://www.google.com/about/careers/applications/jobs/results/"
        "?location=New%20York%2C%20NY&q=%22software%20engineer%22&sort_by=date"
    )
    harvest = runtime.harvest(url, r"google\.com/.*(search|jobs|careers)")
    records = walk_collect(
        harvest["matched"] + harvest["embedded"],
        lambda d: "title" in d and ("id" in d or "job_id" in d) and "locations" in d,
    )
    if records:
        return [parse_job(raw, company.name) for raw in records]
    jobs = _generic.fallback_jobs(harvest, company.name, "google")
    if not jobs:
        # Google renders results server-side (AF_initDataCallback, not plain
        # JSON) — scrape the result links as the last resort. The search URL
        # already pins location to New York, so link + slug are enough. Sweep
        # every anchor and let parse_cards filter: the card markup churns,
        # the /jobs/results/<id>-<slug> URL shape doesn't.
        links = runtime.extract_links(url, "a[href]",
                                      wait_selector="a[href*='jobs/results/']")
        jobs = parse_cards(links, company.name)
    if not jobs:
        raise RuntimeError("no job records captured from Google careers page "
                           f"({_generic.debug_summary(harvest)})")
    return jobs


_CARD_ID = re.compile(r"jobs/results/(\d+)(?:-([a-z0-9-]+))?", re.I)


def parse_cards(links: list[dict], company_name: str) -> list[JobPosting]:
    """[{text, href}] from the results page → postings. Pure — offline-tested.
    Location comes from the search URL's filter; dates are not on the cards
    (unknown-age handling covers that). When the anchor text is unhelpful
    ("Apply", icons) the title is rebuilt from the URL slug."""
    jobs, seen = [], set()
    for link in links:
        m = _CARD_ID.search(link.get("href") or "")
        if not m or m.group(1) in seen:
            continue
        title = (link.get("text") or "").strip().split("\n")[0]
        title = re.sub(r"^learn more about\s+", "", title, flags=re.I).strip()
        if (len(title) < 8 or title.lower() in ("apply", "apply now", "share")) \
                and m.group(2):
            title = m.group(2).replace("-", " ").strip().title()
        if not title:
            continue
        seen.add(m.group(1))
        jobs.append(JobPosting(
            company=company_name,
            title=title,
            location="New York, NY",
            url=f"https://www.google.com/about/careers/applications/jobs/results/{m.group(1)}",
            job_id=m.group(1),
            source="google",
        ))
    return jobs
