"""Company-specific LeetCode question registry.

Online, every big company is known for asking a recognisable *set* of
LeetCode problems (LeetCode's own "company tags", plus community datasets
that aggregate which questions each company asks most). This package tracks
that per-company set so the UI can answer "what does Amazon actually ask?"
next to the Amazon jobs you're applying to.

Two layers, mirroring the rest of the project (ship data, work offline,
refresh pulls live):

- ``COMPANY_QUESTIONS`` — a curated, bundled dataset of the most commonly
  asked problems at the major employers in ``config/companies.yaml``. It is
  seeded into the ``company_problems`` table on every UI start (idempotent),
  so the feature works with **no network**.
- ``refresh`` — pulls an updated, larger list from a configurable community
  "company-wise LeetCode" dataset (CSV per company). Network-optional: a
  failed refresh surfaces an actionable note and leaves the bundled data in
  place, exactly like a broken job board never sinks a pipeline run.

Solve/attempt progress lives in ``company_problem_progress`` and is keyed by
the row id, so re-seeding or refreshing content never wipes how far you got.
"""

from __future__ import annotations

from jobsearch.utils import normalize_company_name

from .seed_data import COMPANY_QUESTIONS

# Some employers are known under more than one name across boards and in the
# community datasets. Map the alternates onto a single canonical key so a
# "Facebook" job finds the "Meta" question set and vice-versa.
COMPANY_ALIASES = {
    "facebook": "meta",
    "meta platforms": "meta",
    "google llc": "google",
    "alphabet": "google",
    "amazon web services": "amazon",
    "aws": "amazon",
    "amazon com": "amazon",
    "microsoft": "microsoft",
    "goldman": "goldman sachs",
    "goldman sachs group": "goldman sachs",
    "jpmorgan": "jpmorgan chase",
    "jp morgan": "jpmorgan chase",
    "jpmorgan chase": "jpmorgan chase",
}


def canonical_key(name: str) -> str:
    """Normalize a company name to the key used in ``company_problems`` —
    legal suffixes dropped (via :func:`normalize_company_name`) and known
    aliases folded onto one canonical employer."""
    key = normalize_company_name(name)
    return COMPANY_ALIASES.get(key, key)


def leetcode_url(slug: str) -> str:
    return f"https://leetcode.com/problems/{slug}/"


def bundled_records() -> list[dict]:
    """Flatten ``COMPANY_QUESTIONS`` into upsert-ready rows.

    Frequency is *relative* (derived from each list's hand-ranked order, most
    common first) since the bundled set has no measured percentages; a refresh
    overwrites it with the dataset's real numbers when available.
    """
    records: list[dict] = []
    for company, problems in COMPANY_QUESTIONS.items():
        key = canonical_key(company)
        n = len(problems)
        for i, p in enumerate(problems):
            # Spread relative frequency from ~99 down to ~40 across the list so
            # the most-asked rises to the top and the bar widths stay readable.
            freq = round(99 - (i * 59 / max(n - 1, 1)), 1) if n > 1 else 90.0
            records.append({
                "company": company,
                "company_key": key,
                "leetcode_number": p.get("n"),
                "leetcode_slug": p["slug"],
                "title": p["title"],
                "difficulty": p.get("diff", "medium"),
                "frequency": freq,
                "timeframe": "curated",
                "topics": p.get("topics", ""),
                "url": leetcode_url(p["slug"]),
                "source": "bundled",
            })
    return records


__all__ = [
    "COMPANY_QUESTIONS",
    "COMPANY_ALIASES",
    "canonical_key",
    "leetcode_url",
    "bundled_records",
]
