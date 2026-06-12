"""SmartRecruiters public postings API.

The list endpoint has no descriptions, so details are fetched per-posting —
only for jobs that already pass the title/location filter, capped by
fetch.max_detail_requests (same pattern as the Workday adapter).
"""

from __future__ import annotations

from ..filters import JobFilter
from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html

PAGE_SIZE = 100
MAX_PAGES = 5


def parse_job(raw: dict, company_name: str, org: str) -> JobPosting:
    location = raw.get("location") or {}
    parts = [location.get("city", ""), location.get("region", ""), location.get("country", "")]
    job_id = str(raw.get("id", ""))
    return JobPosting(
        company=company_name,
        title=raw.get("name", ""),
        location=", ".join(p for p in parts if p),
        url=f"https://jobs.smartrecruiters.com/{org}/{job_id}",
        job_id=job_id,
        posted_at=parse_when(raw.get("releasedDate")),
        source="smartrecruiters",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    org = company.params["org"]
    base = f"https://api.smartrecruiters.com/v1/companies/{org}/postings"

    jobs: list[JobPosting] = []
    for page in range(MAX_PAGES):
        data = get_json(session, base, params={"limit": PAGE_SIZE, "offset": page * PAGE_SIZE})
        postings = data.get("content", [])
        jobs.extend(parse_job(raw, company.name, org) for raw in postings)
        if len(postings) < PAGE_SIZE:
            break
    if not jobs:
        raise RuntimeError(f"smartrecruiters company '{org}' returned 0 postings — id may be stale")

    job_filter = JobFilter(settings.get("search", {}))
    max_details = settings.get("fetch", {}).get("max_detail_requests", 40)
    detailed = 0
    for job in jobs:
        if detailed >= max_details or not job_filter.matches(job):
            continue
        try:
            detail = get_json(session, f"{base}/{job.job_id}")
            sections = ((detail.get("jobAd") or {}).get("sections")) or {}
            job.description = " ".join(
                strip_html(section.get("text", "")) for section in sections.values()
                if isinstance(section, dict)
            ).strip()
            detailed += 1
        except Exception:
            continue  # description is a nice-to-have; title still scores
    return jobs
