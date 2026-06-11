"""Microsoft careers public search API (gcsservices.careers.microsoft.com)."""

from __future__ import annotations

from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html

API = "https://gcsservices.careers.microsoft.com/search/api/v1/search"
PAGE_SIZE = 20
MAX_PAGES = 5


def parse_job(raw: dict, company_name: str) -> JobPosting:
    props = raw.get("properties") or {}
    locations = props.get("locations") or [props.get("primaryLocation", "")]
    job_id = str(raw.get("jobId", ""))
    return JobPosting(
        company=company_name,
        title=raw.get("title", ""),
        location=", ".join(loc for loc in locations if loc),
        url=f"https://jobs.careers.microsoft.com/global/en/job/{job_id}",
        job_id=job_id,
        description=strip_html(props.get("description", "")),
        posted_at=parse_when(raw.get("postingDate")),
        source="microsoft",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    query = settings.get("search", {}).get("query", "senior software engineer")
    jobs: list[JobPosting] = []
    for page in range(1, MAX_PAGES + 1):
        params = {
            "q": query,
            "lc": "New York, New York, United States",
            "l": "en_us",
            "pg": page,
            "pgSz": PAGE_SIZE,
            "o": "Recent",
            "flt": "true",
        }
        data = get_json(session, API, params=params)
        result = ((data.get("operationResult") or {}).get("result")) or {}
        page_jobs = result.get("jobs", [])
        jobs.extend(parse_job(raw, company.name) for raw in page_jobs)
        if len(page_jobs) < PAGE_SIZE:
            break
    return jobs
