"""Meta careers GraphQL endpoint (www.metacareers.com).

Meta has no documented public API; this uses the same GraphQL document the
careers site itself calls. The doc_id rotates occasionally — when it breaks,
the run reports it under "needs attention" and the careers_url is the
fallback.
"""

from __future__ import annotations

import json

from ..models import Company, JobPosting

GRAPHQL = "https://www.metacareers.com/graphql"
DOC_ID = "9114524511922157"


def parse_job(raw: dict, company_name: str) -> JobPosting:
    locations = raw.get("locations") or []
    return JobPosting(
        company=company_name,
        title=raw.get("title", ""),
        location=", ".join(locations) if isinstance(locations, list) else str(locations),
        url=f"https://www.metacareers.com/jobs/{raw.get('id', '')}",
        job_id=str(raw.get("id", "")),
        description=" ".join(str(raw.get(k, "")) for k in ("teams", "sub_teams") if raw.get(k)),
        posted_at=None,  # Meta does not expose posting dates
        source="meta",
    )


def fetch(company: Company, session, settings: dict) -> list[JobPosting]:
    query = settings.get("search", {}).get("query", "senior software engineer")
    variables = {
        "search_input": {
            "q": query,
            "offices": ["New York, NY"],
            "results_per_page": 100,
        }
    }
    payload = {
        "doc_id": DOC_ID,
        "variables": json.dumps(variables),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded", "X-FB-Friendly-Name": "CareersJobSearchResultsQuery"}
    resp = session.post(GRAPHQL, data=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    text = resp.text
    if text.startswith("for (;;);"):
        text = text[len("for (;;);"):]
    data = json.loads(text)
    results = (
        (data.get("data") or {}).get("job_search_with_featured_jobs", {}).get("all_jobs")
        or (data.get("data") or {}).get("job_search")
        or []
    )
    if not results:
        raise RuntimeError("Meta GraphQL returned no job_search results (doc_id may have rotated)")
    return [parse_job(raw, company.name) for raw in results]


def fetch_browser(company: Company, runtime, settings: dict) -> list[JobPosting]:
    """Fallback: load metacareers.com search in Chromium and capture the
    GraphQL XHR the page itself issues — sidesteps the rotating doc_id."""
    from ..utils import walk_collect

    url = "https://www.metacareers.com/jobs?offices[0]=New%20York%2C%20NY&q=software%20engineer"
    payloads = runtime.capture_json(url, r"metacareers\.com/graphql")
    records = walk_collect(
        payloads, lambda d: "title" in d and "id" in d and ("locations" in d or "teams" in d)
    )
    if not records:
        raise RuntimeError("no job records in captured metacareers.com GraphQL responses")
    return [parse_job(raw, company.name) for raw in records]
