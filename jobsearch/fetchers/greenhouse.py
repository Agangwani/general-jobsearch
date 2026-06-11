"""Greenhouse public board API: https://boards-api.greenhouse.io"""

from __future__ import annotations

from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html


def parse_job(raw: dict, company_name: str) -> JobPosting:
    location = (raw.get("location") or {}).get("name", "")
    offices = ", ".join(o.get("name", "") for o in raw.get("offices") or [])
    return JobPosting(
        company=company_name,
        title=raw.get("title", ""),
        location=location or offices,
        url=raw.get("absolute_url", ""),
        job_id=str(raw.get("id", "")),
        description=strip_html(raw.get("content", "")),
        posted_at=parse_when(raw.get("first_published") or raw.get("updated_at")),
        source="greenhouse",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    board = company.params["board"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    data = get_json(session, url)
    limit = settings.get("fetch", {}).get("max_per_company", 1500)
    return [parse_job(raw, company.name) for raw in data.get("jobs", [])[:limit]]
