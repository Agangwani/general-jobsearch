"""Remotive aggregator source: a keyless, documented public API of remote jobs.

Complements themuse/hn_hiring/adzuna with a remote-heavy feed — a good fit for
the startup track (startups post remote-heavily) and for the main track when
remote roles are in scope. Remote postings aren't tied to a city, so location
filtering keeps a posting when it matches a configured location substring OR is
explicitly remote/US/worldwide; the run's own role/location gate makes the final
call. Each posting becomes a CompanyLead with title + description evidence and
its posting URL.

Public API (no key): https://remotive.com/api/remote-jobs?search=<query>
Docs: https://remotive.com/api-documentation
"""

from __future__ import annotations

import re

from ..http import get_json
from ..models import CompanyLead
from ..utils import strip_html

API = "https://remotive.com/api/remote-jobs"
SNIPPET_CHARS = 400
# Markers that mean "remote and broadly reachable" — kept regardless of the
# configured city substrings, since a remote role isn't tied to one location.
# Matched on word boundaries so "usa" doesn't match "jerUSAlem" / "saUSAlito".
_REMOTE_MARKERS = ("remote", "worldwide", "anywhere", "usa", "united states",
                   "us only", "north america")
_REMOTE_RE = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in _REMOTE_MARKERS) + r")\b")


def _location_ok(required: str, location_subs: list[str]) -> bool:
    if not location_subs:
        return True
    hay = (required or "").lower()
    # Every Remotive posting is remote; a blank required-location means "remote,
    # anywhere", so keep it rather than dropping it against a city filter.
    if not hay:
        return True
    if _REMOTE_RE.search(hay):
        return True
    return any(sub in hay for sub in location_subs)


def parse_jobs(payload: dict, location_subs: list[str]) -> list[CompanyLead]:
    leads = []
    for job in (payload or {}).get("jobs", []):
        name = (job.get("company_name") or "").strip()
        if not name:
            continue
        required = job.get("candidate_required_location") or ""
        if not _location_ok(required, location_subs):
            continue
        title = job.get("title", "")
        description = job.get("description", "")
        leads.append(CompanyLead(
            name=name,
            sources=["remotive"],
            titles=[title] if title else [],
            locations=[required] if required else [],
            urls=[job["url"]] if job.get("url") else [],
            snippets=[strip_html(description)[:SNIPPET_CHARS]] if description else [],
        ))
    return leads


def fetch(session, ctx: dict) -> list[CompanyLead]:
    # Remotive supports a free-text `search`; the API caps results itself, so no
    # pagination is needed. A failure propagates to the per-source catch.
    query = ctx.get("query") or ""
    params = {"search": query} if query else None
    payload = get_json(session, API, params=params)
    return parse_jobs(payload, ctx.get("location_subs") or [])
