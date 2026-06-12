"""Uber careers internal search API (www.uber.com/api/loadSearchJobsResults)."""

from __future__ import annotations

from ..http import post_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html

API = "https://www.uber.com/api/loadSearchJobsResults?localeCode=en"


def parse_job(raw: dict, company_name: str) -> JobPosting:
    all_locations = raw.get("allLocations") or []
    parts = []
    for loc in all_locations:
        if isinstance(loc, dict):
            parts.append(", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("countryName")])))
    location = "; ".join(filter(None, parts)) or str((raw.get("location") or {}).get("city", ""))
    job_id = str(raw.get("id", ""))
    return JobPosting(
        company=company_name,
        title=raw.get("title", ""),
        location=location,
        url=f"https://www.uber.com/global/en/careers/list/{job_id}/",
        job_id=job_id,
        description=strip_html(raw.get("description", "")),
        posted_at=parse_when(raw.get("creationDate") or raw.get("updatedDate")),
        source="uber",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    query = settings.get("search", {}).get("query", "senior software engineer")
    body = {
        "params": {
            "query": query,
            "location": [{"country": "USA", "region": "New York", "city": "New York"}],
        },
        "page": 0,
        "limit": 100,
    }
    headers = {"Content-Type": "application/json", "x-csrf-token": "x"}
    data = post_json(session, API, json=body, headers=headers)
    results = ((data.get("data") or {}).get("results")) or []
    return [parse_job(raw, company.name) for raw in results]
