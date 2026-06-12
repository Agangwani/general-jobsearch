"""JPMorgan Chase careers (Oracle Recruiting Cloud) via browser XHR capture."""

from __future__ import annotations

from ..models import Company, JobPosting
from ..utils import first, parse_when, walk_collect

URL = (
    "https://careers.jpmorgan.com/us/en/search-results"
    "?qcountry=United%20States&qcity=New%20York&qstate=New%20York"
)
XHR_PATTERN = r"(recruitingCEJobRequisitions|/search-results|/widgets|phenom)"

TITLE_KEYS = ("Title", "title", "jobTitle", "name")
ID_KEYS = ("Id", "jobId", "id", "reqId", "jobSeqNo")
LOCATION_KEYS = ("PrimaryLocation", "cityStateCountry", "cityState", "location", "locations")
DATE_KEYS = ("PostedDate", "postedDate", "dateCreated", "publishDate")
DESC_KEYS = ("ShortDescriptionStr", "description", "descriptionTeaser", "category")
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
        url = str(first(record, URL_KEYS)) or f"https://careers.jpmorgan.com/us/en/job/{job_id}"
        jobs.append(JobPosting(
            company=company_name,
            title=str(first(record, TITLE_KEYS)),
            location=str(location),
            url=url,
            job_id=job_id,
            description=str(first(record, DESC_KEYS)),
            posted_at=parse_when(first(record, DATE_KEYS, None)),
            source="jpmorgan",
        ))
    return jobs


def fetch(company: Company, runtime, settings: dict) -> list[JobPosting]:
    payloads = runtime.capture_json(URL, XHR_PATTERN)
    jobs = parse_payloads(payloads, company.name)
    if not jobs:
        raise RuntimeError("no job records found in captured careers.jpmorgan.com responses")
    return jobs
