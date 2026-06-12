"""Goldman Sachs careers (higher.gs.com) via headless browser XHR capture."""

from __future__ import annotations

from ..models import Company, JobPosting
from ..utils import first, parse_when, walk_collect

URL = "https://higher.gs.com/results?LOCATION=New%20York&sort=POSTED_DATE&page=1"
XHR_PATTERN = r"higher\.gs\.com/(api|graphql|search)"

TITLE_KEYS = ("jobTitle", "title", "roleTitle", "name")
ID_KEYS = ("jobId", "id", "roleId", "requisitionId")
LOCATION_KEYS = ("location", "locations", "city", "cityName", "primaryLocation")
DATE_KEYS = ("postedDate", "postDate", "createdDate", "datePosted")
DESC_KEYS = ("description", "jobDescription", "summary", "division", "jobFunction")


def _looks_like_job(record: dict) -> bool:
    return any(k in record for k in TITLE_KEYS) and any(k in record for k in ID_KEYS)


def parse_payloads(payloads: list, company_name: str) -> list[JobPosting]:
    jobs = []
    for record in walk_collect(payloads, _looks_like_job):
        job_id = str(first(record, ID_KEYS))
        location = first(record, LOCATION_KEYS)
        if isinstance(location, list):
            location = ", ".join(str(loc) for loc in location)
        jobs.append(JobPosting(
            company=company_name,
            title=str(first(record, TITLE_KEYS)),
            location=str(location),
            url=f"https://higher.gs.com/roles/{job_id}",
            job_id=job_id,
            description=str(first(record, DESC_KEYS)),
            posted_at=parse_when(first(record, DATE_KEYS, None)),
            source="goldman",
        ))
    return jobs


def fetch(company: Company, runtime, settings: dict) -> list[JobPosting]:
    from . import _generic

    harvest = runtime.harvest(URL, XHR_PATTERN)
    jobs = parse_payloads(harvest["matched"] + harvest["embedded"], company.name)
    if not jobs:
        jobs = _generic.fallback_jobs(harvest, company.name, "goldman",
                                      link_fmt="https://higher.gs.com/roles/{id}")
    if not jobs:
        raise RuntimeError("no job records found in captured higher.gs.com responses")
    return jobs
