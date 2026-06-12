"""Millennium Management careers (mlp.com, Phenom platform) via XHR capture."""

from __future__ import annotations

from ..models import Company, JobPosting
from ..utils import first, parse_when, walk_collect

URL = "https://www.mlp.com/job-listings/?location=New%20York"
XHR_PATTERN = r"(mlp\.com/(widgets|api)|phenom)"

TITLE_KEYS = ("title", "jobTitle", "name")
ID_KEYS = ("jobSeqNo", "jobId", "id", "reqId")
LOCATION_KEYS = ("cityStateCountry", "cityState", "location", "city", "multi_location")
DATE_KEYS = ("postedDate", "dateCreated", "publishDate")
DESC_KEYS = ("descriptionTeaser", "description", "category")
URL_KEYS = ("applyUrl", "externalPath", "jobUrl")


def _looks_like_job(record: dict) -> bool:
    return any(k in record for k in TITLE_KEYS) and any(k in record for k in ID_KEYS)


def parse_payloads(payloads: list, company_name: str) -> list[JobPosting]:
    jobs = []
    for record in walk_collect(payloads, _looks_like_job):
        job_id = str(first(record, ID_KEYS))
        location = first(record, LOCATION_KEYS)
        if isinstance(location, list):
            location = ", ".join(str(loc) for loc in location)
        url = str(first(record, URL_KEYS)) or f"https://www.mlp.com/job/{job_id}"
        jobs.append(JobPosting(
            company=company_name,
            title=str(first(record, TITLE_KEYS)),
            location=str(location),
            url=url,
            job_id=job_id,
            description=str(first(record, DESC_KEYS)),
            posted_at=parse_when(first(record, DATE_KEYS, None)),
            source="millennium",
        ))
    return jobs


def fetch(company: Company, runtime, settings: dict) -> list[JobPosting]:
    from . import _generic

    # mlp.com is also Phenom-powered (see jpmorgan.py): the embedded
    # phApp.ddo state plus harvest's built-in retry covers the flakiness
    # where the jobs XHR sometimes never fires.
    harvest = runtime.harvest(URL, XHR_PATTERN)
    jobs = parse_payloads(harvest["matched"] + harvest["embedded"], company.name)
    if not jobs:
        jobs = _generic.fallback_jobs(harvest, company.name, "millennium",
                                      link_fmt="https://www.mlp.com/job/{id}")
    if not jobs:
        raise RuntimeError("no job records found in captured mlp.com responses")
    return jobs
