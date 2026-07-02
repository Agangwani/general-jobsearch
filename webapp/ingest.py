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

from jobsearch.config import load_settings, registry_entries
from jobsearch.tracks import build_track
from jobsearch.utils import normalize_company_name

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


def _ingest_report(root, conn, track, now: str, user_id: str = db.LOCAL_USER_ID):
    """Ingest one track's latest.json for a user. Returns
    (counts, report_keys, report_date, job_counts, present) where job_counts
    maps normalized company name → postings seen this run (feeds the companies
    registry search-state) and present is False when the track has no report.
    A missing report is not an error — that track may not have been run yet."""
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    job_counts: dict[str, int] = {}
    report_path = track.reports_dir / "latest.json"
    if not report_path.exists():
        return counts, set(), "", job_counts, False
    report = json.loads(report_path.read_text())
    descriptions = _load_descriptions(track.corpus_dir)
    report_keys: set[str] = set()
    for raw in list(report.get("jobs", [])) + list(report.get("near_miss", [])):
        record = _to_record(raw, descriptions)
        if record is None:
            continue
        report_keys.add(record["key"])
        counts[db.upsert_job(conn, record, now=now, user_id=user_id)] += 1
        ckey = normalize_company_name(record["company"])
        if ckey:
            job_counts[ckey] = job_counts.get(ckey, 0) + 1
    return counts, report_keys, report.get("generated", "")[:10], job_counts, True


def _ingest_registry(root, conn, settings, track, job_counts: dict[str, int],
                     now: str, user_id: str = db.LOCAL_USER_ID) -> dict[str, int]:
    """Mirror the track's live registry into the companies table: upsert each
    current company (tagged curated/discovered), stamp per-company search-state
    from this run, disable companies no longer in the registry, and log the run.
    Keeps the companies table reflecting exactly what the pipeline fetched, so a
    dropped company never lingers as enabled.

    Registry sync is best-effort: a malformed registry YAML (hand-edited
    companies.yaml, corrupted generated file) must never abort an ingest that
    the pipeline fetch already earned — it degrades to a no-op, mirroring the
    per-board graceful-degradation the pipeline itself uses."""
    try:
        entries = registry_entries(root, settings, track)
    except Exception as exc:  # noqa: BLE001 - a bad registry must not abort ingest
        print(f"Registry sync skipped for {track.name}: {exc}", file=sys.stderr)
        return {"total": 0, "new": 0, "disabled": 0}
    keep: set[str] = set()
    new = 0
    for entry in entries:
        key = normalize_company_name(entry["name"])
        if not key:
            continue
        keep.add(key)
        if db.upsert_company(conn, entry, user_id=user_id, track=track.name,
                             now=now) == "inserted":
            new += 1
        db.touch_company_search(conn, user_id, track.name, key,
                                job_counts.get(key, 0), now)
    disabled = db.disable_absent_companies(conn, user_id, track.name, keep, now)
    db.record_company_search_run(
        conn, user_id, track.name, "ingest",
        companies_total=len(keep), companies_new=new,
        companies_disabled=disabled, jobs_found=sum(job_counts.values()), now=now)
    conn.commit()
    return {"total": len(keep), "new": new, "disabled": disabled}


def _ingest_startup_meta(root, conn, track, user_id: str = db.LOCAL_USER_ID) -> int:
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
        if db.upsert_startup_company(conn, meta, user_id=user_id) != "skipped":
            n += 1
    conn.commit()
    return n


def ingest_latest(root: Path, conn, user_id: str = db.LOCAL_USER_ID) -> dict[str, int]:
    """Ingest every track's latest report for a user, then refresh that user's
    startup facts + flags."""
    settings = load_settings(root / "config" / "settings.yaml")
    main_track = build_track(root, settings, "main", user_id)
    startup_track = build_track(root, settings, "startups", user_id)

    if not (main_track.reports_dir / "latest.json").exists() and \
       not (startup_track.reports_dir / "latest.json").exists():
        raise FileNotFoundError(
            f"{main_track.reports_dir / 'latest.json'} not found — run "
            "`python -m jobsearch run` (and/or `run-startups`) first")

    now = db.utcnow()
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    report_keys: set[str] = set()
    report_date = ""
    present_tracks: list[tuple] = []
    for track in (main_track, startup_track):
        track_counts, keys, date, job_counts, present = _ingest_report(
            root, conn, track, now, user_id)
        for k, v in track_counts.items():
            counts[k] += v
        report_keys |= keys
        report_date = report_date or date
        if present:
            present_tracks.append((track, job_counts))

    # Startup facts + per-job flags. Metadata first so the flag pass sees the
    # freshly-loaded companies; flags run unconditionally so a job already in the
    # DB gets tagged once its company becomes known.
    startups_loaded = _ingest_startup_meta(root, conn, startup_track, user_id)
    flagged = db.refresh_startup_flags(conn, user_id)

    # Mirror each run track's live registry into the companies table (tracking
    # layer + search-state); only tracks that actually ran (have a report) sync,
    # so a never-run track's registry isn't stamped as "searched".
    companies_synced = 0
    companies_new = 0
    for track, job_counts in present_tracks:
        summary = _ingest_registry(root, conn, settings, track, job_counts, now, user_id)
        companies_synced += summary["total"]
        companies_new += summary["new"]

    conn.execute(
        "INSERT INTO runs (ingested_at, report_date, jobs_inserted, jobs_updated, jobs_total) "
        "VALUES (?, ?, ?, ?, ?)",
        (now, report_date, counts["inserted"], counts["updated"], sum(counts.values())),
    )
    conn.commit()
    print(f"Ingest: {counts['inserted']} inserted, {counts['updated']} patched, "
          f"{counts['unchanged']} unchanged; {startups_loaded} startup profiles, "
          f"{flagged} startup flags updated; {companies_synced} companies tracked "
          f"({companies_new} new)", file=sys.stderr)

    # Diagnostic: the dashboard shows every job ever ingested, not just this
    # run's. If a previous run targeted different roles those jobs persist in
    # the to-apply stack. Surface how many so a "why am I still seeing old
    # roles?" result is explained rather than mysterious.
    stale = _count_stale_to_apply(conn, report_keys, user_id)
    if stale:
        print(f"Note: {stale} unapplied job(s) in the dashboard are NOT in these "
              "reports — they're from earlier runs (possibly a different role "
              "target). Filter the dashboard by company/score, or clear them, "
              "to focus on this run.", file=sys.stderr)
    counts["stale_unapplied"] = stale
    counts["startups_loaded"] = startups_loaded
    counts["companies_synced"] = companies_synced
    counts["companies_new"] = companies_new
    return counts


def _count_stale_to_apply(conn, report_keys: set[str],
                          user_id: str = db.LOCAL_USER_ID) -> int:
    """Count not-applied jobs in the DB that are absent from the current
    reports — i.e. carried over from earlier runs."""
    rows = conn.execute(
        "SELECT j.key FROM jobs j JOIN applications a ON a.job_id = j.id "
        "WHERE a.status = 'not_applied' AND j.user_id = ?", (user_id,)).fetchall()
    return sum(1 for r in rows if r["key"] not in report_keys)
