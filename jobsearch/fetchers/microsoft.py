"""Microsoft careers public search API (gcsservices.careers.microsoft.com)."""

from __future__ import annotations

from ..filters import JobFilter
from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html

API = "https://gcsservices.careers.microsoft.com/search/api/v1/search"
DETAIL_API = "https://gcsservices.careers.microsoft.com/search/api/v1/job/{job_id}"
PAGE_SIZE = 20
MAX_PAGES = 5


def enrich_descriptions(jobs: list[JobPosting], session, settings: dict) -> None:
    """The search endpoint returns job stubs without the posting body, so every
    Microsoft role otherwise reaches scoring on its *title alone* and is
    systematically under-ranked. Pull the full description from the per-job
    detail endpoint — but only for jobs already past the title/location filter,
    bounded by fetch.max_detail_requests, exactly like the Workday fetcher.
    Best-effort: a failed detail fetch leaves the title, which still scores."""
    job_filter = JobFilter(settings.get("search", {}))
    max_details = settings.get("fetch", {}).get("max_detail_requests", 40)
    detailed = 0
    for job in jobs:
        if job.description.strip() or detailed >= max_details or not job_filter.matches(job):
            continue
        try:
            data = get_json(session, DETAIL_API.format(job_id=job.job_id),
                            params={"lang": "en_us"})
            result = ((data.get("operationResult") or {}).get("result")) or {}
            body = " ".join(
                strip_html(result.get(field, "") or "")
                for field in ("description", "responsibilities", "qualifications")
            ).strip()
            if body:
                job.description = body
                detailed += 1
        except Exception:  # noqa: BLE001 — description is best-effort; title still scores
            continue


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
    enrich_descriptions(jobs, session, settings)
    return jobs


def fetch_browser(company: Company, runtime, settings: dict) -> list[JobPosting]:
    """Fallback: load the careers search page and capture its own search XHR —
    sidesteps TLS/endpoint changes on the gcsservices host."""
    from ..utils import walk_collect

    from . import _generic

    url = (
        "https://jobs.careers.microsoft.com/global/en/search"
        "?q=senior%20software%20engineer&lc=New%20York%2C%20New%20York%2C%20United%20States&o=Recent"
    )
    harvest = runtime.harvest(url, r"(search/api/v1/search|careers\.microsoft\.com.*search)")
    records = walk_collect(harvest["matched"] + harvest["embedded"],
                           lambda d: "jobId" in d and "title" in d)
    if records:
        return [parse_job(raw, company.name) for raw in records]
    jobs = _generic.fallback_jobs(harvest, company.name, "microsoft")
    if not jobs:
        raise RuntimeError("no job records captured from jobs.careers.microsoft.com "
                           f"({_generic.debug_summary(harvest)})")
    return jobs
