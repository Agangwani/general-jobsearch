"""Workday CXS job search API (used by NVIDIA, Salesforce, Adobe, ...).

POST https://{host}/wday/cxs/{tenant}/{site}/jobs with a searchText body.
Workday only exposes relative posting dates ("Posted 3 Days Ago") in the
list view, and descriptions require one extra request per job, so detail
fetches are capped and best-effort.
"""

from __future__ import annotations

from ..filters import JobFilter
from ..http import post_json, get_json
from ..models import Company, JobPosting
from ..utils import parse_workday_posted_on, strip_html

PAGE_SIZE = 20
MAX_PAGES = 10


def parse_job(raw: dict, company: Company) -> JobPosting:
    host = company.params["host"]
    site = company.params["site"]
    external_path = raw.get("externalPath", "")
    return JobPosting(
        company=company.name,
        title=raw.get("title", ""),
        location=raw.get("locationsText", ""),
        url=f"https://{host}/en-US/{site}{external_path}",
        job_id=external_path.rsplit("/", 1)[-1] or raw.get("bulletFields", [""])[0],
        posted_at=parse_workday_posted_on(raw.get("postedOn", "")),
        source="workday",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    tenant = company.params["tenant"]
    host = company.params["host"]
    site = company.params["site"]
    query = settings.get("search", {}).get("query", "senior software engineer")
    # Without a location term, popular tenants (NVIDIA, Adobe, Salesforce)
    # exhaust the page budget on non-NYC results: the 2026-06-12 funnel showed
    # NVIDIA at 98/100 title passes and 0/100 location passes. Tenant-specific
    # location facet GUIDs can be supplied via a `facets:` param when known.
    location_term = company.params.get("location_term", "New York")
    facets = company.params.get("facets") or {}
    base = f"https://{host}/wday/cxs/{tenant}/{site}"

    jobs: list[JobPosting] = []
    for page in range(MAX_PAGES):
        body = {
            "appliedFacets": facets,
            "limit": PAGE_SIZE,
            "offset": page * PAGE_SIZE,
            "searchText": f"{query} {location_term}".strip(),
        }
        data = post_json(session, f"{base}/jobs", json=body)
        postings = data.get("jobPostings", [])
        jobs.extend(parse_job(raw, company) for raw in postings if raw.get("externalPath"))
        if len(postings) < PAGE_SIZE:
            break

    # Pull descriptions only for postings that already pass the title/location
    # filter, so the per-job detail requests stay bounded.
    job_filter = JobFilter(settings.get("search", {}))
    max_details = settings.get("fetch", {}).get("max_detail_requests", 40)
    detailed = 0
    for job in jobs:
        if detailed >= max_details or not job_filter.matches(job):
            continue
        try:
            external_path = job.url.split(site, 1)[1]
            detail = get_json(session, f"{base}{external_path}")
            job.description = strip_html(
                (detail.get("jobPostingInfo") or {}).get("jobDescription", "")
            )
            detailed += 1
        except Exception:
            continue  # description is a nice-to-have; title still scores
    return jobs
