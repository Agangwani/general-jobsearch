"""Hacker News "Ask HN: Who is hiring?" — the densest free signal for which
tech companies are actively hiring right now, startups especially.

Found through the public Algolia HN API (keyless): the newest story by the
'whoishiring' bot whose title says "Who is hiring?", then every top-level
comment of that thread. Comments follow a loose convention —

    Company | Role(s) | Location | extras…
    Acme is hiring senior engineers in NYC …

— and very often link the company's own ATS board (Greenhouse/Lever/Ashby)
directly, which makes downstream resolution free: classify the URL instead
of probing name-derived slugs.

Parsing (`parse_comment`, `parse_thread`, `pick_hiring_thread`) is pure and
offline-tested; only `fetch` touches the network.
"""

from __future__ import annotations

import html
import re

from ..http import get_json
from ..models import CompanyLead
from ..utils import strip_html

SEARCH_API = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_API = "https://hn.algolia.com/api/v1/items/{id}"

_HREF_RE = re.compile(r'href="([^"]+)"')
_PAREN_RE = re.compile(r"\s*\([^)]*\)")  # "Mercury (YC S17)" → "Mercury"
_IS_HIRING_RE = re.compile(r"^(?P<name>.{2,60}?)\s+is hiring\b[:\s]*(?P<rest>.*)$", re.I)
SNIPPET_CHARS = 500


def pick_hiring_thread(search_payload: dict) -> int | None:
    """The newest 'Who is hiring?' story id (the bot also posts 'Freelancer?'
    and 'Who wants to be hired?' threads — those are not employer signals)."""
    for hit in search_payload.get("hits") or []:
        if "who is hiring" in (hit.get("title") or "").lower():
            try:
                return int(hit["objectID"])
            except (KeyError, TypeError, ValueError):
                continue
    return None


def _clean_company(raw: str) -> str:
    """Header segment → plausible company name, or '' when it's clearly not
    one (a URL, a sentence, …)."""
    name = _PAREN_RE.sub("", raw).strip(" \t-–—:;,.|")
    if not name or len(name) > 64 or "http" in name.lower():
        return ""
    if len(name.split()) > 8:  # a sentence, not a name
        return ""
    return name


def parse_comment(text_html: str, location_subs: list[str]) -> CompanyLead | None:
    """One top-level thread comment → a lead, or None when no company name
    can be extracted or the posting isn't in a wanted location."""
    if not text_html:
        return None
    plain = strip_html(text_html)
    if location_subs and not any(sub in plain.lower() for sub in location_subs):
        return None
    lines = [line for line in plain.split("\n") if line.strip()]
    if not lines:
        return None
    header = lines[0]

    if "|" in header:
        segments = [seg.strip() for seg in header.split("|")]
        name = _clean_company(segments[0])
        evidence = [seg for seg in segments[1:] if seg]
    else:
        match = _IS_HIRING_RE.match(header)
        if not match:
            return None
        name = _clean_company(match.group("name"))
        evidence = [match.group("rest").strip()] if match.group("rest").strip() else []
    if not name:
        return None

    urls = [html.unescape(u) for u in _HREF_RE.findall(text_html)]
    snippet = "\n".join(lines[1:])[:SNIPPET_CHARS]
    return CompanyLead(
        name=name,
        sources=["hn_hiring"],
        titles=[" | ".join(evidence)] if evidence else [],
        locations=[],
        urls=urls,
        snippets=[snippet] if snippet else [],
    )


def parse_thread(item_payload: dict, location_subs: list[str]) -> list[CompanyLead]:
    """Top-level comments only — replies are questions and chatter."""
    leads = []
    for child in item_payload.get("children") or []:
        lead = parse_comment(child.get("text") or "", location_subs)
        if lead:
            leads.append(lead)
    return leads


def fetch(session, ctx: dict) -> list[CompanyLead]:
    search = get_json(session, SEARCH_API, params={
        "tags": "story,author_whoishiring", "hitsPerPage": 10})
    story_id = pick_hiring_thread(search)
    if story_id is None:
        raise RuntimeError("no 'Who is hiring?' thread found via Algolia")
    item = get_json(session, ITEM_API.format(id=story_id))
    return parse_thread(item, ctx.get("location_subs") or [])
