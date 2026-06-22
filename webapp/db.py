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

-- --------------------------------------------- referral discovery scaffold ---
-- Candidates are per-company (an employee can refer for any role at their
-- company); per-(candidate, job) scoring lives in referral_matches.
CREATE TABLE IF NOT EXISTS referral_candidates (
    id                INTEGER PRIMARY KEY,
    company           TEXT NOT NULL,
    name              TEXT NOT NULL,
    headline          TEXT DEFAULT '',
    linkedin_url      TEXT UNIQUE NOT NULL,
    current_role      TEXT DEFAULT '',
    current_company   TEXT DEFAULT '',
    location          TEXT DEFAULT '',
    summary           TEXT DEFAULT '',
    raw_json          TEXT DEFAULT '',
    first_seen_at     TEXT NOT NULL,
    last_refreshed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_referral_candidates_company ON referral_candidates(company);

CREATE TABLE IF NOT EXISTS referral_matches (
    id             INTEGER PRIMARY KEY,
    candidate_id   INTEGER NOT NULL REFERENCES referral_candidates(id),
    job_id         INTEGER NOT NULL REFERENCES jobs(id),
    job_match      REAL NOT NULL DEFAULT 0,
    user_match     REAL NOT NULL DEFAULT 0,
    combined       REAL NOT NULL DEFAULT 0,
    matched_at     TEXT NOT NULL,
    UNIQUE(candidate_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_referral_matches_job ON referral_matches(job_id);

-- Per-job discovery state, polled by the UI while a search runs.
CREATE TABLE IF NOT EXISTS referral_runs (
    id            INTEGER PRIMARY KEY,
    job_id        INTEGER NOT NULL REFERENCES jobs(id),
    state         TEXT NOT NULL,         -- queued | running | done | error
    detail        TEXT DEFAULT '',
    started_at    TEXT NOT NULL,
    finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_referral_runs_job ON referral_runs(job_id);

-- ----------------------------------------- software interview prep modules ---
-- Content is authored in jobsearch/prep/ (coding.py, system_design.py,
-- distributed_systems.py -> ALL_TRACKS) and seeded by jobsearch.prep.seed on
-- every UI start (idempotent — a content_hash in prep_meta detects changes).
-- Progress tables (prep_lesson_progress, prep_problem_progress) are written
-- by the UI as the user works through modules and never wiped by a reseed.
CREATE TABLE IF NOT EXISTS prep_tracks (
    id          INTEGER PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prep_modules (
    id           INTEGER PRIMARY KEY,
    track_id     INTEGER NOT NULL REFERENCES prep_tracks(id),
    slug         TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT DEFAULT '',
    source_refs  TEXT DEFAULT '',
    est_minutes  INTEGER NOT NULL DEFAULT 30,
    sort_order   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_prep_modules_track ON prep_modules(track_id);

CREATE TABLE IF NOT EXISTS prep_lessons (
    id             INTEGER PRIMARY KEY,
    module_id      INTEGER NOT NULL REFERENCES prep_modules(id),
    slug           TEXT NOT NULL,
    title          TEXT NOT NULL,
    body_md        TEXT NOT NULL,
    source_refs    TEXT DEFAULT '',
    key_takeaways  TEXT DEFAULT '',          -- JSON array of bullet strings
    sort_order     INTEGER NOT NULL DEFAULT 0,
    UNIQUE(module_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_prep_lessons_module ON prep_lessons(module_id);

CREATE TABLE IF NOT EXISTS prep_problems (
    id               INTEGER PRIMARY KEY,
    module_id        INTEGER REFERENCES prep_modules(id),
    leetcode_number  INTEGER,
    leetcode_slug    TEXT,
    title            TEXT NOT NULL,
    difficulty       TEXT NOT NULL,          -- easy | medium | hard
    topic            TEXT DEFAULT '',
    url              TEXT DEFAULT '',
    sort_order       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(module_id, leetcode_slug)
);
CREATE INDEX IF NOT EXISTS idx_prep_problems_module ON prep_problems(module_id);

CREATE TABLE IF NOT EXISTS prep_lesson_progress (
    id           INTEGER PRIMARY KEY,
    lesson_id    INTEGER UNIQUE NOT NULL REFERENCES prep_lessons(id),
    state        TEXT NOT NULL DEFAULT 'not_started',
    notes        TEXT DEFAULT '',
    started_at   TEXT,
    completed_at TEXT,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prep_problem_progress (
    id           INTEGER PRIMARY KEY,
    problem_id   INTEGER UNIQUE NOT NULL REFERENCES prep_problems(id),
    state        TEXT NOT NULL DEFAULT 'not_started',  -- not_started | attempted | solved
    notes        TEXT DEFAULT '',
    solved_at    TEXT,
    updated_at   TEXT NOT NULL
);

-- CtCI book problems (Ch.1-17 of "Cracking the Coding Interview"). Unlike
-- prep_problems (a LeetCode bookmark registry) these carry the full prompt,
-- worked solution, and hint texts from the book itself.
CREATE TABLE IF NOT EXISTS prep_ctci_problems (
    id           INTEGER PRIMARY KEY,
    module_id    INTEGER NOT NULL REFERENCES prep_modules(id),
    slug         TEXT NOT NULL,
    ctci_id      TEXT NOT NULL,                       -- e.g. "1.1", "16.4"
    title        TEXT NOT NULL,
    prompt_md    TEXT NOT NULL,
    examples_md  TEXT DEFAULT '',
    hints        TEXT DEFAULT '',                     -- JSON array of strings
    solution_md  TEXT NOT NULL,
    complexity   TEXT DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(module_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_prep_ctci_problems_module ON prep_ctci_problems(module_id);

CREATE TABLE IF NOT EXISTS prep_ctci_problem_progress (
    id              INTEGER PRIMARY KEY,
    ctci_problem_id INTEGER UNIQUE NOT NULL REFERENCES prep_ctci_problems(id),
    state           TEXT NOT NULL DEFAULT 'not_started',
    notes           TEXT DEFAULT '',
    solved_at       TEXT,
    updated_at      TEXT NOT NULL
);

-- Stamped after a successful seed so reseeds skip work when content unchanged.
CREATE TABLE IF NOT EXISTS prep_meta (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ------------------------------------- company-specific LeetCode questions ---
-- "What does <company> actually ask?" — one row per (company, problem).
-- Seeded from the bundled curated set (jobsearch/company_questions) on every
-- UI start, and refreshed/extended from a community dataset via the
-- "⟳ Refresh questions" button. Solve/attempt progress lives in a separate
-- table keyed by row id, so re-seeding or refreshing never wipes it.
CREATE TABLE IF NOT EXISTS company_problems (
    id                INTEGER PRIMARY KEY,
    company           TEXT NOT NULL,            -- display name ("Goldman Sachs")
    company_key       TEXT NOT NULL,            -- normalized match key ("goldman sachs")
    leetcode_number   INTEGER,
    leetcode_slug     TEXT NOT NULL,
    title             TEXT NOT NULL,
    difficulty        TEXT NOT NULL DEFAULT 'medium',  -- easy | medium | hard
    frequency         REAL NOT NULL DEFAULT 0,  -- 0–100; how often this company asks it
    timeframe         TEXT DEFAULT '',          -- curated | alltime | 6months | ...
    topics            TEXT DEFAULT '',
    url               TEXT DEFAULT '',
    source            TEXT DEFAULT 'bundled',   -- bundled | github_csv | ...
    first_seen_at     TEXT NOT NULL,
    last_refreshed_at TEXT NOT NULL,
    UNIQUE(company_key, leetcode_slug)
);
CREATE INDEX IF NOT EXISTS idx_company_problems_key ON company_problems(company_key);

CREATE TABLE IF NOT EXISTS company_problem_progress (
    id                 INTEGER PRIMARY KEY,
    company_problem_id INTEGER UNIQUE NOT NULL REFERENCES company_problems(id),
    state              TEXT NOT NULL DEFAULT 'not_started',  -- not_started | attempted | solved
    notes              TEXT DEFAULT '',
    solved_at          TEXT,
    updated_at         TEXT NOT NULL
);

-- Per-company (or all-company) refresh state, polled by the UI while a
-- background pull runs — mirrors referral_runs.
CREATE TABLE IF NOT EXISTS company_refresh_runs (
    id          INTEGER PRIMARY KEY,
    company_key TEXT DEFAULT '',         -- '' = all companies
    state       TEXT NOT NULL,           -- running | done | error
    detail      TEXT DEFAULT '',
    added       INTEGER NOT NULL DEFAULT 0,
    updated     INTEGER NOT NULL DEFAULT 0,
    started_at  TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_company_refresh_key ON company_refresh_runs(company_key);
"""

LESSON_STATES = ("not_started", "in_progress", "completed")
PROBLEM_STATES = ("not_started", "attempted", "solved")

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


def application_by_url(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    """Exact-URL lookup of an application — used to attribute an open browser
    tab (in 'fill all open tabs') back to a tracked job."""
    if not url:
        return None
    return conn.execute(
        """SELECT a.id AS application_id, j.id AS job_id, j.title, j.company
           FROM jobs j JOIN applications a ON a.job_id = j.id
           WHERE j.url = ? LIMIT 1""",
        (url,),
    ).fetchone()


def job_ids_by_key(conn: sqlite3.Connection, keys) -> dict[str, int]:
    """Map pipeline keys (source:company:job_id) → DB job ids, for the keys
    present. Used to make cluster-map points link to their tracked job."""
    keys = list(keys)
    if not keys:
        return {}
    out: dict[str, int] = {}
    # Chunk to stay under SQLite's variable limit on very large reports.
    for start in range(0, len(keys), 400):
        chunk = keys[start:start + 400]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT id, key FROM jobs WHERE key IN ({placeholders})", chunk
        ).fetchall()
        out.update({r["key"]: r["id"] for r in rows})
    return out


def active_application_urls(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """(application_id, url) for every active job — the caller fuzzy-matches an
    open tab's URL against these (e.g. by canonical apply form / ATS job id)."""
    return conn.execute(
        """SELECT a.id AS application_id, j.url
           FROM jobs j JOIN applications a ON a.job_id = j.id
           WHERE j.is_active = 1 AND j.url != ''"""
    ).fetchall()


# Columns the user can sort by. Values are safe SQL column references.
SORTABLE = {
    "fit":        "j.fit_score",
    "company":    "j.company",
    "title":      "j.title",
    "location":   "j.location",
    "posted":     "j.posted_at",
    "first_seen": "j.first_seen_at",
    "status":     "a.status",
}


def search_jobs(
    conn: sqlite3.Connection,
    q: str = "",
    company: str = "",
    stack: str = "",            # "" | "to_apply" | "applied"
    include_near_miss: bool = True,
    sort_by: str = "",          # key from SORTABLE; empty → default rank_score order
    sort_dir: str = "",         # "asc" | "desc"; empty → desc
    min_fit: float | None = None,
    status_filter: str = "",    # exact application status value
    since: str = "",            # show not-applied jobs only if last_seen_at >= this
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
    # Run scope: limit the to-apply pile to jobs the most recent run surfaced,
    # but never hide a job you've already engaged with (in_progress/applied/…)
    # just because a later run targeted different roles.
    if since:
        sql.append("AND (j.last_seen_at >= ? OR a.status != 'not_applied')")
        args.append(since)
    if stack == "applied":
        sql.append(f"AND a.status IN ({','.join('?' * len(APPLIED_SET))})")
        args += sorted(APPLIED_SET)
    elif stack == "in_progress":
        sql.append("AND a.status = 'in_progress'")
    elif stack == "to_apply":
        # Fresh, not-yet-started jobs only — in_progress is its own stack now.
        not_to_apply = APPLIED_SET | {"in_progress"}
        sql.append(f"AND a.status NOT IN ({','.join('?' * len(not_to_apply))})")
        args += sorted(not_to_apply)
    if not include_near_miss:
        sql.append("AND j.filter_reason = ''")
    if min_fit is not None:
        sql.append("AND j.fit_score >= ?")
        args.append(min_fit)
    if status_filter and status_filter in APP_STATUSES:
        sql.append("AND a.status = ?")
        args.append(status_filter)
    if sort_by in SORTABLE:
        col = SORTABLE[sort_by]
        direction = "ASC" if sort_dir == "asc" else "DESC"
        nulls = "NULLS LAST" if direction == "DESC" else "NULLS FIRST"
        sql.append(f"ORDER BY {col} {direction} {nulls}")
    else:
        sql.append("ORDER BY a.status != 'in_progress', j.rank_score DESC NULLS LAST, j.first_seen_at DESC")
    sql.append("LIMIT ?")
    args.append(limit)
    return conn.execute(" ".join(sql), args).fetchall()


def top_fit_to_apply(conn: sqlite3.Connection, n: int = 5) -> list[sqlite3.Row]:
    """The n best-fit jobs that are applyable now: active, have a URL, and not
    yet in an applied/closed state. Highest fit first, rank as tiebreak."""
    placeholders = ",".join("?" * len(APPLIED_SET))
    return conn.execute(
        f"""SELECT j.*, a.id AS application_id, a.status
            FROM jobs j JOIN applications a ON a.job_id = j.id
            WHERE j.is_active = 1 AND j.url != '' AND a.status NOT IN ({placeholders})
            ORDER BY j.fit_score DESC NULLS LAST, j.rank_score DESC NULLS LAST,
                     j.first_seen_at DESC
            LIMIT ?""",
        (*sorted(APPLIED_SET), n),
    ).fetchall()


def companies_for_stack(conn: sqlite3.Connection, stack: str = "") -> list[str]:
    """Distinct companies, scoped to a stack (to_apply / applied) so each
    section's company filter lists only the companies that actually have jobs
    in it. Empty stack → every company."""
    sql = ["SELECT DISTINCT j.company FROM jobs j "
           "JOIN applications a ON a.job_id = j.id WHERE 1=1"]
    args: list = []
    if stack == "applied":
        sql.append(f"AND a.status IN ({','.join('?' * len(APPLIED_SET))})")
        args += sorted(APPLIED_SET)
    elif stack == "in_progress":
        sql.append("AND a.status = 'in_progress'")
    elif stack == "to_apply":
        # Fresh, not-yet-started jobs only — in_progress is its own stack now.
        not_to_apply = APPLIED_SET | {"in_progress"}
        sql.append(f"AND a.status NOT IN ({','.join('?' * len(not_to_apply))})")
        args += sorted(not_to_apply)
    sql.append("ORDER BY j.company")
    return [r["company"] for r in conn.execute(" ".join(sql), args).fetchall()]


def latest_run_ingested_at(conn: sqlite3.Connection) -> str:
    """Ingest timestamp of the most recent run, or '' if none. Jobs that run
    surfaced all carry this exact value in last_seen_at (upsert stamps every
    report job, changed or not), so it's the boundary for 'this run only'."""
    row = conn.execute("SELECT MAX(ingested_at) AS t FROM runs").fetchone()
    return row["t"] if row and row["t"] else ""


def stack_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT a.status, COUNT(*) AS n FROM applications a "
        "JOIN jobs j ON j.id = a.job_id WHERE j.is_active = 1 GROUP BY a.status"
    ).fetchall()
    by_status = {r["status"]: r["n"] for r in rows}
    applied = sum(n for s, n in by_status.items() if s in APPLIED_SET)
    in_progress = by_status.get("in_progress", 0)
    to_apply = sum(n for s, n in by_status.items()
                   if s not in APPLIED_SET and s != "in_progress")
    return {"to_apply": to_apply, "in_progress": in_progress, "applied": applied,
            "by_status": by_status}


# ---------------------------------------------------------- prep queries ---
def prep_tracks_overview(conn: sqlite3.Connection) -> list[dict]:
    """One row per track with totals + completion counts. Drives /prep landing."""
    rows = conn.execute("""
        SELECT
          t.id, t.slug, t.title, t.description,
          (SELECT COUNT(*) FROM prep_modules m WHERE m.track_id = t.id) AS module_count,
          (SELECT COUNT(*) FROM prep_lessons l
            JOIN prep_modules m ON m.id = l.module_id WHERE m.track_id = t.id) AS lesson_count,
          (SELECT COUNT(*) FROM prep_lesson_progress p
            JOIN prep_lessons l ON l.id = p.lesson_id
            JOIN prep_modules m ON m.id = l.module_id
            WHERE m.track_id = t.id AND p.state = 'completed') AS lessons_done,
          (SELECT COUNT(*) FROM prep_problems pr
            JOIN prep_modules m ON m.id = pr.module_id WHERE m.track_id = t.id) AS problem_count,
          (SELECT COUNT(*) FROM prep_problem_progress pp
            JOIN prep_problems pr ON pr.id = pp.problem_id
            JOIN prep_modules m ON m.id = pr.module_id
            WHERE m.track_id = t.id AND pp.state = 'solved') AS problems_done,
          (SELECT COUNT(*) FROM prep_ctci_problems cp
            JOIN prep_modules m ON m.id = cp.module_id WHERE m.track_id = t.id) AS ctci_count,
          (SELECT COUNT(*) FROM prep_ctci_problem_progress cpp
            JOIN prep_ctci_problems cp ON cp.id = cpp.ctci_problem_id
            JOIN prep_modules m ON m.id = cp.module_id
            WHERE m.track_id = t.id AND cpp.state = 'solved') AS ctci_done
        FROM prep_tracks t
        ORDER BY t.sort_order, t.id
    """).fetchall()
    return [dict(r) for r in rows]


def prep_modules_for_track(conn: sqlite3.Connection, track_id: int) -> list[dict]:
    rows = conn.execute("""
        SELECT
          m.id, m.slug, m.title, m.summary, m.source_refs, m.est_minutes,
          (SELECT COUNT(*) FROM prep_lessons l WHERE l.module_id = m.id) AS lesson_count,
          (SELECT COUNT(*) FROM prep_lesson_progress p
            JOIN prep_lessons l ON l.id = p.lesson_id
            WHERE l.module_id = m.id AND p.state = 'completed') AS lessons_done,
          (SELECT COUNT(*) FROM prep_problems pr WHERE pr.module_id = m.id) AS problem_count,
          (SELECT COUNT(*) FROM prep_problem_progress pp
            JOIN prep_problems pr ON pr.id = pp.problem_id
            WHERE pr.module_id = m.id AND pp.state = 'solved') AS problems_done,
          (SELECT COUNT(*) FROM prep_ctci_problems cp WHERE cp.module_id = m.id) AS ctci_count,
          (SELECT COUNT(*) FROM prep_ctci_problem_progress cpp
            JOIN prep_ctci_problems cp ON cp.id = cpp.ctci_problem_id
            WHERE cp.module_id = m.id AND cpp.state = 'solved') AS ctci_done
        FROM prep_modules m
        WHERE m.track_id = ?
        ORDER BY m.sort_order, m.id
    """, (track_id,)).fetchall()
    return [dict(r) for r in rows]


def prep_module_detail(conn: sqlite3.Connection, module_slug: str) -> dict | None:
    module = conn.execute("""
        SELECT m.*, t.slug AS track_slug, t.title AS track_title
        FROM prep_modules m JOIN prep_tracks t ON t.id = m.track_id
        WHERE m.slug = ?
    """, (module_slug,)).fetchone()
    if module is None:
        return None
    lessons = conn.execute("""
        SELECT l.id, l.slug, l.title, l.source_refs, l.sort_order,
               COALESCE(p.state, 'not_started') AS state
        FROM prep_lessons l
        LEFT JOIN prep_lesson_progress p ON p.lesson_id = l.id
        WHERE l.module_id = ?
        ORDER BY l.sort_order, l.id
    """, (module["id"],)).fetchall()
    problems = conn.execute("""
        SELECT pr.*, COALESCE(pp.state, 'not_started') AS state
        FROM prep_problems pr
        LEFT JOIN prep_problem_progress pp ON pp.problem_id = pr.id
        WHERE pr.module_id = ?
        ORDER BY pr.sort_order, pr.id
    """, (module["id"],)).fetchall()
    ctci_problems = conn.execute("""
        SELECT cp.id, cp.slug, cp.ctci_id, cp.title, cp.complexity, cp.sort_order,
               COALESCE(cpp.state, 'not_started') AS state
        FROM prep_ctci_problems cp
        LEFT JOIN prep_ctci_problem_progress cpp ON cpp.ctci_problem_id = cp.id
        WHERE cp.module_id = ?
        ORDER BY cp.sort_order, cp.id
    """, (module["id"],)).fetchall()
    return {
        "module": dict(module),
        "lessons": [dict(r) for r in lessons],
        "problems": [dict(r) for r in problems],
        "ctci_problems": [dict(r) for r in ctci_problems],
    }


def prep_lesson_detail(conn: sqlite3.Connection, module_slug: str, lesson_slug: str) -> dict | None:
    row = conn.execute("""
        SELECT
          l.*, m.slug AS module_slug, m.title AS module_title, m.id AS module_id,
          t.slug AS track_slug, t.title AS track_title,
          COALESCE(p.state, 'not_started') AS state,
          COALESCE(p.notes, '') AS notes
        FROM prep_lessons l
        JOIN prep_modules m ON m.id = l.module_id
        JOIN prep_tracks t ON t.id = m.track_id
        LEFT JOIN prep_lesson_progress p ON p.lesson_id = l.id
        WHERE m.slug = ? AND l.slug = ?
    """, (module_slug, lesson_slug)).fetchone()
    if row is None:
        return None
    siblings = conn.execute("""
        SELECT id, slug, title, sort_order FROM prep_lessons
        WHERE module_id = ? ORDER BY sort_order, id
    """, (row["module_id"],)).fetchall()
    return {"lesson": dict(row), "siblings": [dict(r) for r in siblings]}


def set_lesson_state(conn: sqlite3.Connection, lesson_id: int, state: str,
                     notes: str | None = None) -> None:
    if state not in LESSON_STATES:
        raise ValueError(f"invalid lesson state {state!r}")
    now = utcnow()
    row = conn.execute(
        "SELECT id, state FROM prep_lesson_progress WHERE lesson_id = ?",
        (lesson_id,)).fetchone()
    started_at = now if state in ("in_progress", "completed") else None
    completed_at = now if state == "completed" else None
    if row is None:
        conn.execute(
            """INSERT INTO prep_lesson_progress
                 (lesson_id, state, notes, started_at, completed_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (lesson_id, state, notes or "", started_at, completed_at, now))
    else:
        sets = ["state = ?", "updated_at = ?"]
        args: list = [state, now]
        if notes is not None:
            sets.append("notes = ?")
            args.append(notes)
        if state == "completed":
            sets.append("completed_at = ?")
            args.append(now)
        # Only stamp started_at on the first transition out of not_started so
        # users can see how long they spent on a lesson.
        if row["state"] == "not_started" and state != "not_started":
            sets.append("started_at = ?")
            args.append(now)
        args.append(lesson_id)
        conn.execute(
            f"UPDATE prep_lesson_progress SET {', '.join(sets)} WHERE lesson_id = ?",
            args)
    conn.commit()


def set_problem_state(conn: sqlite3.Connection, problem_id: int, state: str,
                      notes: str | None = None) -> None:
    if state not in PROBLEM_STATES:
        raise ValueError(f"invalid problem state {state!r}")
    now = utcnow()
    row = conn.execute(
        "SELECT id, state FROM prep_problem_progress WHERE problem_id = ?",
        (problem_id,)).fetchone()
    solved_at = now if state == "solved" else None
    if row is None:
        conn.execute(
            """INSERT INTO prep_problem_progress
                 (problem_id, state, notes, solved_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (problem_id, state, notes or "", solved_at, now))
    else:
        sets = ["state = ?", "updated_at = ?"]
        args: list = [state, now]
        if notes is not None:
            sets.append("notes = ?")
            args.append(notes)
        if state == "solved":
            sets.append("solved_at = ?")
            args.append(now)
        args.append(problem_id)
        conn.execute(
            f"UPDATE prep_problem_progress SET {', '.join(sets)} WHERE problem_id = ?",
            args)
    conn.commit()


def prep_ctci_problem_detail(conn: sqlite3.Connection, module_slug: str,
                             problem_slug: str) -> dict | None:
    """Full content + sibling nav for a single CtCI book problem."""
    row = conn.execute("""
        SELECT
          cp.*, m.slug AS module_slug, m.title AS module_title, m.id AS module_id,
          t.slug AS track_slug, t.title AS track_title,
          COALESCE(cpp.state, 'not_started') AS state,
          COALESCE(cpp.notes, '') AS notes
        FROM prep_ctci_problems cp
        JOIN prep_modules m ON m.id = cp.module_id
        JOIN prep_tracks t ON t.id = m.track_id
        LEFT JOIN prep_ctci_problem_progress cpp ON cpp.ctci_problem_id = cp.id
        WHERE m.slug = ? AND cp.slug = ?
    """, (module_slug, problem_slug)).fetchone()
    if row is None:
        return None
    siblings = conn.execute("""
        SELECT id, slug, ctci_id, title, sort_order FROM prep_ctci_problems
        WHERE module_id = ? ORDER BY sort_order, id
    """, (row["module_id"],)).fetchall()
    return {"problem": dict(row), "siblings": [dict(r) for r in siblings]}


def set_ctci_problem_state(conn: sqlite3.Connection, ctci_problem_id: int,
                           state: str, notes: str | None = None) -> None:
    if state not in PROBLEM_STATES:
        raise ValueError(f"invalid ctci problem state {state!r}")
    now = utcnow()
    row = conn.execute(
        "SELECT id, state FROM prep_ctci_problem_progress WHERE ctci_problem_id = ?",
        (ctci_problem_id,)).fetchone()
    solved_at = now if state == "solved" else None
    if row is None:
        conn.execute(
            """INSERT INTO prep_ctci_problem_progress
                 (ctci_problem_id, state, notes, solved_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (ctci_problem_id, state, notes or "", solved_at, now))
    else:
        sets = ["state = ?", "updated_at = ?"]
        args: list = [state, now]
        if notes is not None:
            sets.append("notes = ?")
            args.append(notes)
        if state == "solved":
            sets.append("solved_at = ?")
            args.append(now)
        args.append(ctci_problem_id)
        conn.execute(
            f"UPDATE prep_ctci_problem_progress SET {', '.join(sets)} WHERE ctci_problem_id = ?",
            args)
    conn.commit()


def prep_resume_target(conn: sqlite3.Connection) -> dict | None:
    """The "resume where you left off" hook on the /prep landing. Returns the
    most-recently-touched in-progress lesson, or — failing that — the first
    not_started lesson, or None if everything is done."""
    row = conn.execute("""
        SELECT m.slug AS module_slug, l.slug AS lesson_slug, l.title AS lesson_title,
               m.title AS module_title, t.title AS track_title, 'in_progress' AS source
        FROM prep_lesson_progress p
        JOIN prep_lessons l ON l.id = p.lesson_id
        JOIN prep_modules m ON m.id = l.module_id
        JOIN prep_tracks t ON t.id = m.track_id
        WHERE p.state = 'in_progress'
        ORDER BY p.updated_at DESC LIMIT 1
    """).fetchone()
    if row:
        return dict(row)
    row = conn.execute("""
        SELECT m.slug AS module_slug, l.slug AS lesson_slug, l.title AS lesson_title,
               m.title AS module_title, t.title AS track_title, 'next' AS source
        FROM prep_lessons l
        JOIN prep_modules m ON m.id = l.module_id
        JOIN prep_tracks t ON t.id = m.track_id
        LEFT JOIN prep_lesson_progress p ON p.lesson_id = l.id
        WHERE COALESCE(p.state, 'not_started') = 'not_started'
        ORDER BY t.sort_order, m.sort_order, l.sort_order LIMIT 1
    """).fetchone()
    return dict(row) if row else None


def prep_overall_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Headline numbers for the nav badge — total + completed lessons."""
    rows = conn.execute("""
        SELECT
          (SELECT COUNT(*) FROM prep_lessons) AS lessons_total,
          (SELECT COUNT(*) FROM prep_lesson_progress WHERE state = 'completed') AS lessons_done,
          (SELECT COUNT(*) FROM prep_problems) AS problems_total,
          (SELECT COUNT(*) FROM prep_problem_progress WHERE state = 'solved') AS problems_done,
          (SELECT COUNT(*) FROM prep_ctci_problems) AS ctci_total,
          (SELECT COUNT(*) FROM prep_ctci_problem_progress WHERE state = 'solved') AS ctci_done
    """).fetchone()
    return dict(rows) if rows else {
        "lessons_total": 0, "lessons_done": 0,
        "problems_total": 0, "problems_done": 0,
        "ctci_total": 0, "ctci_done": 0,
    }


# ----------------------------------------------- company LeetCode questions ---
def upsert_company_problem(conn: sqlite3.Connection, rec: dict,
                           now: str | None = None) -> str:
    """Insert or refresh one company problem (keyed by company_key + slug).
    Returns 'inserted' or 'updated'. Commits are batched by the caller."""
    now = now or utcnow()
    row = conn.execute(
        "SELECT id FROM company_problems WHERE company_key = ? AND leetcode_slug = ?",
        (rec["company_key"], rec["leetcode_slug"])).fetchone()
    params = {
        "company": rec["company"], "company_key": rec["company_key"],
        "leetcode_number": rec.get("leetcode_number"),
        "leetcode_slug": rec["leetcode_slug"], "title": rec["title"],
        "difficulty": rec.get("difficulty", "medium"),
        "frequency": float(rec.get("frequency", 0) or 0),
        "timeframe": rec.get("timeframe", ""), "topics": rec.get("topics", ""),
        "url": rec.get("url", ""), "source": rec.get("source", "bundled"),
    }
    if row is None:
        conn.execute(
            """INSERT INTO company_problems
                 (company, company_key, leetcode_number, leetcode_slug, title,
                  difficulty, frequency, timeframe, topics, url, source,
                  first_seen_at, last_refreshed_at)
               VALUES (:company, :company_key, :leetcode_number, :leetcode_slug,
                       :title, :difficulty, :frequency, :timeframe, :topics,
                       :url, :source, :now, :now)""",
            {**params, "now": now})
        return "inserted"
    conn.execute(
        """UPDATE company_problems SET
             company = :company, leetcode_number = :leetcode_number,
             title = :title, difficulty = :difficulty, frequency = :frequency,
             timeframe = :timeframe, topics = :topics, url = :url,
             source = :source, last_refreshed_at = :now
           WHERE id = :id""",
        {**params, "now": now, "id": row["id"]})
    return "updated"


def seed_company_problems(conn: sqlite3.Connection, records: list[dict]) -> dict:
    """Bulk-upsert curated/bundled company problems. Idempotent and
    progress-preserving (upsert by natural key keeps ids). Returns counts."""
    now = utcnow()
    inserted = updated = 0
    for rec in records:
        if upsert_company_problem(conn, rec, now) == "inserted":
            inserted += 1
        else:
            updated += 1
    conn.commit()
    return {"inserted": inserted, "updated": updated, "total": len(records)}


def companies_overview(conn: sqlite3.Connection) -> list[dict]:
    """One row per company with question + solved counts, busiest first.
    Drives the /companies landing."""
    rows = conn.execute("""
        SELECT cp.company_key,
               MIN(cp.company) AS company,
               COUNT(*) AS problem_count,
               SUM(CASE WHEN cp.difficulty = 'easy' THEN 1 ELSE 0 END) AS easy,
               SUM(CASE WHEN cp.difficulty = 'medium' THEN 1 ELSE 0 END) AS medium,
               SUM(CASE WHEN cp.difficulty = 'hard' THEN 1 ELSE 0 END) AS hard,
               SUM(CASE WHEN pr.state = 'solved' THEN 1 ELSE 0 END) AS solved,
               MAX(cp.last_refreshed_at) AS last_refreshed_at,
               MAX(CASE WHEN cp.source != 'bundled' THEN 1 ELSE 0 END) AS refreshed
        FROM company_problems cp
        LEFT JOIN company_problem_progress pr ON pr.company_problem_id = cp.id
        GROUP BY cp.company_key
        ORDER BY problem_count DESC, company COLLATE NOCASE
    """).fetchall()
    return [dict(r) for r in rows]


def company_problems_for(conn: sqlite3.Connection, company_key: str,
                         difficulty: str = "", limit: int = 0) -> list[dict]:
    """A company's questions (most-asked first) with solve state joined."""
    sql = ["""SELECT cp.*, COALESCE(pr.state, 'not_started') AS state
              FROM company_problems cp
              LEFT JOIN company_problem_progress pr ON pr.company_problem_id = cp.id
              WHERE cp.company_key = ?"""]
    args: list = [company_key]
    if difficulty in ("easy", "medium", "hard"):
        sql.append("AND cp.difficulty = ?")
        args.append(difficulty)
    sql.append("ORDER BY cp.frequency DESC, cp.leetcode_number")
    if limit:
        sql.append("LIMIT ?")
        args.append(limit)
    return [dict(r) for r in conn.execute(" ".join(sql), args).fetchall()]


def company_problem_count(conn: sqlite3.Connection, company_key: str) -> int:
    """Row count for a company without loading/dict-ifying every problem —
    used where only the total is needed (page CTAs, the unfiltered count)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM company_problems WHERE company_key = ?",
        (company_key,)).fetchone()
    return row["n"] if row else 0


def company_display_name(conn: sqlite3.Connection, company_key: str) -> str:
    row = conn.execute(
        "SELECT company FROM company_problems WHERE company_key = ? LIMIT 1",
        (company_key,)).fetchone()
    return row["company"] if row else company_key.title()


def set_company_problem_state(conn: sqlite3.Connection, problem_id: int,
                              state: str, notes: str | None = None) -> None:
    if state not in PROBLEM_STATES:
        raise ValueError(f"invalid company problem state {state!r}")
    now = utcnow()
    row = conn.execute(
        "SELECT id FROM company_problem_progress WHERE company_problem_id = ?",
        (problem_id,)).fetchone()
    solved_at = now if state == "solved" else None
    if row is None:
        conn.execute(
            """INSERT INTO company_problem_progress
                 (company_problem_id, state, notes, solved_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (problem_id, state, notes or "", solved_at, now))
    else:
        sets = ["state = ?", "updated_at = ?"]
        args: list = [state, now]
        if notes is not None:
            sets.append("notes = ?")
            args.append(notes)
        if state == "solved":
            sets.append("solved_at = ?")
            args.append(now)
        args.append(problem_id)
        conn.execute(
            f"UPDATE company_problem_progress SET {', '.join(sets)} "
            "WHERE company_problem_id = ?", args)
    conn.commit()


def company_overall_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Headline numbers for the nav badge — distinct companies + solved/total."""
    row = conn.execute("""
        SELECT
          (SELECT COUNT(DISTINCT company_key) FROM company_problems) AS companies,
          (SELECT COUNT(*) FROM company_problems) AS problems_total,
          (SELECT COUNT(*) FROM company_problem_progress WHERE state = 'solved')
            AS problems_done
    """).fetchone()
    return dict(row) if row else {"companies": 0, "problems_total": 0,
                                  "problems_done": 0}


# --- company question refresh runs (mirror referral_runs) -------------------
def start_company_refresh(conn: sqlite3.Connection, company_key: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO company_refresh_runs (company_key, state, started_at) "
        "VALUES (?, 'running', ?)", (company_key, utcnow()))
    conn.commit()
    return cur.lastrowid


def finish_company_refresh(conn: sqlite3.Connection, run_id: int, *,
                           added: int = 0, updated: int = 0,
                           detail: str = "") -> None:
    conn.execute(
        """UPDATE company_refresh_runs
             SET state = 'done', added = ?, updated = ?, detail = ?,
                 finished_at = ?
           WHERE id = ?""",
        (added, updated, detail, utcnow(), run_id))
    conn.commit()


def fail_company_refresh(conn: sqlite3.Connection, run_id: int,
                         detail: str) -> None:
    conn.execute(
        "UPDATE company_refresh_runs SET state = 'error', detail = ?, "
        "finished_at = ? WHERE id = ?", (detail[:500], utcnow(), run_id))
    conn.commit()


def latest_company_refresh(conn: sqlite3.Connection,
                           company_key: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM company_refresh_runs WHERE company_key IN (?, '') "
        "ORDER BY id DESC LIMIT 1", (company_key,)).fetchone()


def company_refresh_running(conn: sqlite3.Connection, company_key: str) -> bool:
    """True if a refresh covering this company (specific or all) is in flight."""
    row = latest_company_refresh(conn, company_key)
    return bool(row and row["state"] == "running")
