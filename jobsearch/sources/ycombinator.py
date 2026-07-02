"""Y Combinator company directory — the startup universe.

The other sources answer "who posted a job this month?"; this one answers
"which startups exist in this city?", which is what the startup pipeline needs
to "search through all startup companies." It reads the community-maintained,
keyless YC OSS API (a static JSON mirror of YC's public company directory,
https://github.com/yc-oss/api) — documented and public, the same ToS-friendly
bar as The Muse and the HN source.

Each YC record carries exactly the startup facts we want to track (team size,
batch, status, stage, industry, location, website, descriptions), so this
source fills `CompanyLead.meta` (see jobsearch/startups.py) on top of the usual
resume-ranking evidence. Companies are filtered to the configured city and, by
default, to active companies that are hiring.

`parse_companies` is pure and offline-tested; only `fetch` touches the network.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..http import get_json
from ..models import CompanyLead
from ..startups import StartupMeta, extract_funding, extract_people

# The OSS mirror ships pre-filtered slices; `hiring.json` is companies marked
# currently hiring, `all.json` is the whole directory. We pick per ctx.
API_BASE = "https://yc-oss.github.io/api/companies"
SNIPPET_CHARS = 600


def _founded_year(record: dict) -> str:
    ts = record.get("launched_at")
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return str(datetime.fromtimestamp(ts, tz=timezone.utc).year)
        except (ValueError, OverflowError, OSError):
            return ""
    return ""


def _location_matches(record: dict, location_subs: list[str]) -> bool:
    if not location_subs:
        return True
    hay = " ".join([
        str(record.get("all_locations") or ""),
        " ".join(record.get("regions") or []),
    ]).lower()
    return any(sub in hay for sub in location_subs)


def _meta_for(record: dict) -> dict:
    """Build the StartupMeta dict for one YC record, enriching the coarse YC
    `stage` with anything the description's free text reveals (round size,
    extra investors, notable founders)."""
    description = (record.get("long_description") or "").strip()
    one_liner = (record.get("one_liner") or "").strip()
    team = record.get("team_size")
    meta = StartupMeta(
        name=(record.get("name") or "").strip(),
        employees="" if team in (None, 0, "") else str(team),
        founded=_founded_year(record),
        batch=(record.get("batch") or "").strip(),
        status=(record.get("status") or "").strip(),
        stage=(record.get("stage") or "").strip(),
        industry=(record.get("industry") or "").strip(),
        tags=list(record.get("tags") or []),
        location=(record.get("all_locations") or "").strip(),
        website=(record.get("website") or "").strip(),
        one_liner=one_liner,
        description=description[:1200],
        top_company=bool(record.get("top_company")),
        is_hiring=bool(record.get("isHiring")),
        yc_url=(record.get("url") or "").strip(),
        investors=["Y Combinator"],  # YC-backed by definition; seed the list
        source="ycombinator",
    ).to_dict()

    # Coarse YC stage → our last_round when it names a round; mine the prose for
    # amounts / extra investors / founders the structured fields don't carry.
    blurb = "\n".join([one_liner, description])
    funding = extract_funding(blurb)
    for key, value in funding.items():
        if key == "investors":
            for inv in value:
                if inv not in meta["investors"]:
                    meta["investors"].append(inv)
        elif not meta.get(key):
            meta[key] = value
    if not meta.get("last_round") and meta.get("stage"):
        meta["last_round"] = meta["stage"]
    people = extract_people(blurb)
    if people:
        meta["notable_people"] = people
    return meta


def parse_companies(
    records: list[dict], location_subs: list[str], require_hiring: bool = False,
    statuses: list[str] | None = None,
) -> list[CompanyLead]:
    """YC records → leads in the wanted city. Evidence (one-liner + description
    + industry/tags) is what resume-ranking scores; meta carries the facts the
    UI tracks. `statuses` (lowercased) filters by company status when given."""
    statuses = [s.lower() for s in statuses] if statuses else None
    leads = []
    for record in records:
        name = (record.get("name") or "").strip()
        if not name:
            continue
        if require_hiring and not record.get("isHiring"):
            continue
        if statuses and (record.get("status") or "").lower() not in statuses:
            continue
        if not _location_matches(record, location_subs):
            continue
        meta = _meta_for(record)
        evidence = [meta["one_liner"], meta["description"]]
        if meta["industry"]:
            evidence.append(meta["industry"])
        if meta["tags"]:
            evidence.append(" ".join(meta["tags"]))
        snippet = "\n".join(e for e in evidence if e)[:SNIPPET_CHARS]
        leads.append(CompanyLead(
            name=name,
            sources=["ycombinator"],
            titles=[meta["one_liner"]] if meta["one_liner"] else [],
            locations=[meta["location"]] if meta["location"] else [],
            urls=[meta["website"]] if meta["website"] else [],
            snippets=[snippet] if snippet else [],
            meta=meta,
        ))
    return leads


def fetch(session, ctx: dict) -> list[CompanyLead]:
    yc = ctx.get("ycombinator") or {}
    # Default to the "hiring" slice (smaller, and the startup pipeline wants
    # companies with open roles); the whole directory is opt-in via slice: all.
    slice_name = yc.get("slice", "hiring")
    payload = get_json(session, f"{API_BASE}/{slice_name}.json")
    records = payload if isinstance(payload, list) else payload.get("companies") or []
    return parse_companies(
        records,
        ctx.get("location_subs") or [],
        require_hiring=bool(yc.get("require_hiring", False)),
        statuses=yc.get("statuses") or ["active"],
    )
