"""Apple jobs search API (jobs.apple.com).

Apple requires a CSRF token issued on the search page before the JSON API
accepts a POST, so this does a priming GET first. Apple changes this flow
occasionally; failures land in the report's "needs attention" section.
"""

from __future__ import annotations

from ..http import post_json
from ..models import Company, JobPosting
from ..utils import parse_when

SEARCH_PAGE = "https://jobs.apple.com/en-us/search"
API = "https://jobs.apple.com/api/v1/search"


def parse_job(raw: dict, company_name: str) -> JobPosting:
    locations = ", ".join(
        loc.get("name", "") for loc in raw.get("locations") or [] if isinstance(loc, dict)
    )
    slug = raw.get("transformedPostingTitle") or ""
    job_id = str(raw.get("positionId") or raw.get("id", ""))
    return JobPosting(
        company=company_name,
        title=raw.get("postingTitle") or raw.get("title", ""),
        location=locations or "New York City",
        url=f"https://jobs.apple.com/en-us/details/{job_id}/{slug}",
        job_id=job_id,
        description=str(raw.get("jobSummary", "")),
        posted_at=parse_when(raw.get("postingDate") or raw.get("postDateInGMT")),
        source="apple",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    query = settings.get("search", {}).get("query", "senior software engineer")
    prime = session.get(SEARCH_PAGE, params={"location": "new-york-city-NYC"}, timeout=30)
    prime.raise_for_status()
    csrf = prime.headers.get("X-Apple-CSRF-Token", "")

    body = {
        "query": query,
        "filters": {"postLocation": ["postLocation-NYC"]},
        "page": 1,
        "locale": "en-us",
        "sort": "newest",
    }
    headers = {"X-Apple-CSRF-Token": csrf, "Content-Type": "application/json"}
    data = post_json(session, API, json=body, headers=headers)
    results = (data.get("res") or data).get("searchResults", [])
    if not results:
        # Apple NYC always has open roles; an empty result means the API
        # shape/flow changed — raise so the browser fallback takes over.
        raise RuntimeError("Apple search API returned 0 results")
    return [parse_job(raw, company.name) for raw in results]


def fetch_browser(company: Company, runtime, settings: dict) -> list[JobPosting]:
    """Fallback: load the jobs.apple.com search page in Chromium and capture
    its own search XHR — sidesteps the CSRF token dance entirely."""
    from ..utils import walk_collect

    url = f"{SEARCH_PAGE}?location=new-york-city-NYC&sort=newest&search=senior%20software%20engineer"
    payloads = runtime.capture_json(url, r"jobs\.apple\.com/api")
    records = walk_collect(
        payloads, lambda d: ("postingTitle" in d or "transformedPostingTitle" in d) and ("positionId" in d or "id" in d)
    )
    if not records:
        raise RuntimeError("no job records in captured jobs.apple.com responses")
    return [parse_job(raw, company.name) for raw in records]
