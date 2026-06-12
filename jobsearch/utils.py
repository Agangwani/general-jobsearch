from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

_TAG_RE = re.compile(r"<[^>]+>")
_HSPACE_RE = re.compile(r"[ \t]+")


def strip_html(text: str) -> str:
    """Convert (possibly entity-escaped) HTML into plain text, one line per
    block element and a `• ` marker per list item, so descriptions keep their
    paragraph/bullet structure for display and sentence-level boilerplate
    stripping."""
    if not text:
        return ""
    # Greenhouse double-escapes (&amp;nbsp;), so unescape until stable —
    # otherwise "nbsp" leaks into the text and shows up as a TF-IDF token.
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = re.sub(r"<li\b[^>]*>", "\n• ", text, flags=re.I)
    text = re.sub(
        r"</?(br|p|li|div|ul|ol|h[1-6]|tr|section|article)\b[^>]*>",
        "\n", text, flags=re.I,
    )
    text = _TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ")
    lines = (_HSPACE_RE.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def parse_when(value) -> Optional[datetime]:
    """Best-effort timestamp parsing across the formats job boards use."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:  # epoch milliseconds
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    value = str(value).strip()
    iso = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    if value.isdigit():
        return parse_when(int(value))
    return None


def walk_collect(obj, predicate, _out=None) -> list[dict]:
    """Recursively collect every dict in a nested JSON payload that satisfies
    `predicate`. Lets browser fetchers harvest job records from captured XHR
    bodies without hard-coding each site's response nesting."""
    if _out is None:
        _out = []
    if isinstance(obj, dict):
        if predicate(obj):
            _out.append(obj)
        else:
            for value in obj.values():
                walk_collect(value, predicate, _out)
    elif isinstance(obj, list):
        for item in obj:
            walk_collect(item, predicate, _out)
    return _out


def first(record: dict, keys: tuple[str, ...], default=""):
    """Return the first non-empty value among `keys` in `record`."""
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


_WORKDAY_DAYS_RE = re.compile(r"posted\s+(\d+)\+?\s+days?\s+ago", re.I)


def parse_workday_posted_on(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Workday only exposes relative dates like 'Posted 3 Days Ago'."""
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    lowered = text.lower()
    if "today" in lowered:
        return now
    if "yesterday" in lowered:
        return now - timedelta(days=1)
    match = _WORKDAY_DAYS_RE.search(lowered)
    if match:
        days = int(match.group(1))
        if "+" in text:
            days += 5  # "30+ days ago" — push it past the recency window
        return now - timedelta(days=days)
    return None
