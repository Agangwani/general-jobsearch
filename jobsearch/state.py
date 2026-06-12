"""Persistence of jobs seen on previous runs, so the report can flag NEW ones.

The state lives in a TSV ("key<TAB>date" per line, sorted): git merges line
formats cleanly, and even a botched merge (conflict markers committed) only
costs the conflicted lines — the loader salvages every valid line instead of
silently resetting, which is exactly what happened with the old JSON format
(a corrupt merge made every job look 🆕).
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models import JobPosting

_TSV_LINE = re.compile(r"^(\S+)\t(\d{4}-\d{2}-\d{2})$")
# Legacy JSON entries ("key": "date") — also matches inside corrupted files.
_JSON_LINE = re.compile(r'"([^"]+)"\s*:\s*"(\d{4}-\d{2}-\d{2})"')


def _salvage(text: str) -> dict[str, str]:
    seen: dict[str, str] = {}
    for line in text.splitlines():
        match = _TSV_LINE.match(line.strip()) or _JSON_LINE.search(line)
        if match:
            seen.setdefault(match.group(1), match.group(2))
    return seen


def load_seen(path: Path) -> dict[str, str]:
    candidates = [path]
    if not path.exists():  # migrate from the legacy JSON state if present
        candidates = [path.with_suffix(".json"), path]
    for candidate in candidates:
        if candidate.exists():
            seen = _salvage(candidate.read_text())
            if not seen:
                print(f"  WARNING: state file {candidate} had no readable entries — "
                      "every job will be flagged new", file=sys.stderr)
            return seen
    return {}


def mark_new(jobs: list[JobPosting], seen: dict[str, str]) -> None:
    for job in jobs:
        job.is_new = job.key not in seen


def update_seen(jobs: list[JobPosting], seen: dict[str, str], path: Path) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    for job in jobs:
        seen.setdefault(job.key, today)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{key}\t{date}\n" for key, date in sorted(seen.items())))
