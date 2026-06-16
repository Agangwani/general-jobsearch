"""Pull pipeline output into the application database.

Reads reports/latest.json (matched + near-miss jobs) and joins descriptions
from the newest corpus snapshot in data/corpus/ (latest.json deliberately
omits descriptions to keep the report light). Upserts each job: new keys are
inserted with the exact insertion timestamp; existing keys are patched only
where values changed, with the diff recorded in job_events. Running ingest
five times a day therefore never duplicates a posting.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from . import db


def _load_descriptions(corpus_dir: Path) -> dict[str, str]:
    snapshots = sorted(corpus_dir.glob("*.jsonl.gz"))
    if not snapshots:
        return {}
    descriptions = {}
    with gzip.open(snapshots[-1], "rt", encoding="utf-8") as fh:
        for line in fh:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if raw.get("key") and raw.get("description"):
                descriptions[raw["key"]] = raw["description"]
    return descriptions


def _to_record(raw: dict, descriptions: dict[str, str]) -> dict | None:
    key = raw.get("key", "")
    if not key:
        return None
    return {
        "key": key,
        "source": key.split(":", 1)[0],
        "company": raw.get("company", ""),
        "title": raw.get("title", ""),
        "location": raw.get("location", ""),
        "url": raw.get("url", ""),
        "description": descriptions.get(key, ""),
        "posted_at": None if raw.get("posted") in (None, "unknown") else raw.get("posted"),
        "fit_score": raw.get("fit"),
        "rank_score": raw.get("rank_score"),
        "cluster": raw.get("cluster"),
        "filter_reason": raw.get("filter_reason", ""),
        "validation": raw.get("validation", ""),
        "validation_note": raw.get("validation_note", ""),
    }


def ingest_latest(root: Path, conn) -> dict[str, int]:
    report_path = root / "reports" / "latest.json"
    if not report_path.exists():
        raise FileNotFoundError(f"{report_path} not found — run `python -m jobsearch run` first")
    report = json.loads(report_path.read_text())
    descriptions = _load_descriptions(root / "data" / "corpus")

    now = db.utcnow()
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    report_keys: set[str] = set()
    for raw in list(report.get("jobs", [])) + list(report.get("near_miss", [])):
        record = _to_record(raw, descriptions)
        if record is None:
            continue
        report_keys.add(record["key"])
        outcome = db.upsert_job(conn, record, now=now)
        counts[outcome] += 1

    conn.execute(
        "INSERT INTO runs (ingested_at, report_date, jobs_inserted, jobs_updated, jobs_total) "
        "VALUES (?, ?, ?, ?, ?)",
        (now, report.get("generated", "")[:10], counts["inserted"], counts["updated"],
         sum(counts.values())),
    )
    conn.commit()
    print(f"Ingest: {counts['inserted']} inserted, {counts['updated']} patched, "
          f"{counts['unchanged']} unchanged", file=sys.stderr)

    # Diagnostic: the dashboard shows every job ever ingested, not just this
    # run's. If a previous run targeted different roles (e.g. SWE) those jobs
    # persist in the to-apply stack. Surface how many so a "why am I still
    # seeing old roles?" result is explained rather than mysterious.
    stale = _count_stale_to_apply(conn, report_keys)
    if stale:
        print(f"Note: {stale} unapplied job(s) in the dashboard are NOT in this "
              "report — they're from earlier runs (possibly a different role "
              "target). Filter the dashboard by company/score, or clear them, "
              "to focus on this run.", file=sys.stderr)
    counts["stale_unapplied"] = stale
    return counts


def _count_stale_to_apply(conn, report_keys: set[str]) -> int:
    """Count not-applied jobs in the DB that are absent from the current
    report — i.e. carried over from earlier runs."""
    rows = conn.execute(
        "SELECT j.key FROM jobs j JOIN applications a ON a.job_id = j.id "
        "WHERE a.status = 'not_applied'").fetchall()
    return sum(1 for r in rows if r["key"] not in report_keys)
