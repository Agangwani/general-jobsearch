"""SQLite store for the job-application workflow.

Design principles (see docs/design-frontend.md):

- `jobs` is the canonical row per unique posting (keyed by the pipeline's
  `source:company:job_id` key). `first_seen_at` is the exact UTC insertion
  timestamp of the run that discovered it; re-runs the same day only bump
  `last_seen_at` or patch changed fields — never duplicate.
- Every mutation appends to an event table (`job_events`,
  `application_events`) so each row's full history is queryable: nothing is
  ever lost by an update.
- `applications` tracks the apply lifecycle separately from the posting
  itself; the two "stacks" in the UI (to-apply / applied) are views over
  `applications.status`.
- `email_*` tables are the scaffold for the Gmail module: messages land
  append-only and link to applications/jobs when matched.

The DB lives at data/jobsearch.db (gitignored — it holds profile PII and
application history).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY,
    key             TEXT UNIQUE NOT NULL,
    source          TEXT NOT NULL,
    company         TEXT NOT NULL,
    title           TEXT NOT NULL,
    location        TEXT DEFAULT '',
    url             TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    posted_at       TEXT,
    fit_score       REAL,
    rank_score      REAL,
    cluster         INTEGER,
    filter_reason   TEXT DEFAULT '',
    validation      TEXT DEFAULT '',
    validation_note TEXT DEFAULT '',
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen_at);

CREATE TABLE IF NOT EXISTS job_events (
    id          INTEGER PRIMARY KEY,
    job_id      INTEGER NOT NULL REFERENCES jobs(id),
    event_type  TEXT NOT NULL,      -- inserted | updated | deactivated | reactivated
    payload     TEXT DEFAULT '',    -- JSON: {field: [old, new], ...}
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id);

CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY,
    job_id        INTEGER UNIQUE NOT NULL REFERENCES jobs(id),
    status        TEXT NOT NULL DEFAULT 'not_applied',
    applied_at    TEXT,
    submitted_via TEXT DEFAULT '',
    notes         TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_events (
    id             INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id),
    status         TEXT NOT NULL,
    detail         TEXT DEFAULT '',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_app_events_app ON application_events(application_id);

CREATE TABLE IF NOT EXISTS profile_fields (
    id         INTEGER PRIMARY KEY,
    field      TEXT UNIQUE NOT NULL,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY,
    ingested_at   TEXT NOT NULL,
    report_date   TEXT DEFAULT '',
    jobs_inserted INTEGER NOT NULL DEFAULT 0,
    jobs_updated  INTEGER NOT NULL DEFAULT 0,
    jobs_total    INTEGER NOT NULL DEFAULT 0
);

-- ------------------------------------------------- email module scaffold ---
CREATE TABLE IF NOT EXISTS email_accounts (
    id         INTEGER PRIMARY KEY,
    provider   TEXT NOT NULL,            -- gmail
    address    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'disconnected',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_messages (
    id             INTEGER PRIMARY KEY,
    account_id     INTEGER REFERENCES email_accounts(id),
    application_id INTEGER REFERENCES applications(id),
    job_id         INTEGER REFERENCES jobs(id),
    message_id     TEXT UNIQUE,          -- provider message id
    thread_id      TEXT,
    direction      TEXT DEFAULT 'inbound',
    from_addr      TEXT DEFAULT '',
    to_addr        TEXT DEFAULT '',
    subject        TEXT DEFAULT '',
    snippet        TEXT DEFAULT '',
    body           TEXT DEFAULT '',
    sent_at        TEXT,
    ingested_at    TEXT NOT NULL,
    classification TEXT DEFAULT ''       -- confirmation | interview | rejection | other
);
CREATE INDEX IF NOT EXISTS idx_email_app ON email_messages(application_id);
"""

# Application lifecycle. Transitions are not enforced (the human is in
# charge), but the UI offers these in order.
APP_STATUSES = [
    "not_applied", "in_progress", "applied", "confirmed",
    "interviewing", "offer", "rejected", "withdrawn",
]
APPLIED_SET = {"applied", "confirmed", "interviewing", "offer", "rejected", "withdrawn"}

# Job fields that get patched (with an audit event) when a re-run brings
# new/changed values.
PATCHABLE = (
    "title", "location", "url", "description", "posted_at", "fit_score",
    "rank_score", "cluster", "filter_reason", "validation", "validation_note",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_job(conn: sqlite3.Connection, record: dict, now: str | None = None) -> str:
    """Insert a job or patch an existing one. Returns 'inserted', 'updated',
    or 'unchanged'. Every change is recorded in job_events."""
    now = now or utcnow()
    row = conn.execute("SELECT * FROM jobs WHERE key = ?", (record["key"],)).fetchone()
    if row is None:
        conn.execute(
            """INSERT INTO jobs (key, source, company, title, location, url,
                                 description, posted_at, fit_score, rank_score,
                                 cluster, filter_reason, validation,
                                 validation_note, first_seen_at, last_seen_at)
               VALUES (:key, :source, :company, :title, :location, :url,
                       :description, :posted_at, :fit_score, :rank_score,
                       :cluster, :filter_reason, :validation,
                       :validation_note, :now, :now)""",
            {**_defaults(record), "now": now},
        )
        job_id = conn.execute("SELECT id FROM jobs WHERE key = ?", (record["key"],)).fetchone()["id"]
        conn.execute(
            "INSERT INTO job_events (job_id, event_type, created_at) VALUES (?, 'inserted', ?)",
            (job_id, now),
        )
        conn.execute(
            "INSERT INTO applications (job_id, created_at, updated_at) VALUES (?, ?, ?)",
            (job_id, now, now),
        )
        conn.commit()
        return "inserted"

    changes = {}
    for field in PATCHABLE:
        if field not in record:
            continue
        new = record[field]
        old = row[field]
        # A re-run with an empty description must not erase a stored one.
        if new in (None, "") and old not in (None, ""):
            continue
        if new != old:
            changes[field] = [old, new]

    sets = ", ".join(f"{f} = ?" for f in changes)
    if changes:
        conn.execute(
            f"UPDATE jobs SET {sets}, last_seen_at = ?, is_active = 1 WHERE id = ?",
            [v[1] for v in changes.values()] + [now, row["id"]],
        )
        conn.execute(
            "INSERT INTO job_events (job_id, event_type, payload, created_at) "
            "VALUES (?, 'updated', ?, ?)",
            (row["id"], json.dumps(changes, default=str), now),
        )
        conn.commit()
        return "updated"

    conn.execute("UPDATE jobs SET last_seen_at = ?, is_active = 1 WHERE id = ?", (now, row["id"]))
    conn.commit()
    return "unchanged"


def _defaults(record: dict) -> dict:
    base = {
        "location": "", "url": "", "description": "", "posted_at": None,
        "fit_score": None, "rank_score": None, "cluster": None,
        "filter_reason": "", "validation": "", "validation_note": "",
    }
    base.update(record)
    return base


def set_application_status(
    conn: sqlite3.Connection, application_id: int, status: str,
    detail: str = "", via: str = "",
) -> None:
    now = utcnow()
    fields = {"status": status, "updated_at": now}
    if status == "applied":
        fields["applied_at"] = now
    if via:
        fields["submitted_via"] = via
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE applications SET {sets} WHERE id = ?", [*fields.values(), application_id])
    conn.execute(
        "INSERT INTO application_events (application_id, status, detail, created_at) "
        "VALUES (?, ?, ?, ?)",
        (application_id, status, detail, now),
    )
    conn.commit()


def job_with_application(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT j.*, a.id AS application_id, a.status, a.applied_at,
                  a.submitted_via, a.notes
           FROM jobs j JOIN applications a ON a.job_id = j.id
           WHERE j.id = ?""",
        (job_id,),
    ).fetchone()


def search_jobs(
    conn: sqlite3.Connection,
    q: str = "",
    company: str = "",
    stack: str = "",           # "" | "to_apply" | "applied"
    include_near_miss: bool = True,
    limit: int = 500,
) -> list[sqlite3.Row]:
    sql = [
        """SELECT j.*, a.id AS application_id, a.status, a.applied_at
           FROM jobs j JOIN applications a ON a.job_id = j.id WHERE 1=1"""
    ]
    args: list = []
    if q:
        sql.append("AND (j.title LIKE ? OR j.description LIKE ? OR j.company LIKE ? OR j.location LIKE ?)")
        args += [f"%{q}%"] * 4
    if company:
        sql.append("AND j.company = ?")
        args.append(company)
    if stack == "applied":
        sql.append(f"AND a.status IN ({','.join('?' * len(APPLIED_SET))})")
        args += sorted(APPLIED_SET)
    elif stack == "to_apply":
        sql.append(f"AND a.status NOT IN ({','.join('?' * len(APPLIED_SET))})")
        args += sorted(APPLIED_SET)
    if not include_near_miss:
        sql.append("AND j.filter_reason = ''")
    sql.append("ORDER BY a.status != 'in_progress', j.rank_score DESC NULLS LAST, j.first_seen_at DESC")
    sql.append("LIMIT ?")
    args.append(limit)
    return conn.execute(" ".join(sql), args).fetchall()


def stack_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT a.status, COUNT(*) AS n FROM applications a "
        "JOIN jobs j ON j.id = a.job_id WHERE j.is_active = 1 GROUP BY a.status"
    ).fetchall()
    by_status = {r["status"]: r["n"] for r in rows}
    applied = sum(n for s, n in by_status.items() if s in APPLIED_SET)
    to_apply = sum(n for s, n in by_status.items() if s not in APPLIED_SET)
    return {"to_apply": to_apply, "applied": applied, "by_status": by_status}
