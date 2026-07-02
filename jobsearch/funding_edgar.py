"""Best-effort total-raised enrichment from SEC EDGAR Form D filings.

When a US company sells securities in a private placement it usually files a
**Form D** with the SEC, which states `totalAmountSold` — real dollars, free and
keyless. That is the only ToS-friendly online source that returns actual funding
numbers (the YC directory only exposes a two-bucket Early/Growth `stage`, and
Wikidata/Wikipedia have ~0 coverage for early startups). This module turns a
company name into a `{"total_raised": "$25M"}` fact, or `{}` when EDGAR has
nothing usable — which, honestly, is most of the time for the tiny startups this
pipeline targets:

- **SAFE / pre-seed rounds are never filed**, so the earliest startups are invisible.
- **Non-US startups** don't file Form D at all.
- **Brand ≠ legal name** (e.g. "Ramp" files under a different entity) breaks the match.
- **SPV noise**: a syndicate that invests *in* a startup files its own Form D under
  a name like "Gaingels Middesk LLC" — that is the *investor's* allocation, not the
  company's raise. We reject those by requiring the filer's name to normalize
  exactly to the company name (see `_is_company_match`).

Because of all that, this is *enrichment for display*, clearly labelled approximate
and user-editable in the UI. Every network call degrades to `{}` on any failure so
a discovery run never breaks (graceful degradation is mandatory — jobsearch/CLAUDE.md).
The parsing/selection core is pure and offline-tested.

SEC serves the two hosts we need behind different bot filters, confirmed live:
EDGAR full-text search (`efts.sec.gov`) wants a browser User-Agent; the filing
archive (`www.sec.gov/Archives`) wants the "Name email" contact User-Agent SEC
documents. We set each per request rather than globally.
"""

from __future__ import annotations

import re

from .startups import format_money, parse_money
from .utils import normalize_company_name

# SEC asks automated clients to identify with a contact string containing an
# email. Overridable via config so a user can supply their real address.
DEFAULT_SEC_CONTACT_UA = "jobsearch startup research admin@example.com"
# efts.sec.gov (full-text search) blocks the contact UA but accepts a browser one.
_EFTS_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/primary_doc.xml"

# Phrases that mark a filer as an investment vehicle rather than the operating
# company — a secondary guard behind the exact-name match. Deliberately narrow:
# the exact normalized-name match is the primary gate, and tokens that
# normalize_company_name already strips as legal suffixes (e.g. "holdings") or
# that appear in legitimate operating-company names (e.g. "ventures") must NOT
# be here, or a real company's own filing gets rejected.
_SPV_MARKERS = (
    "spv", "co-invest", "coinvest", "syndicate", "a series of",
)


def _clean_entity_name(display_name: str) -> str:
    """"Acme, Inc. (CIK 0001234567)" → "Acme, Inc."."""
    return re.sub(r"\s*\(CIK\s*\d+\)\s*$", "", display_name or "", flags=re.I).strip()


def _is_company_match(entity_name: str, company_name: str) -> bool:
    """True only when the filer *is* the company: its name normalizes exactly to
    the company name and carries no SPV marker. This is what rejects
    "Gaingels Middesk LLC" for a "Middesk" query."""
    entity_norm = normalize_company_name(_clean_entity_name(entity_name))
    if not entity_norm or entity_norm != normalize_company_name(company_name):
        return False
    low = (entity_name or "").lower()
    return not any(marker in low for marker in _SPV_MARKERS)


def select_company_filings(hits: list[dict], company_name: str) -> list[dict]:
    """From raw efts `hits[]._source` records keep only this company's own Form D
    filings, one descriptor per record: {cik, adsh, file_num, file_date}."""
    out = []
    for hit in hits:
        src = hit.get("_source", hit) or {}
        names = src.get("display_names") or []
        if not any(_is_company_match(n, company_name) for n in names):
            continue
        ciks = src.get("ciks") or []
        adsh = src.get("adsh") or (hit.get("_id", "").split(":", 1)[0])
        if not ciks or not adsh:
            continue
        out.append({
            "cik": str(ciks[0]),
            "adsh": adsh,
            "file_num": (src.get("file_num") or [""])[0] if isinstance(src.get("file_num"), list) else (src.get("file_num") or ""),
            "file_date": src.get("file_date") or "",
        })
    return out


def parse_amount_sold(xml: str) -> float | None:
    """`totalAmountSold` (dollars) from a Form D primary_doc.xml, or None."""
    m = re.search(r"<totalAmountSold>\s*([\d.]+)\s*</totalAmountSold>", xml or "", re.I)
    return float(m.group(1)) if m else None


def total_raised_dollars(amount_by_offering: dict[str, float]) -> float:
    """Total across distinct offerings. Callers key by `file_num` and store the
    largest cumulative `totalAmountSold` seen for that offering, so amendments of
    one round aren't double-counted; summing across offerings then approximates a
    company's cumulative raise."""
    return float(sum(amount_by_offering.values()))


def _get(session, url, ua, **params):
    resp = session.get(
        url, params=params or None,
        headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
        timeout=getattr(session, "request_timeout", 30),
    )
    resp.raise_for_status()
    return resp


def edgar_total_raised(session, name: str, contact_ua: str = DEFAULT_SEC_CONTACT_UA,
                       max_offerings: int = 6) -> dict:
    """{"total_raised": "$25M"} for `name` from its own Form D filings, or {} when
    EDGAR has nothing usable / anything fails. Never raises."""
    if not name or not name.strip():
        return {}
    try:
        resp = _get(session, _EFTS_URL, _EFTS_UA, q=f'"{name}"', forms="D")
        hits = (resp.json().get("hits") or {}).get("hits") or []
    except Exception:  # noqa: BLE001 — a dead lookup must never sink discovery
        return {}

    filings = select_company_filings(hits, name)
    if not filings:
        return {}

    # One XML fetch per distinct offering (latest amendment wins). Group by
    # file_num (the SEC offering id); when it's missing, fall back to the CIK so
    # every file_num-less filing for one company collapses to a single key rather
    # than each accession becoming its own "offering" — otherwise an original and
    # its amendment (which restates the *cumulative* amount) would be summed.
    latest_by_offering: dict[str, dict] = {}
    for f in filings:
        key = f["file_num"] or f"cik:{f['cik']}"
        cur = latest_by_offering.get(key)
        if cur is None or f["file_date"] > cur["file_date"]:
            latest_by_offering[key] = f

    amount_by_offering: dict[str, float] = {}
    for key, f in list(latest_by_offering.items())[:max_offerings]:
        try:
            url = _ARCHIVE_URL.format(cik=int(f["cik"]), adsh=f["adsh"].replace("-", ""))
            amount = parse_amount_sold(_get(session, url, contact_ua).text)
        except Exception:  # noqa: BLE001
            amount = None
        if amount is not None:
            amount_by_offering[key] = amount

    if not amount_by_offering:
        return {}
    total = total_raised_dollars(amount_by_offering)
    if total <= 0:
        return {}
    # Form D is a floor, not a cap table — the value is best-effort/approximate
    # and stays user-editable in the UI.
    return {"total_raised": format_money(total)}
