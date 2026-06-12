"""Daily corpus snapshots.

Every run persists the full fetched corpus (pre-filter, post-dedupe) to
data/corpus/YYYY-MM-DD.jsonl.gz so scoring changes can be replayed and
A/B-tested offline against real data. Snapshots are local-only (gitignored —
they contain full descriptions and would bloat the repo).
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import JobPosting


def write_snapshot(jobs: list[JobPosting], out_dir: Path, retention_days: int = 14) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    path = out_dir / f"{today}.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for job in jobs:
            fh.write(json.dumps({
                "key": job.key,
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "url": job.url,
                "posted": job.posted_at.isoformat() if job.posted_at else None,
                "source": job.source,
                "description": job.description,
            }, ensure_ascii=False) + "\n")
    _prune(out_dir, retention_days)
    return path


def load_snapshot(path: Path) -> list[JobPosting]:
    jobs = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            raw = json.loads(line)
            posted = raw.get("posted")
            jobs.append(JobPosting(
                company=raw.get("company", ""),
                title=raw.get("title", ""),
                location=raw.get("location", ""),
                url=raw.get("url", ""),
                job_id=raw.get("key", "::").split(":")[-1],
                description=raw.get("description", ""),
                posted_at=datetime.fromisoformat(posted) if posted else None,
                source=raw.get("source", ""),
            ))
    return jobs


def _prune(out_dir: Path, retention_days: int) -> None:
    if retention_days <= 0:
        return
    snapshots = sorted(out_dir.glob("*.jsonl.gz"))
    for stale in snapshots[:-retention_days]:
        stale.unlink(missing_ok=True)
