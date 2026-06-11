"""Lever public postings API: https://api.lever.co/v0/postings/{org}"""

from __future__ import annotations

from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html


def parse_job(raw: dict, company_name: str) -> JobPosting:
    categories = raw.get("categories") or {}
    description = raw.get("descriptionPlain") or strip_html(raw.get("description", ""))
    extra = " ".join(strip_html(item.get("content", "")) for item in raw.get("lists") or [])
    location = categories.get("location", "")
    all_locations = raw.get("workplaceType", "")
    return JobPosting(
        company=company_name,
        title=raw.get("text", ""),
        location=location or all_locations,
        url=raw.get("hostedUrl", ""),
        job_id=str(raw.get("id", "")),
        description=f"{description}\n{extra}".strip(),
        posted_at=parse_when(raw.get("createdAt")),
        source="lever",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    org = company.params["org"]
    url = f"https://api.lever.co/v0/postings/{org}?mode=json"
    data = get_json(session, url)
    limit = settings.get("fetch", {}).get("max_per_company", 1500)
    return [parse_job(raw, company.name) for raw in data[:limit]]
