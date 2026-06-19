"""Pull an updated, frequency-measured company → LeetCode list from a
community "company-wise" dataset.

This is the "⟳ Refresh questions / pull a new list" half of the feature. The
community datasets publish one CSV per company (e.g.
``amazon_alltime.csv``) with columns for the problem title, difficulty,
frequency and a LeetCode link. We:

1. Try a handful of filename spellings for the company (datasets disagree on
   ``goldman-sachs`` vs ``goldman_sachs`` vs ``goldmansachs``).
2. Parse the CSV *tolerantly* — column names differ between datasets, so we
   match by header keyword (title / difficulty / frequency / link / id)
   rather than a fixed schema.
3. Return normalized rows ready for ``upsert_company_problem``.

Network-optional by design: every failure raises ``RefreshError`` with an
actionable message; the caller leaves the bundled data untouched and shows
the note in the UI, exactly like a broken job board lands in "needs
attention" rather than failing a whole run.
"""

from __future__ import annotations

import csv
import io
import re

from jobsearch.http import make_session
from jobsearch.utils import normalize_company_name

from . import canonical_key, leetcode_url

# Default source: the community "LeetCode questions, company-wise" CSV dataset.
# Override base/timeframe under `company_questions:` in config/settings.yaml.
DEFAULT_BASE = (
    "https://raw.githubusercontent.com/krishnadey30/"
    "LeetCode-Questions-CompanyWise/master"
)
DEFAULT_TIMEFRAME = "alltime"  # alltime | 6months | 1year | 30days

_SLUG_RE = re.compile(r"/problems/([a-z0-9-]+)")


class RefreshError(RuntimeError):
    """Raised when an online refresh can't complete (no network, no file for
    the company, unparseable response). Carries a human-readable reason."""


def _file_candidates(company: str, timeframe: str) -> list[str]:
    """Plausible CSV filenames for a company, most-likely first. Datasets vary
    on word separators, so we try a few and use whichever resolves.

    Order is deterministic and most-specific-first; the bare-first-word stem
    ('goldman') is a last resort since it can collide with another company's
    file. ``dict.fromkeys`` dedups while preserving that order."""
    key = normalize_company_name(company)  # 'goldman sachs', 'jpmorgan chase'
    stems = [
        key.replace(" ", "-"),
        key.replace(" ", "_"),
        key.replace(" ", ""),
        key.split(" ")[0] if key else "",
    ]
    ordered = list(dict.fromkeys(s for s in stems if s))
    return [f"{stem}_{timeframe}.csv" for stem in ordered]


def _slug_from_link(link: str) -> str:
    m = _SLUG_RE.search(link or "")
    return m.group(1) if m else ""


def _norm_difficulty(value: str) -> str:
    v = (value or "").strip().lower()
    return v if v in ("easy", "medium", "hard") else "medium"


def _parse_frequency(value: str) -> float:
    """Frequencies come as '92.3', '0.92', '92.3%' or blank. Normalize to a
    0–100 scale so the UI bar and sort behave.

    A value strictly between 0 and 1 is read as a 0..1 fraction and scaled up;
    1.0 and above are treated as already-percentage so a legitimate low score
    of '1' on a 0..100 dataset isn't inflated to 100 (which would wrongly sort
    it to the top)."""
    s = (value or "").strip().replace("%", "")
    if not s:
        return 0.0
    try:
        f = float(s)
    except ValueError:
        return 0.0
    return round(f * 100, 1) if 0 < f < 1 else round(f, 1)


def _column_map(header: list[str]) -> dict[str, int]:
    """Map our logical fields to column indices by header keyword, tolerant of
    the differing schemas across community datasets."""
    idx: dict[str, int] = {}
    for i, raw in enumerate(header):
        h = (raw or "").strip().lower()
        # Check the more specific columns first; "title" (which also matches the
        # generic 'problem'/'name') is last so a header like "Problem Link" or
        # "Problem URL" is classified as the link column, not the title.
        if ("link" in h or "url" in h) and "link" not in idx:
            idx["link"] = i
        elif "difficult" in h and "difficulty" not in idx:
            idx["difficulty"] = i
        elif ("frequen" in h or h == "freq") and "frequency" not in idx:
            idx["frequency"] = i
        elif h in ("id", "#", "number", "no", "no.") and "number" not in idx:
            idx["number"] = i
        elif ("title" in h or "problem" in h or "name" in h) and "title" not in idx:
            idx["title"] = i
    return idx


def parse_csv(text: str, company: str, *, source: str = "github_csv",
              timeframe: str = DEFAULT_TIMEFRAME) -> list[dict]:
    """Parse one company CSV into upsert-ready records. Public for testing."""
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []
    cols = _column_map(rows[0])
    if "title" not in cols or "link" not in cols:
        raise RefreshError(
            "dataset CSV had an unexpected layout (no title/link columns)")
    key = canonical_key(company)
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows[1:]:
        def cell(field: str) -> str:
            i = cols.get(field)
            return row[i].strip() if i is not None and i < len(row) else ""

        link = cell("link")
        slug = _slug_from_link(link)
        title = cell("title")
        if not slug or not title or slug in seen:
            continue
        seen.add(slug)
        number = None
        if cell("number"):
            try:
                number = int(re.sub(r"\D", "", cell("number")) or 0) or None
            except ValueError:
                number = None
        out.append({
            "company": company,
            "company_key": key,
            "leetcode_number": number,
            "leetcode_slug": slug,
            "title": title,
            "difficulty": _norm_difficulty(cell("difficulty")),
            "frequency": _parse_frequency(cell("frequency")),
            "timeframe": timeframe,
            "topics": "",
            "url": link or leetcode_url(slug),
            "source": source,
        })
    return out


def fetch_for_company(company: str, settings: dict | None = None,
                      session=None) -> list[dict]:
    """Download and parse the company's list from the configured dataset.

    Raises :class:`RefreshError` on any failure so the caller can keep the
    bundled list and surface the reason. Returns [] only if the file is found
    but genuinely empty.
    """
    cfg = (settings or {}).get("company_questions", {}) or {}
    base = (cfg.get("github_csv_base") or DEFAULT_BASE).rstrip("/")
    timeframe = cfg.get("timeframe") or DEFAULT_TIMEFRAME
    sess = session or make_session(timeout=int(cfg.get("timeout_seconds", 30)))

    tried: list[str] = []
    last_status = None
    for fname in _file_candidates(company, timeframe):
        url = f"{base}/{fname}"
        tried.append(fname)
        try:
            resp = sess.get(url, timeout=getattr(sess, "request_timeout", 30))
        except Exception as exc:  # noqa: BLE001 — network down, DNS, TLS, …
            raise RefreshError(f"could not reach the dataset host: {exc}") from exc
        if resp.status_code == 200 and resp.text.strip():
            return parse_csv(resp.text, company, timeframe=timeframe)
        last_status = resp.status_code
    raise RefreshError(
        f"no question list found for {company!r} in the dataset "
        f"(tried {', '.join(tried)}; last HTTP {last_status}). "
        "The bundled list is unchanged.")
