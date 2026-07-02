"""Startup company metadata: the canonical shape plus best-effort extraction.

The startup pipeline tracks more than "who is hiring" — for each startup it
keeps the *helpful* facts you weigh when deciding whether to apply: team size,
funding stage and amount, who's backing them, notable people, industry, and so
on. This module defines that record (`StartupMeta`) and the free, ToS-friendly
ways we populate it:

- **Structured fields** come straight from the Y Combinator directory
  (`sources/ycombinator.py`): team_size → employees, batch, status, stage,
  industry, founded year, website. Every YC company is, by definition,
  Y Combinator-backed, so YC seeds the investor list.
- **Funding signals** that no free *structured* API exposes (round size, lead
  investors, notable hires) are mined heuristically from the free text we
  already have — HN "Who is hiring?" blurbs and YC descriptions routinely say
  "Series A, $20M, backed by a16z and Sequoia". `extract_funding` /
  `extract_people` do that with conservative regexes.

Anything still unknown is left blank and is **user-editable** in the UI: the
honest position is that precise, current cap-table data needs a paid source
(Crunchbase/PitchBook) or manual entry, and the schema is built to hold it
either way. Every function here is pure and offline-tested.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# The metadata fields the UI shows and lets you edit. Stored per company
# (keyed by normalized name) in data/startup_meta.json and the startup_companies
# DB table. Lists are kept as lists here and JSON-encoded at the DB boundary.


@dataclass
class StartupMeta:
    name: str = ""
    employees: str = ""           # team size, e.g. "120" or "51-200"
    founded: str = ""             # year founded, e.g. "2019"
    batch: str = ""               # YC batch, e.g. "W21" (blank for non-YC)
    status: str = ""              # Active | Acquired | Public | Inactive
    stage: str = ""               # Seed | Series A | Growth | …
    last_round: str = ""          # most recent round described, e.g. "Series B"
    last_round_amount: str = ""   # e.g. "$25M"
    total_raised: str = ""        # e.g. "$60M"
    investors: list[str] = field(default_factory=list)   # notable VCs / backers
    notable_people: list[str] = field(default_factory=list)  # founders / leaders
    industry: str = ""
    tags: list[str] = field(default_factory=list)
    location: str = ""
    website: str = ""
    one_liner: str = ""
    description: str = ""
    top_company: bool = False     # YC "top company" flag
    is_hiring: bool = False
    yc_url: str = ""
    source: str = ""              # ycombinator | hn_hiring | manual | …
    notes: str = ""               # free-form, user-editable

    def to_dict(self) -> dict:
        return asdict(self)


# Fields a user edit / richer source may overwrite; lists are unioned.
_SCALAR_FIELDS = (
    "employees", "founded", "batch", "status", "stage", "last_round",
    "last_round_amount", "total_raised", "industry", "location", "website",
    "one_liner", "description", "yc_url", "source", "notes",
)
_LIST_FIELDS = ("investors", "tags", "notable_people")


def merge_meta(base: dict, extra: dict) -> dict:
    """Combine two metadata dicts: `base` wins on scalar conflicts (it's the
    earlier/curated one), missing scalars are filled from `extra`, and list
    fields are unioned preserving order. Used to fold multiple sources'
    evidence for the same company into one record."""
    out = dict(base or {})
    extra = extra or {}
    for key in _SCALAR_FIELDS:
        if not out.get(key) and extra.get(key):
            out[key] = extra[key]
    for key in _LIST_FIELDS:
        merged = list(out.get(key) or [])
        seen = {v.lower() for v in merged if isinstance(v, str)}
        for value in extra.get(key) or []:
            if isinstance(value, str) and value.lower() not in seen:
                merged.append(value)
                seen.add(value.lower())
        if merged:
            out[key] = merged
    for key in ("top_company", "is_hiring"):
        out[key] = bool(out.get(key)) or bool(extra.get(key))
    if not out.get("name"):
        out["name"] = extra.get("name", "")
    return out


# ------------------------------------------------------------- headcount ---
_COUNT_RE = re.compile(r"\d[\d,]*")


def parse_employee_count(value) -> int | None:
    """Best-effort upper bound of a team-size string → int, or None if unknown.

    Handles the shapes we see in metadata: "120", "51-200" (→200), "10,000+"
    (→10000), "1001-5000 employees". Returns None when there's no number to
    read (e.g. themuse leads, which carry no size), so unknown-size companies
    are never dropped by a size guard — only companies with a *known* large
    headcount are."""
    if value is None:
        return None
    counts = [int(m.group().replace(",", "")) for m in _COUNT_RE.finditer(str(value))]
    return max(counts) if counts else None


# ------------------------------------------------------------ money parse ---
_MONEY_MULT = {
    "k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
}
_MONEY_RE = re.compile(
    r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(thousand|million|billion|mm|bn|k|m|b)?\b",
    re.I,
)


def parse_money(value) -> float | None:
    """Best-effort dollar amount of a money string → float, or None if unknown.

    Handles the shapes we store/mine: "$25M"→25e6, "$1.5 billion"→1.5e9,
    "$750k"→750e3, "$3,000,000"→3e6, normalized "1.5B"→1.5e9, and a bare
    integer like "211967"→211967 (SEC Form D dollars). Mirrors
    parse_employee_count's None-means-unknown contract so an unrecorded raise
    never trips a funding guard."""
    if value is None:
        return None
    m = _MONEY_RE.search(str(value))
    if not m:
        return None
    return float(m.group(1).replace(",", "")) * _MONEY_MULT.get((m.group(2) or "").lower(), 1.0)


def format_money(dollars: float) -> str:
    """A round dollar amount → a compact display string ("$212K", "$25M",
    "$200M", "$1.5B") matching the style extract_funding already produces.
    One decimal place, trailing ".0" trimmed — never scientific notation."""
    if dollars >= 1e9:
        value, unit = dollars / 1e9, "B"
    elif dollars >= 1e6:
        value, unit = dollars / 1e6, "M"
    elif dollars >= 1e3:
        return f"${round(dollars / 1e3)}K"
    else:
        return f"${round(dollars)}"
    return f"${f'{value:.1f}'.rstrip('0').rstrip('.')}{unit}"


# --------------------------------------------------------------- funding ---
# A curated list of well-known investors so "backed by a16z / Sequoia" in a
# free-text blurb resolves to clean names. Not exhaustive — it's a signal, not
# a cap table. Order matters only for display.
KNOWN_INVESTORS = [
    "Y Combinator", "Andreessen Horowitz", "a16z", "Sequoia", "Accel",
    "Founders Fund", "Greylock", "Benchmark", "Index Ventures", "Lightspeed",
    "Khosla Ventures", "Bessemer", "General Catalyst", "Tiger Global",
    "Insight Partners", "Kleiner Perkins", "GV", "Google Ventures",
    "Coatue", "Thrive Capital", "Bain Capital", "NEA", "Battery Ventures",
    "First Round", "Initialized", "SV Angel", "Craft Ventures", "8VC",
    "Spark Capital", "Redpoint", "Menlo Ventures", "GGV Capital",
    "Norwest", "ICONIQ", "DST Global", "SoftBank", "Ribbit Capital",
    "Union Square Ventures", "USV", "Felicis", "Lux Capital",
]

_STAGE_RE = re.compile(
    r"\b(pre[-\s]?seed|seed|series\s+[a-k]|growth\s+stage|growth|late[-\s]stage)\b",
    re.I,
)
# "$20M", "$1.5 billion", "$750k", "$3,000,000"
_AMOUNT_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:k|m|bn?|thousand|million|billion)?\b",
    re.I,
)
_RAISED_RE = re.compile(
    r"(?:raised|closed|secured|announced)\s+(?:a\s+)?"
    r"(?:\$\s?\d[\d,]*(?:\.\d+)?\s*(?:k|m|bn?|thousand|million|billion)?)",
    re.I,
)
_BACKED_RE = re.compile(
    r"(?:backed by|investors?(?:\s+include)?|funded by|raised from)\s*:?\s*(.+?)"
    r"(?:[.\n]|$)",
    re.I,
)


def _norm_stage(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw.strip()).title()
    s = s.replace("Pre Seed", "Pre-Seed").replace("Pre-Seed", "Pre-Seed")
    return re.sub(r"Series ([a-k])", lambda m: "Series " + m.group(1).upper(), s, flags=re.I)


def find_investors(text: str) -> list[str]:
    """Known investor names mentioned anywhere in the text (case-insensitive),
    de-duplicated, in the order they appear in KNOWN_INVESTORS."""
    if not text:
        return []
    low = text.lower()
    found = []
    for name in KNOWN_INVESTORS:
        if re.search(r"\b" + re.escape(name.lower()) + r"\b", low):
            # collapse the a16z/Andreessen and GV/Google Ventures aliases
            canonical = {"a16z": "Andreessen Horowitz",
                         "google ventures": "GV", "usv": "Union Square Ventures"}.get(
                name.lower(), name)
            if canonical not in found:
                found.append(canonical)
    return found


def extract_funding(text: str) -> dict:
    """Best-effort funding facts from a free-text blurb. Returns only the keys
    it's confident about (stage / last_round_amount / investors), so callers can
    merge it without clobbering structured data with blanks."""
    out: dict = {}
    if not text:
        return out
    stage = _STAGE_RE.search(text)
    if stage:
        out["stage"] = _norm_stage(stage.group(1))
        out["last_round"] = out["stage"]
    # Prefer an amount adjacent to "raised/closed/…"; otherwise, when there's a
    # funding signal at all (a stage or a raised-phrase), take the first dollar
    # figure in the blurb. Best-effort by design — clearly labeled in the UI.
    raised = _RAISED_RE.search(text)
    amount = _AMOUNT_RE.search(raised.group(0)) if raised else None
    if not amount and (out.get("stage") or raised):
        amount = _AMOUNT_RE.search(text)
    if amount:
        out["last_round_amount"] = _norm_amount(amount.group(0))
    investors = find_investors(text)
    if investors:
        out["investors"] = investors
    return out


def _norm_amount(raw: str) -> str:
    s = re.sub(r"\s+", "", raw.strip())
    s = s.replace("million", "M").replace("Million", "M")
    s = s.replace("billion", "B").replace("Billion", "B")
    s = s.replace("thousand", "K").replace("Thousand", "K")
    return s.upper().replace("BN", "B")


_FOUNDED_BY_RE = re.compile(
    r"founded by\s+(.+?)(?:[.\n,;]|\s+(?:in|who|after|and is|—|-)\s|$)", re.I)
_EX_RE = re.compile(r"\bex[-\s](?:[A-Z][\w.&]+)(?:\s*/\s*[A-Z][\w.&]+)*", re.I)


def extract_people(text: str) -> list[str]:
    """Notable people / leadership hints from a blurb: a 'founded by …' clause
    and 'ex-BigCo' pedigree markers. Conservative — meant as a starting point
    you can correct in the UI, not authoritative."""
    if not text:
        return []
    people: list[str] = []
    m = _FOUNDED_BY_RE.search(text)
    if m:
        clause = m.group(1).strip()
        if 0 < len(clause) <= 80:
            people.append("Founded by " + clause)
    for ex in _EX_RE.findall(text):
        tag = ex.strip()
        if tag and tag not in people:
            people.append(tag)
    return people[:6]
