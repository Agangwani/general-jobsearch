"""Adzuna search API — the broadest employer coverage of the three sources
(aggregates enterprise boards that never post on HN), but it needs a free
API key: register at https://developer.adzuna.com and export ADZUNA_APP_ID
and ADZUNA_APP_KEY. Without them the source raises SourceSkip and the
discovery run carries on with the keyless sources.

The `what`/`where` parameters come straight from settings (`search.query`,
`discovery.location`), so the same code serves a data scientist in NYC and
a designer in Austin. Parsing is pure (`parse_jobs`) and offline-tested.
"""

from __future__ import annotations

import os

from . import SourceSkip
from ..http import get_json
from ..models import CompanyLead
from ..utils import strip_html

API = "https://api.adzuna.com/v1/api/jobs/us/search/{page}"
PAGE_SIZE = 50
SNIPPET_CHARS = 400


def parse_jobs(payload: dict, location_subs: list[str]) -> list[CompanyLead]:
    leads = []
    for job in payload.get("results") or []:
        company = ((job.get("company") or {}).get("display_name") or "").strip()
        if not company:
            continue
        location = (job.get("location") or {}).get("display_name") or ""
        if location_subs and not any(sub in location.lower() for sub in location_subs):
            continue
        snippet = strip_html(job.get("description") or "")[:SNIPPET_CHARS]
        title = (job.get("title") or "").strip()
        # redirect_url points at Adzuna's tracker, not the employer — useless
        # for ATS resolution, so no urls evidence from this source.
        leads.append(CompanyLead(
            name=company,
            sources=["adzuna"],
            titles=[title] if title else [],
            locations=[location] if location else [],
            snippets=[snippet] if snippet else [],
        ))
    return leads


def fetch(session, ctx: dict) -> list[CompanyLead]:
    app_id = os.environ.get("ADZUNA_APP_ID", "")
    app_key = os.environ.get("ADZUNA_APP_KEY", "")
    if not (app_id and app_key):
        raise SourceSkip(
            "ADZUNA_APP_ID / ADZUNA_APP_KEY not set (free key: developer.adzuna.com)")
    leads: list[CompanyLead] = []
    for page in range(1, ctx.get("max_pages", 8) + 1):
        payload = get_json(session, API.format(page=page), params={
            "app_id": app_id,
            "app_key": app_key,
            "what": ctx.get("query", ""),
            "where": ctx.get("location", "New York, NY"),
            "results_per_page": PAGE_SIZE,
        })
        results = payload.get("results") or []
        leads.extend(parse_jobs(payload, ctx.get("location_subs") or []))
        if len(results) < PAGE_SIZE:
            break
    return leads
