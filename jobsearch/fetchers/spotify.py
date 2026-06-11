"""Spotify's lifeatspotify.com job API.

The API exposes neither posting dates nor descriptions in the list view, so
Spotify roles score on title alone and get the configured unknown-age
recency penalty.
"""

from __future__ import annotations

from ..http import get_json
from ..models import Company, JobPosting

API = "https://api-dot-new-spotifyjobs-com.nw.r.appspot.com/wp-json/animal/v1/job/search"


def parse_job(raw: dict, company_name: str) -> JobPosting:
    location = raw.get("location")
    if isinstance(location, dict):
        location = location.get("location", "")
    return JobPosting(
        company=company_name,
        title=raw.get("text") or raw.get("headline", ""),
        location=str(location or "New York"),
        url=f"https://www.lifeatspotify.com/jobs/{raw.get('id', '')}",
        job_id=str(raw.get("id", "")),
        description=str(raw.get("main_category", {}).get("name", "") if isinstance(raw.get("main_category"), dict) else ""),
        posted_at=None,
        source="spotify",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    data = get_json(session, API, params={"l": "new-york", "c": "backend,engineering"})
    results = data.get("result") or []
    return [parse_job(raw, company.name) for raw in results]
