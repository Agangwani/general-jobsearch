"""Pull pipeline output into the application database.

Reads each track's report (`reports/latest.json` for the main pipeline,
`reports/startups/latest.json` for the startup pipeline) and joins descriptions
from that track's newest corpus snapshot (latest.json deliberately omits
descriptions to keep the report light). Upserts each job: new keys are inserted
with the exact insertion timestamp; existing keys are patched only where values
changed, with the diff recorded in job_events. Running ingest repeatedly never
duplicates a posting.

After the jobs land, it loads the startup metadata sidecar
(`data/startup_meta.json`, written by `discover-startups`) into the
startup_companies table and flags every job whose company is a known startup, so
the dashboard can show only / hide / mix startup jobs.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from jobsearch.config import load_settings
from jobsearch.tracks import build_track

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


def _ingest_report(root, conn, track, now: str) -> tuple[dict[str, int], set[str], str]:
    """Ingest one track's latest.json. Returns (counts, report_keys, report_date).
    A missing report is not an error — that track may not have been run yet."""
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    report_path = track.reports_dir / "latest.json"
    if not report_path.exists():
        return counts, set(), ""
    report = json.loads(report_path.read_text())
    descriptions = _load_descriptions(track.corpus_dir)
    report_keys: set[str] = set()
    for raw in list(report.get("jobs", [])) + list(report.get("near_miss", [])):
        record = _to_record(raw, descriptions)
        if record is None:
            continue
        report_keys.add(record["key"])
        counts[db.upsert_job(conn, record, now=now)] += 1
    return counts, report_keys, report.get("generated", "")[:10]


def _ingest_startup_meta(root, conn, track) -> int:
    """Load the startup metadata sidecar into startup_companies. Returns the
    number of companies upserted (skips ones a user has edited in the UI)."""
    if not track.meta_file or not track.meta_file.exists():
        return 0
    try:
        payload = json.loads(track.meta_file.read_text())
    except (ValueError, OSError):
        return 0
    n = 0
    for meta in (payload.get("companies") or {}).values():
        if db.upsert_startup_company(conn, meta) != "skipped":
            n += 1
    conn.commit()
    return n


def ingest_latest(root: Path, conn) -> dict[str, int]:
    """Ingest every track's latest report, then refresh startup facts + flags."""
    settings = load_settings(root / "config" / "settings.yaml")
    main_track = build_track(root, settings, "main")
    startup_track = build_track(root, settings, "startups")

    if not (main_track.reports_dir / "latest.json").exists() and \
       not (startup_track.reports_dir / "latest.json").exists():
        raise FileNotFoundError(
            f"{main_track.reports_dir / 'latest.json'} not found — run "
            "`python -m jobsearch run` (and/or `run-startups`) first")

    now = db.utcnow()
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    report_keys: set[str] = set()
    report_date = ""
    for track in (main_track, startup_track):
        track_counts, keys, date = _ingest_report(root, conn, track, now)
        for k, v in track_counts.items():
            counts[k] += v
        report_keys |= keys
        report_date = report_date or date

    # Startup facts + per-job flags. Metadata first so the flag pass sees the
    # freshly-loaded companies; flags run unconditionally so a job already in the
    # DB gets tagged once its company becomes known.
    startups_loaded = _ingest_startup_meta(root, conn, startup_track)
    flagged = db.refresh_startup_flags(conn)

    conn.execute(
        "INSERT INTO runs (ingested_at, report_date, jobs_inserted, jobs_updated, jobs_total) "
        "VALUES (?, ?, ?, ?, ?)",
        (now, report_date, counts["inserted"], counts["updated"], sum(counts.values())),
    )
    conn.commit()
    print(f"Ingest: {counts['inserted']} inserted, {counts['updated']} patched, "
          f"{counts['unchanged']} unchanged; {startups_loaded} startup profiles, "
          f"{flagged} startup flags updated", file=sys.stderr)

    # Diagnostic: the dashboard shows every job ever ingested, not just this
    # run's. If a previous run targeted different roles those jobs persist in
    # the to-apply stack. Surface how many so a "why am I still seeing old
    # roles?" result is explained rather than mysterious.
    stale = _count_stale_to_apply(conn, report_keys)
    if stale:
        print(f"Note: {stale} unapplied job(s) in the dashboard are NOT in these "
              "reports — they're from earlier runs (possibly a different role "
              "target). Filter the dashboard by company/score, or clear them, "
              "to focus on this run.", file=sys.stderr)
    counts["stale_unapplied"] = stale
    counts["startups_loaded"] = startups_loaded
    return counts


def _count_stale_to_apply(conn, report_keys: set[str]) -> int:
    """Count not-applied jobs in the DB that are absent from the current
    reports — i.e. carried over from earlier runs."""
    rows = conn.execute(
        "SELECT j.key FROM jobs j JOIN applications a ON a.job_id = j.id "
        "WHERE a.status = 'not_applied'").fetchall()
    return sum(1 for r in rows if r["key"] not in report_keys)
