"""Ashby public job-board API: https://api.ashbyhq.com/posting-api/job-board/{org}"""

from __future__ import annotations

from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html


def parse_job(raw: dict, company_name: str) -> JobPosting:
    locations = [raw.get("location") or ""]
    locations += [loc.get("location", "") for loc in raw.get("secondaryLocations") or []]
    if raw.get("isRemote"):
        locations.append("Remote - US")
    description = raw.get("descriptionPlain") or strip_html(raw.get("descriptionHtml", ""))
    return JobPosting(
        company=company_name,
        title=raw.get("title", ""),
        location=", ".join(loc for loc in locations if loc),
        url=raw.get("jobUrl") or raw.get("applyUrl", ""),
        job_id=str(raw.get("id", "")),
        description=description,
        posted_at=parse_when(raw.get("publishedAt")),
        source="ashby",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    org = company.params["org"]
    url = f"https://api.ashbyhq.com/posting-api/job-board/{org}"
    data = get_json(session, url)
    limit = settings.get("fetch", {}).get("max_per_company", 1500)
    jobs = [raw for raw in data.get("jobs", []) if raw.get("isListed", True)]
    if not jobs:
        raise RuntimeError(f"ashby board '{org}' returned 0 postings — org may have migrated ATS")
    return [parse_job(raw, company.name) for raw in jobs[:limit]]
