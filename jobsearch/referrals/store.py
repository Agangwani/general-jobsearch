"""SQLite layer for referral candidates and per-job matches.

Candidates are global per-company (one row per LinkedIn URL, refreshed when
re-discovered). Matches are per-(candidate, job) and re-recorded on every
discovery run — the scores depend on the current resume and the job's
current description, both of which can change between runs.

Uses the connection opened by webapp.db.connect() — same conn, same
row_factory, same WAL settings.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .rank import ScoredCandidate
from .sources.linkedin import CandidateHit


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------- candidates

def upsert_candidate(conn: sqlite3.Connection, company: str, hit: CandidateHit) -> int:
    """Insert or refresh a candidate by linkedin_url. Returns the row id."""
    now = _utcnow()
    raw = json.dumps({
        "headline": hit.headline,
        "current_role": hit.current_role,
        "current_company": hit.current_company,
        "location": hit.location,
        "raw_text": hit.raw_text,
    })
    row = conn.execute(
        "SELECT id FROM referral_candidates WHERE linkedin_url = ?",
        (hit.linkedin_url,),
    ).fetchone()
    if row is None:
        # RETURNING id is portable across SQLite (3.35+) and Postgres; psycopg
        # has no cursor.lastrowid, so the new id is read back explicitly.
        row = conn.execute(
            """INSERT INTO referral_candidates
                 (company, name, headline, linkedin_url, "current_role",
                  current_company, location, summary, raw_json,
                  first_seen_at, last_refreshed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (company, hit.name, hit.headline, hit.linkedin_url, hit.current_role,
             hit.current_company, hit.location, "", raw, now, now),
        ).fetchone()
        conn.commit()
        return row["id"]
    conn.execute(
        """UPDATE referral_candidates
              SET company = ?, name = ?, headline = ?, "current_role" = ?,
                  current_company = ?, location = ?, raw_json = ?,
                  last_refreshed_at = ?
            WHERE id = ?""",
        (company, hit.name, hit.headline, hit.current_role,
         hit.current_company, hit.location, raw, now, row["id"]),
    )
    conn.commit()
    return row["id"]


# -------------------------------------------------------------------- matches

def record_match(
    conn: sqlite3.Connection, candidate_id: int, job_id: int,
    job_match: float, user_match: float, combined: float,
) -> None:
    now = _utcnow()
    conn.execute(
        """INSERT INTO referral_matches
             (candidate_id, job_id, job_match, user_match, combined, matched_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(candidate_id, job_id) DO UPDATE SET
             job_match = excluded.job_match,
             user_match = excluded.user_match,
             combined = excluded.combined,
             matched_at = excluded.matched_at""",
        (candidate_id, job_id, job_match, user_match, combined, now),
    )
    conn.commit()


def save_matches(
    conn: sqlite3.Connection, job_id: int, company: str,
    scored: list[ScoredCandidate],
) -> int:
    """Upsert every scored hit and record its match. Returns rows persisted."""
    n = 0
    for s in scored:
        cid = upsert_candidate(conn, company, s.hit)
        record_match(conn, cid, job_id, s.job_match, s.user_match, s.combined)
        n += 1
    return n


def candidates_for_job(conn: sqlite3.Connection, job_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT c.*, m.job_match, m.user_match, m.combined, m.matched_at
             FROM referral_matches m
             JOIN referral_candidates c ON c.id = m.candidate_id
            WHERE m.job_id = ?
            ORDER BY m.combined DESC, m.job_match DESC""",
        (job_id,),
    ).fetchall()


# ----------------------------------------------------------------------- runs
# The UI polls a single referral_runs row per job to render a "Discovering …"
# state while a background thread is searching.

def start_run(conn: sqlite3.Connection, job_id: int) -> int:
    row = conn.execute(
        "INSERT INTO referral_runs (job_id, state, started_at) "
        "VALUES (?, 'running', ?) RETURNING id",
        (job_id, _utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


def finish_run(conn: sqlite3.Connection, run_id: int, detail: str = "") -> None:
    conn.execute(
        "UPDATE referral_runs SET state = 'done', detail = ?, finished_at = ? WHERE id = ?",
        (detail, _utcnow(), run_id),
    )
    conn.commit()


def fail_run(conn: sqlite3.Connection, run_id: int, detail: str) -> None:
    conn.execute(
        "UPDATE referral_runs SET state = 'error', detail = ?, finished_at = ? WHERE id = ?",
        (detail[:500], _utcnow(), run_id),
    )
    conn.commit()


def latest_run(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM referral_runs WHERE job_id = ? ORDER BY id DESC LIMIT 1",
        (job_id,),
    ).fetchone()


def is_running(conn: sqlite3.Connection, job_id: int) -> bool:
    row = latest_run(conn, job_id)
    return bool(row and row["state"] == "running")
