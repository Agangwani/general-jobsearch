"""Amazon's public search API on amazon.jobs (sorted by most recent)."""

from __future__ import annotations

from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html

BASE = "https://www.amazon.jobs"


def parse_job(raw: dict, company_name: str) -> JobPosting:
    description = " ".join(
        strip_html(raw.get(field, "") or "")
        for field in ("description_short", "description", "basic_qualifications", "preferred_qualifications")
    )
    return JobPosting(
        company=company_name,
        title=raw.get("title", ""),
        location=raw.get("location") or raw.get("normalized_location", ""),
        url=BASE + raw.get("job_path", ""),
        job_id=str(raw.get("id_icims") or raw.get("id", "")),
        description=description.strip(),
        posted_at=parse_when(raw.get("posted_date")),
        source="amazon",
    )


PAGE_SIZE = 100
MAX_PAGES = 3  # the 2026-06-12 funnel showed only 9/100 page-1 results were NYC


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    query = settings.get("search", {}).get("query", "senior software engineer")
    jobs: list[JobPosting] = []
    for page in range(MAX_PAGES):
        params = {
            "base_query": query,
            "loc_query": "New York, NY, United States",
            "city[]": "New York",
            "country[]": "USA",
            "sort": "recent",
            "result_limit": PAGE_SIZE,
            "offset": page * PAGE_SIZE,
            "normalized_country_code[]": "USA",
        }
        data = get_json(session, f"{BASE}/en/search.json", params=params)
        batch = data.get("jobs", [])
        jobs.extend(parse_job(raw, company.name) for raw in batch)
        if len(batch) < PAGE_SIZE:
            break
    return jobs
