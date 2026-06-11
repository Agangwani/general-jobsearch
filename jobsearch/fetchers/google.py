"""Google careers public search API (careers.google.com/api/v3/search)."""

from __future__ import annotations

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
    return jobs
