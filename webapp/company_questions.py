"""Glue between the company-question data layer and the web app.

- :func:`seed_bundled` loads the curated set into ``company_problems`` on
  every UI start (idempotent; a content hash short-circuits the no-op case).
- :func:`run_refresh` pulls a fresh list from the configured community dataset
  for one company (or all), upserting and recording a ``company_refresh_runs``
  row the UI polls — the same pattern as referral discovery.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import yaml

from jobsearch.company_questions import bundled_records
from jobsearch.company_questions.refresh import RefreshError, fetch_for_company

from . import db


def seed_bundled(conn: sqlite3.Connection) -> dict:
    """Seed the curated company → LeetCode sets. No-op when unchanged."""
    records = bundled_records()
    blob = json.dumps(records, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    have = conn.execute("SELECT COUNT(*) AS n FROM company_problems").fetchone()["n"]
    meta = conn.execute(
        "SELECT value FROM prep_meta WHERE key = 'company_questions_hash'").fetchone()
    if have and meta and meta["value"] == content_hash:
        return {"seeded": False, "total": have}
    summary = db.seed_company_problems(conn, records)
    conn.execute(
        """INSERT INTO prep_meta (key, value, updated_at)
           VALUES ('company_questions_hash', ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                          updated_at = excluded.updated_at""",
        (content_hash, db.utcnow()))
    conn.commit()
    summary["seeded"] = True
    return summary


def _settings(root: Path) -> dict:
    path = root / "config" / "settings.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def run_refresh(conn: sqlite3.Connection, root: Path, company: str,
                company_key: str) -> None:
    """Background worker: pull `company`'s list from the dataset and upsert it.
    Records its own ``company_refresh_runs`` row (running → done/error)."""
    run_id = db.start_company_refresh(conn, company_key)
    try:
        records = fetch_for_company(company, _settings(root))
        added = updated = 0
        now = db.utcnow()
        for rec in records:
            # Trust the canonical key derived at seed time over the dataset's.
            rec["company_key"] = company_key
            if db.upsert_company_problem(conn, rec, now) == "inserted":
                added += 1
            else:
                updated += 1
        conn.commit()
        db.finish_company_refresh(
            conn, run_id, added=added, updated=updated,
            detail=f"pulled {len(records)} from dataset "
                   f"({added} new, {updated} updated)")
    except RefreshError as exc:
        db.fail_company_refresh(conn, run_id, str(exc))
    except Exception as exc:  # noqa: BLE001 — never crash the worker thread
        db.fail_company_refresh(conn, run_id, f"unexpected error: {exc}")
