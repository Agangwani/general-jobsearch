"""Greenhouse public board API.

Greenhouse runs two board systems:
- Legacy (boards.greenhouse.io):    boards-api.greenhouse.io/v1/boards/{slug}/jobs
- Next-gen (job-boards.greenhouse.io): same API endpoint, same slug

If the primary API returns 404 the board slug is stale — update it in companies.yaml.
"""

from __future__ import annotations

import requests

from ..http import get_json
from ..models import Company, JobPosting
from ..utils import parse_when, strip_html

_API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


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
    try:
        data = get_json(session, _API.format(board=board))
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise RuntimeError(
                f"greenhouse board '{board}' not found (404) — "
                "slug may be stale or the board migrated; update companies.yaml"
            ) from exc
        raise
    limit = settings.get("fetch", {}).get("max_per_company", 1500)
    jobs = [parse_job(raw, company.name) for raw in data.get("jobs", [])[:limit]]
    if not jobs:
        raise RuntimeError(f"greenhouse board '{board}' returned 0 postings — slug may be stale")
    return jobs
