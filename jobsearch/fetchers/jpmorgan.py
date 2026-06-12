"""JPMorgan Chase careers (Oracle Recruiting Cloud) via browser XHR capture."""

from __future__ import annotations

from ..models import Company, JobPosting
from ..utils import first, parse_when, walk_collect

# careers.jpmorgan.com now redirects to a www.jpmorganchase.com landing page
# (run diagnostics, 2026-06-12) with no jobs data on it. Their application
# stack is Oracle Recruiting Cloud — navigate its CandidateExperience search
# directly; it fires the recruitingCEJobRequisitions XHR on load.
URL = (
    "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/requisitions"
    "?keyword=software%20engineer&location=New%20York%2C%20NY%2C%20United%20States&mode=location"
)
XHR_PATTERN = r"(recruitingCEJobRequisitions|hcmRestApi|/search-results|/widgets|phenom)"

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
        url = str(first(record, URL_KEYS)) or (
        "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001"
        f"/job/{job_id}")
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
    from . import _generic

    harvest = runtime.harvest(URL, XHR_PATTERN)
    jobs = parse_payloads(harvest["matched"] + harvest["embedded"], company.name)
    if not jobs:
        jobs = _generic.fallback_jobs(
            harvest, company.name, "jpmorgan",
            link_fmt="https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience"
                     "/en/sites/CX_1001/job/{id}")
    if not jobs:
        raise RuntimeError("no job records found in captured careers.jpmorgan.com responses "
                           f"({_generic.debug_summary(harvest)})")
    return jobs
