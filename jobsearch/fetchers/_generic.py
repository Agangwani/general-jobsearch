"""Last-resort job-record extraction for browser-harvested pages.

Site fetchers parse with their precise key maps first; when that yields
nothing (the board changed its response shape, or the XHR pattern missed the
real endpoint) they fall back to this module over *everything* the harvest
brought back: pattern-matched XHRs, every other JSON response, and JSON
embedded in the DOM.

Two passes, highest precision first:
1. schema.org JSON-LD ``JobPosting`` objects — standardized fields, embedded
   by most career sites for Google-for-Jobs SEO.
2. Duck-typed records: any dict with a plausible title string, an id, and
   location/url evidence. The downstream title/location filters cut whatever
   noise slips through.
"""

from __future__ import annotations

from ..models import JobPosting
from ..utils import first, parse_when, strip_html, walk_collect

TITLE_KEYS = ("title", "jobTitle", "JobTitle", "job_title", "postingTitle",
              "positionTitle", "roleTitle", "name")
ID_KEYS = ("jobId", "JobsId", "job_id", "jobSeqNo", "reqId", "requisitionId",
           "positionId", "jobPostingId", "id")
LOCATION_KEYS = ("location", "locations", "cityStateCountry", "cityState",
                 "city", "primaryLocation", "jobLocation")
URL_KEYS = ("applyUrl", "apply_url", "canonicalPositionUrl", "externalPath",
            "jobUrl", "url")
DATE_KEYS = ("postedDate", "postingDate", "datePosted", "postDate",
             "publish_date", "publishDate", "dateCreated", "t_create")
DESC_KEYS = ("description", "jobDescription", "descriptionTeaser",
             "jobSummary", "summary", "job_description")


def _location_text(value) -> str:
    """Normalize the location shapes boards use: str, list of str/dict, or a
    dict with a name/display/city field (incl. JSON-LD address nesting)."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(filter(None, (_location_text(v) for v in value)))
    if isinstance(value, dict):
        address = value.get("address")
        if isinstance(address, dict):
            return ", ".join(filter(None, (
                address.get("addressLocality", ""), address.get("addressRegion", ""))))
        return str(first(value, ("name", "display", "city", "label", "value"), ""))
    return str(value) if value is not None else ""


def looks_like_job(record: dict) -> bool:
    title = first(record, TITLE_KEYS, None)
    if not isinstance(title, str) or not 4 <= len(title.strip()) <= 150:
        return False
    if first(record, ID_KEYS, None) in (None, ""):
        return False
    has_location = first(record, LOCATION_KEYS, None) not in (None, "", [], {})
    has_url = isinstance(first(record, URL_KEYS, None), str)
    return has_location or has_url


def _is_jsonld_posting(record: dict) -> bool:
    kind = record.get("@type")
    if isinstance(kind, list):
        return "JobPosting" in kind
    return kind == "JobPosting"


def _to_posting(record: dict, company_name: str, source: str, link_fmt: str) -> JobPosting:
    job_id = str(first(record, ID_KEYS) or first(record, URL_KEYS)
                 or first(record, TITLE_KEYS))
    url = first(record, URL_KEYS, "")
    if not isinstance(url, str) or not url.startswith("http"):
        url = link_fmt.format(id=job_id) if link_fmt else str(url)
    return JobPosting(
        company=company_name,
        title=str(first(record, TITLE_KEYS)).strip(),
        location=_location_text(first(record, LOCATION_KEYS, "")),
        url=url,
        job_id=job_id,
        description=strip_html(str(first(record, DESC_KEYS, ""))),
        posted_at=parse_when(first(record, DATE_KEYS, None)),
        source=source,
    )


def debug_summary(harvest: dict) -> str:
    """One line describing what the harvest actually saw — embedded in the
    'no records' error so the daily report's needs-attention section carries
    enough signal to fix the board without a debugging session."""
    debug = harvest.get("debug") or {}
    urls = debug.get("response_urls") or []
    sample = ", ".join(urls[:8])
    return (f"final URL: {debug.get('final_url', '?')}; "
            f"{len(harvest.get('matched', []))} matched + "
            f"{len(harvest.get('extra', []))} other JSON responses, "
            f"{len(harvest.get('embedded', []))} embedded blobs; "
            f"URLs seen: {sample or 'none'}")


def fallback_jobs(harvest: dict, company_name: str, source: str,
                  link_fmt: str = "") -> list[JobPosting]:
    """Extract postings from a BrowserRuntime.harvest() result. `link_fmt`
    (e.g. "https://higher.gs.com/roles/{id}") builds an apply URL when the
    record carries none."""
    payloads = (harvest.get("matched", []) + harvest.get("embedded", [])
                + harvest.get("extra", []))
    jobs: list[JobPosting] = []
    seen: set[str] = set()

    def add(record: dict) -> None:
        posting = _to_posting(record, company_name, source, link_fmt)
        key = posting.url or posting.job_id
        if posting.title and key not in seen:
            seen.add(key)
            jobs.append(posting)

    for record in walk_collect(payloads, _is_jsonld_posting):
        add(record)
    for record in walk_collect(payloads, looks_like_job):
        add(record)
    return jobs
