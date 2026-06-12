"""Eightfold-powered career sites (Netflix's explore.jobs.netflix.net)."""

from __future__ import annotations

from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html

PAGE_SIZE = 50
MAX_PAGES = 4


def parse_job(raw: dict, company_name: str, base_url: str) -> JobPosting:
    locations = raw.get("locations") or [raw.get("location", "")]
    url = raw.get("canonicalPositionUrl") or f"{base_url}/careers/job/{raw.get('id', '')}"
    return JobPosting(
        company=company_name,
        title=raw.get("name", ""),
        location=", ".join(loc for loc in locations if loc),
        url=url,
        job_id=str(raw.get("id", "")),
        description=strip_html(raw.get("job_description", "")),
        posted_at=parse_when(raw.get("t_create") or raw.get("t_update")),
        source="eightfold",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    base_url = company.params["base_url"].rstrip("/")
    domain = company.params["domain"]
    query = settings.get("search", {}).get("query", "senior software engineer")

    jobs: list[JobPosting] = []
    for page in range(MAX_PAGES):
        params = {
            "domain": domain,
            "query": query,
            "location": "New York",
            "start": page * PAGE_SIZE,
            "num": PAGE_SIZE,
            "sort_by": "new",
        }
        data = get_json(session, f"{base_url}/api/apply/v2/jobs", params=params)
        positions = data.get("positions", [])
        jobs.extend(parse_job(raw, company.name, base_url) for raw in positions)
        if len(positions) < PAGE_SIZE:
            break
    return jobs


def fetch_browser(company: Company, runtime, settings: dict) -> list[JobPosting]:
    """Fallback for Eightfold tenants that 403 plain HTTP clients (e.g.
    Morgan Stanley): load the careers page in Chromium and capture the
    /api/apply/v2/jobs XHR the page itself issues."""
    from ..utils import walk_collect

    base_url = company.params["base_url"].rstrip("/")
    url = f"{base_url}/careers?location=New%20York&sort_by=new"
    payloads = runtime.capture_json(url, r"/api/apply/v2/jobs")
    records = walk_collect(payloads, lambda d: "name" in d and "id" in d and ("location" in d or "locations" in d))
    if not records:
        raise RuntimeError(f"no positions captured from {base_url} careers page")
    return [parse_job(raw, company.name, base_url) for raw in records]
