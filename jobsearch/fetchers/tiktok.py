"""TikTok careers (lifeattiktok.com) via browser XHR capture."""

from __future__ import annotations

from ..models import Company, JobPosting
from ..utils import first, parse_when, strip_html, walk_collect

URL = "https://lifeattiktok.com/search?location=CT_114&keyword=software%20engineer"
XHR_PATTERN = r"(api\.lifeattiktok\.com|/search/job|job/posts)"

TITLE_KEYS = ("title", "job_title", "name")
ID_KEYS = ("id", "job_post_id", "job_id")
DATE_KEYS = ("publish_time", "publish_date", "create_time")
DESC_KEYS = ("description", "requirement", "job_function")


def _looks_like_job(record: dict) -> bool:
    return any(k in record for k in TITLE_KEYS) and any(k in record for k in ID_KEYS)


def _location(record: dict) -> str:
    city = record.get("city_info") or record.get("location_info") or {}
    if isinstance(city, dict):
        return str(city.get("name") or city.get("en_name", ""))
    locations = record.get("city_list") or []
    if isinstance(locations, list):
        return ", ".join(
            str(loc.get("name", loc) if isinstance(loc, dict) else loc) for loc in locations
        )
    return str(city)


def parse_payloads(payloads: list, company_name: str) -> list[JobPosting]:
    jobs = []
    for record in walk_collect(payloads, _looks_like_job):
        job_id = str(first(record, ID_KEYS))
        description = " ".join(strip_html(str(record.get(k, ""))) for k in DESC_KEYS)
        jobs.append(JobPosting(
            company=company_name,
            title=str(first(record, TITLE_KEYS)),
            location=_location(record),
            url=f"https://lifeattiktok.com/search/{job_id}",
            job_id=job_id,
            description=description.strip(),
            posted_at=parse_when(first(record, DATE_KEYS, None)),
            source="tiktok",
        ))
    return jobs


def fetch(company: Company, runtime, settings: dict) -> list[JobPosting]:
    payloads = runtime.capture_json(URL, XHR_PATTERN)
    jobs = parse_payloads(payloads, company.name)
    if not jobs:
        raise RuntimeError("no job records found in captured lifeattiktok.com responses")
    return jobs
