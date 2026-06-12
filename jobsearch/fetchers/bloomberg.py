"""Bloomberg careers JSON search (careers.bloomberg.com)."""

from __future__ import annotations

from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when

API = "https://careers.bloomberg.com/json/search/joblist"


def parse_job(raw: dict, company_name: str) -> JobPosting:
    job_id = str(raw.get("JobsId") or raw.get("id", ""))
    locations = raw.get("Locations") or raw.get("locations") or []
    if isinstance(locations, list):
        location = ", ".join(str(loc) for loc in locations)
    else:
        location = str(locations)
    return JobPosting(
        company=company_name,
        title=raw.get("JobTitle") or raw.get("title", ""),
        location=location,
        url=f"https://careers.bloomberg.com/job/detail/{job_id}",
        job_id=job_id,
        description=str(raw.get("Description") or raw.get("description", "")),
        posted_at=parse_when(raw.get("PostedDate") or raw.get("posted_date")),
        source="bloomberg",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    query = settings.get("search", {}).get("query", "senior software engineer")
    params = {"ftsearch": query, "location": "New York", "sort": "POSTED_DATE"}
    data = get_json(session, API, params=params)
    results = data.get("results") or data.get("jobs") or []
    if not results:
        raise RuntimeError("Bloomberg joblist API returned no results — endpoint may have moved")
    return [parse_job(raw, company.name) for raw in results]


def fetch_browser(company: Company, runtime, settings: dict) -> list[JobPosting]:
    """Fallback: load the Bloomberg careers search page in Chromium and
    capture whatever jobs JSON its frontend loads."""
    from ..utils import walk_collect

    url = "https://careers.bloomberg.com/job/search?ftsearch=senior%20software%20engineer&location=New%20York"
    payloads = runtime.capture_json(url, r"careers\.bloomberg\.com/.*(json|api|search)")
    records = walk_collect(
        payloads,
        lambda d: any(k in d for k in ("JobTitle", "jobTitle", "title"))
        and any(k in d for k in ("JobsId", "jobId", "id")),
    )
    if not records:
        raise RuntimeError("no job records captured from careers.bloomberg.com")
    return [parse_job(raw, company.name) for raw in records]
