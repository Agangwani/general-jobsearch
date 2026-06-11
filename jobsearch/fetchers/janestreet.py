"""Jane Street open roles (janestreet.com).

The open-roles page hydrates from a jobs JSON the frontend fetches; capture
that XHR first, and fall back to scraping the rendered role-card links if the
JSON shape ever changes. Postings carry no dates, so they score with the
configured unknown-age penalty (like Spotify).
"""

from __future__ import annotations

from ..models import Company, JobPosting
from ..utils import first, walk_collect

URL = (
    "https://www.janestreet.com/join-jane-street/open-roles/"
    "?type=experienced-candidates&location=new-york"
)
XHR_PATTERN = r"janestreet\.com/.*\.json"

TITLE_KEYS = ("position", "title", "name")
ID_KEYS = ("id", "slug", "position_id")
LOCATION_KEYS = ("city", "location", "locations")
DESC_KEYS = ("overview", "description", "team", "department")


def _looks_like_job(record: dict) -> bool:
    return any(k in record for k in TITLE_KEYS) and any(k in record for k in ID_KEYS)


def parse_payloads(payloads: list, company_name: str) -> list[JobPosting]:
    jobs = []
    for record in walk_collect(payloads, _looks_like_job):
        job_id = str(first(record, ID_KEYS))
        location = first(record, LOCATION_KEYS, "New York")
        if isinstance(location, list):
            location = ", ".join(str(loc) for loc in location)
        jobs.append(JobPosting(
            company=company_name,
            title=str(first(record, TITLE_KEYS)),
            location=str(location),
            url=f"https://www.janestreet.com/join-jane-street/position/{job_id}/",
            job_id=job_id,
            description=str(first(record, DESC_KEYS)),
            source="janestreet",
        ))
    return jobs


def parse_links(links: list[dict], company_name: str) -> list[JobPosting]:
    jobs = []
    for link in links:
        href = link.get("href", "")
        title = (link.get("text") or "").strip().split("\n")[0]
        if "/position/" not in href or not title:
            continue
        job_id = href.rstrip("/").rsplit("/", 1)[-1]
        jobs.append(JobPosting(
            company=company_name,
            title=title,
            location="New York",
            url=href,
            job_id=job_id,
            source="janestreet",
        ))
    return jobs


def fetch(company: Company, runtime, settings: dict) -> list[JobPosting]:
    payloads = runtime.capture_json(URL, XHR_PATTERN)
    jobs = parse_payloads(payloads, company.name)
    if not jobs:
        links = runtime.extract_links(URL, "a[href*='/position/']")
        jobs = parse_links(links, company.name)
    if not jobs:
        raise RuntimeError("no roles found via janestreet.com JSON capture or DOM scrape")
    return jobs
