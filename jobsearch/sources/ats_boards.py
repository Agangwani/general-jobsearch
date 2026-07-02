"""ATS board directory source: pull fresh openings straight from companies'
public Applicant Tracking System APIs (Greenhouse, Lever, Ashby).

The aggregators (themuse / hn_hiring / adzuna) surface whoever happens to post to
a job board; this instead reads a seed list of ATS board *tokens* and fetches
each board's current openings directly from its public, no-auth JSON endpoint —
the fastest keyless way to widen the discovered pool. Unlike config/companies.yaml
(which is always fetched, unranked), this seed is a *candidate pool*: every board's
postings become CompanyLeads that ranking scores against the resume, so a large
seed of, say, 200 startup boards is distilled to the best-fitting handful per
resume. Each posting carries the hosted board URL, so ATS resolution is free.

Seed shape — `discovery.ats_boards` / `startups.ats_boards` in config/settings.yaml:

    ats_boards:
      - {ats: greenhouse, token: airbnb, name: Airbnb}
      - {ats: lever, token: ramp}          # name optional (derived from token)
      - {ats: ashby, token: linear}
"""

from __future__ import annotations

from ..http import get_json
from ..models import CompanyLead
from ..utils import strip_html

SNIPPET_CHARS = 400

# Public, no-auth JSON endpoints (same data the careers page renders).
_API = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true",
}
# Human-facing careers URL per token, emitted so resolve_lead classifies it free.
_HOSTED = {
    "greenhouse": "https://job-boards.greenhouse.io/{token}",
    "lever": "https://jobs.lever.co/{token}",
    "ashby": "https://jobs.ashbyhq.com/{token}",
}


def _name_for(seed: dict) -> str:
    """Display name from the seed, or a titlecased token as a fallback."""
    name = (seed.get("name") or "").strip()
    if name:
        return name
    token = str(seed.get("token") or "").replace("-", " ").replace("_", " ")
    return token.title().strip()


def _matches_location(text: str, location_subs: list[str]) -> bool:
    if not location_subs:
        return True
    hay = (text or "").lower()
    return any(sub in hay for sub in location_subs)


def _lead(name: str, title: str, location: str, url: str, board_url: str,
          description: str) -> CompanyLead:
    return CompanyLead(
        name=name,
        sources=["ats_boards"],
        titles=[title] if title else [],
        locations=[location] if location else [],
        # The specific posting URL (if any) plus the board URL — either lets
        # resolve_lead classify the ATS for free.
        urls=[u for u in (url, board_url) if u],
        snippets=[strip_html(description)[:SNIPPET_CHARS]] if description else [],
    )


def parse_greenhouse(payload: dict, name: str, token: str,
                     location_subs: list[str]) -> list[CompanyLead]:
    board_url = _HOSTED["greenhouse"].format(token=token)
    leads = []
    for job in (payload or {}).get("jobs", []):
        location = ((job.get("location") or {}).get("name") or "")
        if not _matches_location(location, location_subs):
            continue
        leads.append(_lead(name, job.get("title", ""), location,
                           job.get("absolute_url", ""), board_url,
                           job.get("content", "")))
    return leads


def parse_lever(payload: list, name: str, token: str,
                location_subs: list[str]) -> list[CompanyLead]:
    board_url = _HOSTED["lever"].format(token=token)
    leads = []
    for job in payload or []:
        cats = job.get("categories") or {}
        location = cats.get("location") or ""
        if not _matches_location(location, location_subs):
            continue
        leads.append(_lead(name, job.get("text", ""), location,
                           job.get("hostedUrl", ""), board_url,
                           job.get("descriptionPlain") or job.get("description", "")))
    return leads


def parse_ashby(payload: dict, name: str, token: str,
                location_subs: list[str]) -> list[CompanyLead]:
    board_url = _HOSTED["ashby"].format(token=token)
    # Ashby carries the real org name on the payload; prefer it over the seed.
    org_name = (payload or {}).get("name") or (payload or {}).get("organizationName") or name
    leads = []
    for job in (payload or {}).get("jobs", []):
        location = job.get("location") or ""
        if not _matches_location(location, location_subs):
            continue
        leads.append(_lead(org_name, job.get("title", ""), location,
                           job.get("jobUrl") or job.get("applyUrl", ""), board_url,
                           job.get("descriptionPlain") or job.get("descriptionHtml", "")))
    return leads


_PARSERS = {"greenhouse": parse_greenhouse, "lever": parse_lever, "ashby": parse_ashby}


def fetch(session, ctx: dict) -> list[CompanyLead]:
    """Fetch every seeded ATS board's current openings. A board that errors (dead
    token, transient 5xx) is skipped so one bad board never sinks the source;
    the shared session's Retry handles 429/5xx backoff."""
    seeds = ctx.get("ats_boards") or []
    location_subs = ctx.get("location_subs") or []
    leads: list[CompanyLead] = []
    for seed in seeds:
        ats = str(seed.get("ats") or "").lower()
        token = str(seed.get("token") or "").strip()
        parser = _PARSERS.get(ats)
        if not (parser and token):
            continue
        try:
            payload = get_json(session, _API[ats].format(token=token))
        except Exception:  # noqa: BLE001 - a dead board must not sink the source
            continue
        leads.extend(parser(payload, _name_for(seed), token, location_subs))
    return leads
