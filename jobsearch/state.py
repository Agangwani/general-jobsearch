"""Persistence of jobs seen on previous runs, so the report can flag NEW ones."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import JobPosting


def load_seen(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def mark_new(jobs: list[JobPosting], seen: dict[str, str]) -> None:
    for job in jobs:
        job.is_new = job.key not in seen


def update_seen(jobs: list[JobPosting], seen: dict[str, str], path: Path) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    for job in jobs:
        seen.setdefault(job.key, today)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seen, indent=0, sort_keys=True) + "\n")
