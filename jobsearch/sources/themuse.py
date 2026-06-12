"""The Muse public jobs API — free, keyless, documented, strong NYC coverage.

GET https://www.themuse.com/api/public/jobs?category=…&location=…&page=N
returns 20 postings per page with the employer name, role title, locations,
and an HTML description — exactly the evidence a CompanyLead needs. Category
names are Muse-specific ("Software Engineering", "Data Science", …), so
company_discovery infers them from the resume (infer_categories) instead of
hard-coding engineering; `discovery.categories` in settings.yaml overrides.

Parsing is pure (`parse_jobs`) and offline-tested.
"""

from __future__ import annotations

from ..http import get_json
from ..models import CompanyLead
from ..utils import strip_html

API = "https://www.themuse.com/api/public/jobs"
PAGE_SIZE = 20  # fixed by the API
SNIPPET_CHARS = 400


def parse_jobs(payload: dict, location_subs: list[str]) -> list[CompanyLead]:
    """One lead per posting whose location matches (merged downstream)."""
    leads = []
    for job in payload.get("results") or []:
        company = ((job.get("company") or {}).get("name") or "").strip()
        if not company:
            continue
        locations = [(loc.get("name") or "") for loc in (job.get("locations") or [])]
        if location_subs and not any(
                sub in loc.lower() for loc in locations for sub in location_subs):
            continue
        snippet = strip_html(job.get("contents") or "")[:SNIPPET_CHARS]
        title = (job.get("name") or "").strip()
        leads.append(CompanyLead(
            name=company,
            sources=["themuse"],
            titles=[title] if title else [],
            locations=[loc for loc in locations if loc],
            snippets=[snippet] if snippet else [],
        ))
    return leads


def fetch(session, ctx: dict) -> list[CompanyLead]:
    leads: list[CompanyLead] = []
    for category in ctx.get("categories") or ["Software Engineering"]:
        page = 1
        while page <= ctx.get("max_pages", 8):
            payload = get_json(session, API, params={
                "page": page,
                "category": category,
                "location": ctx.get("location", "New York, NY"),
            })
            leads.extend(parse_jobs(payload, ctx.get("location_subs") or []))
            if page >= int(payload.get("page_count") or 1):
                break
            page += 1
    return leads
