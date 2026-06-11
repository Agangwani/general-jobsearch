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
    return [parse_job(raw, company.name) for raw in results]
