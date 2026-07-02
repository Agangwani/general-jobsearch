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
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jobsearch.utils import normalize_company_name

# Sentinel owner id for single-user / local mode. Per-user (hosted) rows use the
# Supabase auth UUID instead; per-user columns default to this so local behavior
# is completely unchanged (one implicit user).
LOCAL_USER_ID = "local"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY,
    user_id         TEXT NOT NULL DEFAULT 'local',   -- owner (Stage 2a data isolation)
    key             TEXT NOT NULL,
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
    is_active       INTEGER NOT NULL DEFAULT 1,
    -- 1 when this job's company is a known startup (in startup_companies); set
    -- by ingest so the dashboard can show only / hide / mix startup jobs.
    is_startup      INTEGER NOT NULL DEFAULT 0,
    -- Per-user uniqueness: the pipeline's source:company:job_id key is unique
    -- within an owner, so two tenants can each hold the same posting.
    UNIQUE(user_id, key)
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_startup ON jobs(is_startup);

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
    user_id    TEXT NOT NULL DEFAULT 'local',   -- owner of this field (Stage 2b)
    field      TEXT NOT NULL,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, field)
);

-- Per-user resume text (Stage 2b): the durable, hosted-safe store the pipeline
-- scores against — the filesystem is ephemeral on hosted deploys, so the raw
-- resume can't live only in data/resume.txt. One row per user; pdf_name lets
-- auto-apply attach the resume under its original filename.
CREATE TABLE IF NOT EXISTS user_resumes (
    user_id     TEXT PRIMARY KEY DEFAULT 'local',
    resume_text TEXT NOT NULL DEFAULT '',
    pdf_name    TEXT DEFAULT '',
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY,
    ingested_at   TEXT NOT NULL,
    report_date   TEXT DEFAULT '',
    jobs_inserted INTEGER NOT NULL DEFAULT 0,
    jobs_updated  INTEGER NOT NULL DEFAULT 0,
    jobs_total    INTEGER NOT NULL DEFAULT 0
);

-- --------------------------------------------------- startup company facts ---
-- The "helpful info" the startup pipeline tracks per company (employees,
-- funding stage/amount, investors, notable people, …). Populated by ingest
-- from data/startup_meta.json (written by `discover-startups`) and editable in
-- the UI; user_edited=1 protects manual edits from being clobbered on re-ingest.
-- Keyed by normalized company name so it joins jobs.company across spellings.
CREATE TABLE IF NOT EXISTS startup_companies (
    id                INTEGER PRIMARY KEY,
    user_id           TEXT NOT NULL DEFAULT 'local',   -- owner (Stage 2a data isolation)
    company_key       TEXT NOT NULL,
    name              TEXT NOT NULL,
    employees         TEXT DEFAULT '',
    founded           TEXT DEFAULT '',
    batch             TEXT DEFAULT '',
    status            TEXT DEFAULT '',
    stage             TEXT DEFAULT '',
    last_round        TEXT DEFAULT '',
    last_round_amount TEXT DEFAULT '',
    total_raised      TEXT DEFAULT '',
    investors         TEXT DEFAULT '',   -- JSON array
    notable_people    TEXT DEFAULT '',   -- JSON array
    industry          TEXT DEFAULT '',
    tags              TEXT DEFAULT '',   -- JSON array
    location          TEXT DEFAULT '',
    website           TEXT DEFAULT '',
    one_liner         TEXT DEFAULT '',
    description       TEXT DEFAULT '',
    top_company       INTEGER NOT NULL DEFAULT 0,
    is_hiring         INTEGER NOT NULL DEFAULT 0,
    yc_url            TEXT DEFAULT '',
    source            TEXT DEFAULT '',
    notes             TEXT DEFAULT '',
    user_edited       INTEGER NOT NULL DEFAULT 0,
    updated_at        TEXT NOT NULL,
    UNIQUE(user_id, company_key)
);
CREATE INDEX IF NOT EXISTS idx_startup_companies_key ON startup_companies(user_id, company_key);

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
    "current_role"    TEXT DEFAULT '',   -- quoted: reserved keyword in Postgres
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
    user_id      TEXT NOT NULL DEFAULT 'local',
    lesson_id    INTEGER NOT NULL REFERENCES prep_lessons(id),
    state        TEXT NOT NULL DEFAULT 'not_started',
    notes        TEXT DEFAULT '',
    started_at   TEXT,
    completed_at TEXT,
    updated_at   TEXT NOT NULL,
    UNIQUE(user_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS prep_problem_progress (
    id           INTEGER PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'local',
    problem_id   INTEGER NOT NULL REFERENCES prep_problems(id),
    state        TEXT NOT NULL DEFAULT 'not_started',  -- not_started | attempted | solved
    notes        TEXT DEFAULT '',
    solved_at    TEXT,
    updated_at   TEXT NOT NULL,
    UNIQUE(user_id, problem_id)
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
    user_id         TEXT NOT NULL DEFAULT 'local',
    ctci_problem_id INTEGER NOT NULL REFERENCES prep_ctci_problems(id),
    state           TEXT NOT NULL DEFAULT 'not_started',
    notes           TEXT DEFAULT '',
    solved_at       TEXT,
    updated_at      TEXT NOT NULL,
    UNIQUE(user_id, ctci_problem_id)
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
    user_id            TEXT NOT NULL DEFAULT 'local',
    company_problem_id INTEGER NOT NULL REFERENCES company_problems(id),
    state              TEXT NOT NULL DEFAULT 'not_started',  -- not_started | attempted | solved
    notes              TEXT DEFAULT '',
    solved_at          TEXT,
    updated_at         TEXT NOT NULL,
    UNIQUE(user_id, company_problem_id)
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

-- ------------------------------------------------------- hosted-mode accounts ---
-- Only used when the app runs behind Supabase Auth (hosted mode; webapp/auth.py).
-- `id` is the Supabase auth user UUID. Local single-user mode never writes here.
-- Until per-user data isolation (Stage 2b) every account would share one dataset,
-- so signups are gated to the first (owner) account.
CREATE TABLE IF NOT EXISTS app_users (
    id            TEXT PRIMARY KEY,            -- Supabase auth user id (UUID)
    email         TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    last_login_at TEXT
);

-- ------------------------------------------------- company registry ---
-- The set of companies each user's pipeline searches, per track (main vs
-- startups) — previously only in the gitignored YAML registries
-- (config/companies.yaml + data/companies.discovered.yaml, and the startups
-- equivalents). One row per (user_id, track, company_key). `source`
-- distinguishes the curated seed from resume-discovered entries; the
-- search-state columns (last_searched_at, last_found_jobs) let discovery
-- prioritize fresh, not-recently-searched companies. Populated by ingest from
-- each track's live registry; user_edited=1 protects UI edits from re-sync.
-- Keyed by normalize_company_name so it joins jobs.company / startup_companies.
CREATE TABLE IF NOT EXISTS companies (
    id               INTEGER PRIMARY KEY,
    user_id          TEXT NOT NULL DEFAULT 'local',
    track            TEXT NOT NULL DEFAULT 'main',   -- main | startups
    company_key      TEXT NOT NULL,                  -- normalize_company_name(name)
    name             TEXT NOT NULL,
    ats              TEXT NOT NULL DEFAULT '',
    careers_url      TEXT DEFAULT '',
    tags             TEXT DEFAULT '',                -- JSON array
    params           TEXT DEFAULT '',                -- JSON object (ATS fetcher params)
    source           TEXT NOT NULL DEFAULT 'curated',-- curated | discovered
    discovered_via   TEXT DEFAULT '',                -- audit: which source(s) + how
    enabled          INTEGER NOT NULL DEFAULT 1,
    first_seen_at    TEXT NOT NULL,
    last_searched_at TEXT DEFAULT '',
    last_found_jobs  INTEGER NOT NULL DEFAULT 0,
    user_edited      INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL,
    UNIQUE(user_id, track, company_key)
);
CREATE INDEX IF NOT EXISTS idx_companies_user_track ON companies(user_id, track, enabled);
CREATE INDEX IF NOT EXISTS idx_companies_sweep ON companies(user_id, track, last_searched_at);

-- Append-only log of each registry-sync / discovery run per track (freshness
-- history + auditing). Mirrors company_refresh_runs / referral_runs: no UNIQUE.
CREATE TABLE IF NOT EXISTS company_search_runs (
    id                 INTEGER PRIMARY KEY,
    user_id            TEXT NOT NULL DEFAULT 'local',
    track              TEXT NOT NULL DEFAULT 'main',
    ran_at             TEXT NOT NULL,
    source             TEXT NOT NULL DEFAULT 'ingest',  -- ingest | discovery
    companies_total    INTEGER NOT NULL DEFAULT 0,
    companies_new      INTEGER NOT NULL DEFAULT 0,
    companies_disabled INTEGER NOT NULL DEFAULT 0,
    jobs_found         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_company_search_runs ON company_search_runs(user_id, track, ran_at);
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


def _require_row(conn: sqlite3.Connection, table: str, row_id: int) -> None:
    """Guard a state-change setter against a stale/unknown parent id.

    The status/progress setters below UPDATE a parent row (a no-op for an
    unknown id, no error) and then INSERT an event/progress row whose FK
    references that parent. For an id with no parent row the INSERT violates
    the FK — raising sqlite3.IntegrityError on SQLite or psycopg.errors.*
    on Postgres, and (on Postgres) poisoning the open transaction. Rather than
    catch a dialect-specific error after the fact, we check the parent exists
    up front and raise ValueError when it doesn't. Every caller already turns a
    ValueError into a 303 redirect (mirroring the bad-state-value path), so a
    stale id is a clean no-op in both backends instead of an HTTP 500.

    ``table`` is a fixed internal literal (never user input), so interpolating
    it into the SQL is safe.
    """
    if conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone() is None:
        raise ValueError(f"no {table} row with id {row_id!r}")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path):
    """Open the application database.

    Defaults to local SQLite at ``path`` (the single-user, on-your-machine
    product). When ``JOBSEARCH_DATABASE_URL`` is set — hosted deployments, see
    ``docs/design-hosting.md`` — it connects to that Postgres database instead
    and ``path`` is ignored. Both backends expose the same connection API to the
    rest of the app (see ``webapp/pgcompat.py``)."""
    url = os.environ.get("JOBSEARCH_DATABASE_URL")
    if url:
        from .pgcompat import connect_postgres, sqlite_schema_to_postgres
        conn = connect_postgres(url)
        conn.executescript(sqlite_schema_to_postgres(SCHEMA))
        return conn
    return _connect_sqlite(path)


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive, idempotent column top-ups for DBs created before a column
    existed (CREATE TABLE IF NOT EXISTS won't add columns to an existing table).
    Same philosophy as profile.ensure_fields — never destructive."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "is_startup" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN is_startup INTEGER NOT NULL DEFAULT 0")
    # Per-user scoping. Existing single-user DBs gain a user_id column on each
    # per-user table, defaulting to the local owner, so all current rows belong
    # to 'local'. The old single-column UNIQUE constraints stay (harmless with
    # one local user — SQLite can't drop an inline UNIQUE via ALTER); the code
    # scopes by (user_id, …) explicitly rather than relying on them. Fresh DBs
    # get the composite UNIQUE from SCHEMA; hosted Postgres uses the migrations.
    # Stage 2b: profile + prep/company progress.
    # Stage 2a: the job/application/startup data itself.
    for tbl in ("profile_fields", "prep_lesson_progress", "prep_problem_progress",
                "prep_ctci_problem_progress", "company_problem_progress",
                "jobs", "startup_companies"):
        tcols = {r["name"] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
        if "user_id" not in tcols:
            conn.execute(
                f"ALTER TABLE {tbl} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'")
    conn.commit()


def upsert_job(conn: sqlite3.Connection, record: dict, now: str | None = None,
               user_id: str = LOCAL_USER_ID) -> str:
    """Insert a job or patch an existing one, scoped to ``user_id``. Returns
    'inserted', 'updated', or 'unchanged'. Every change is recorded in
    job_events. The pipeline key is unique within an owner, so two users can
    each hold the same posting."""
    now = now or utcnow()
    row = conn.execute("SELECT * FROM jobs WHERE user_id = ? AND key = ?",
                       (user_id, record["key"])).fetchone()
    if row is None:
        conn.execute(
            """INSERT INTO jobs (user_id, key, source, company, title, location, url,
                                 description, posted_at, fit_score, rank_score,
                                 cluster, filter_reason, validation,
                                 validation_note, first_seen_at, last_seen_at)
               VALUES (:user_id, :key, :source, :company, :title, :location, :url,
                       :description, :posted_at, :fit_score, :rank_score,
                       :cluster, :filter_reason, :validation,
                       :validation_note, :now, :now)""",
            {**_defaults(record), "user_id": user_id, "now": now},
        )
        job_id = conn.execute("SELECT id FROM jobs WHERE user_id = ? AND key = ?",
                              (user_id, record["key"])).fetchone()["id"]
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
    detail: str = "", via: str = "", user_id: str = LOCAL_USER_ID,
) -> None:
    # A stale/unknown id would no-op the UPDATE but fail the application_events
    # FK on INSERT (a 500); raise ValueError so callers redirect instead. The
    # jobs-ownership join also rejects a forged id that belongs to another user
    # (applications is scoped transitively through job_id → jobs.user_id).
    if conn.execute(
        "SELECT 1 FROM applications a JOIN jobs j ON j.id = a.job_id "
        "WHERE a.id = ? AND j.user_id = ?", (application_id, user_id)).fetchone() is None:
        raise ValueError(f"no application {application_id!r} for user {user_id!r}")
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


def job_with_application(conn: sqlite3.Connection, job_id: int,
                         user_id: str = LOCAL_USER_ID) -> sqlite3.Row | None:
    # ``job_id`` arrives from a URL path param, and FastAPI's ``int`` accepts an
    # arbitrary-precision Python integer. SQLite's INTEGER is signed 64-bit, so
    # an id outside that range raises OverflowError rather than just missing.
    # Treat any out-of-range id as "no such job" so the routes (job detail,
    # referrals, cluster view) degrade to their existing not-found redirect
    # instead of returning HTTP 500. The user_id scope also makes another
    # tenant's job id read as not-found.
    if not (-(2 ** 63) <= job_id < 2 ** 63):
        return None
    return conn.execute(
        """SELECT j.*, a.id AS application_id, a.status, a.applied_at,
                  a.submitted_via, a.notes
           FROM jobs j JOIN applications a ON a.job_id = j.id
           WHERE j.id = ? AND j.user_id = ?""",
        (job_id, user_id),
    ).fetchone()


def application_by_url(conn: sqlite3.Connection, url: str,
                       user_id: str = LOCAL_USER_ID) -> sqlite3.Row | None:
    """Exact-URL lookup of an application — used to attribute an open browser
    tab (in 'fill all open tabs') back to a tracked job."""
    if not url:
        return None
    return conn.execute(
        """SELECT a.id AS application_id, j.id AS job_id, j.title, j.company
           FROM jobs j JOIN applications a ON a.job_id = j.id
           WHERE j.url = ? AND j.user_id = ? LIMIT 1""",
        (url, user_id),
    ).fetchone()


def job_ids_by_key(conn: sqlite3.Connection, keys,
                   user_id: str = LOCAL_USER_ID) -> dict[str, int]:
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
            f"SELECT id, key FROM jobs WHERE user_id = ? AND key IN ({placeholders})",
            [user_id, *chunk],
        ).fetchall()
        out.update({r["key"]: r["id"] for r in rows})
    return out


def active_application_urls(conn: sqlite3.Connection,
                            user_id: str = LOCAL_USER_ID) -> list[sqlite3.Row]:
    """(application_id, url) for every active job — the caller fuzzy-matches an
    open tab's URL against these (e.g. by canonical apply form / ATS job id)."""
    return conn.execute(
        """SELECT a.id AS application_id, j.url
           FROM jobs j JOIN applications a ON a.job_id = j.id
           WHERE j.is_active = 1 AND j.url != '' AND j.user_id = ?""",
        (user_id,),
    ).fetchall()


def like_term(q: str) -> str:
    """Build a safe ``LIKE`` pattern for a user search term.

    User-supplied text is a literal substring, not a pattern, so escape the
    LIKE metacharacters ``%`` and ``_`` (and the escape char itself) and wrap
    in ``%…%``. Callers must pair this with ``ESCAPE '\\'`` in the SQL so a
    typed ``%`` matches a literal percent instead of "anything". Without this,
    ``q='%'`` returns every row and ``q='N_w'`` matches "New …"."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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
    startup_scope: str = "",    # "" | "all" (both) | "only" (startups) | "hide"
    limit: int = 500,
    user_id: str = LOCAL_USER_ID,
) -> list[sqlite3.Row]:
    sql = [
        """SELECT j.*, a.id AS application_id, a.status, a.applied_at
           FROM jobs j JOIN applications a ON a.job_id = j.id WHERE 1=1"""
    ]
    args: list = []
    sql.append("AND j.user_id = ?")
    args.append(user_id)
    if startup_scope == "only":
        sql.append("AND j.is_startup = 1")
    elif startup_scope == "hide":
        sql.append("AND j.is_startup = 0")
    if q:
        sql.append("AND (j.title LIKE ? ESCAPE '\\' OR j.description LIKE ? ESCAPE '\\' "
                   "OR j.company LIKE ? ESCAPE '\\' OR j.location LIKE ? ESCAPE '\\')")
        args += [like_term(q)] * 4
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


def top_fit_to_apply(conn: sqlite3.Connection, n: int = 5,
                     user_id: str = LOCAL_USER_ID) -> list[sqlite3.Row]:
    """The n best-fit jobs that are applyable now: active, have a URL, and not
    yet in an applied/closed state. Highest fit first, rank as tiebreak."""
    placeholders = ",".join("?" * len(APPLIED_SET))
    return conn.execute(
        f"""SELECT j.*, a.id AS application_id, a.status
            FROM jobs j JOIN applications a ON a.job_id = j.id
            WHERE j.user_id = ? AND j.is_active = 1 AND j.url != ''
                  AND a.status NOT IN ({placeholders})
            ORDER BY j.fit_score DESC NULLS LAST, j.rank_score DESC NULLS LAST,
                     j.first_seen_at DESC
            LIMIT ?""",
        (user_id, *sorted(APPLIED_SET), n),
    ).fetchall()


def companies_for_stack(conn: sqlite3.Connection, stack: str = "",
                        user_id: str = LOCAL_USER_ID) -> list[str]:
    """Distinct companies, scoped to a stack (to_apply / applied) so each
    section's company filter lists only the companies that actually have jobs
    in it. Empty stack → every company."""
    sql = ["SELECT DISTINCT j.company FROM jobs j "
           "JOIN applications a ON a.job_id = j.id WHERE 1=1"]
    args: list = []
    sql.append("AND j.user_id = ?")
    args.append(user_id)
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


def _stack_of(status: str) -> str:
    if status in APPLIED_SET:
        return "applied"
    if status == "in_progress":
        return "in_progress"
    return "to_apply"


def stack_counts(conn: sqlite3.Connection, user_id: str = LOCAL_USER_ID) -> dict:
    """Per-stack counts (to_apply / in_progress / applied), split into startup
    vs. non-startup so the home page's big numbers can distinguish the two.
    Keeps the flat to_apply/in_progress/applied keys for backward compatibility;
    adds `startup` and `other` sub-dicts and their totals."""
    rows = conn.execute(
        "SELECT a.status, j.is_startup AS su, COUNT(*) AS n FROM applications a "
        "JOIN jobs j ON j.id = a.job_id WHERE j.is_active = 1 AND j.user_id = ? "
        "GROUP BY a.status, j.is_startup",
        (user_id,),
    ).fetchall()
    zero = {"to_apply": 0, "in_progress": 0, "applied": 0}
    out: dict = {**zero, "by_status": {},
                 "startup": dict(zero), "other": dict(zero)}
    for r in rows:
        stack = _stack_of(r["status"])
        side = "startup" if r["su"] else "other"
        out[stack] += r["n"]
        out[side][stack] += r["n"]
        out["by_status"][r["status"]] = out["by_status"].get(r["status"], 0) + r["n"]
    out["startup_total"] = sum(out["startup"].values())
    out["other_total"] = sum(out["other"].values())
    return out


# ---------------------------------------------------------- prep queries ---
def prep_tracks_overview(conn: sqlite3.Connection,
                         user_id: str = LOCAL_USER_ID) -> list[dict]:
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
            WHERE m.track_id = t.id AND p.state = 'completed' AND p.user_id = :uid) AS lessons_done,
          (SELECT COUNT(*) FROM prep_problems pr
            JOIN prep_modules m ON m.id = pr.module_id WHERE m.track_id = t.id) AS problem_count,
          (SELECT COUNT(*) FROM prep_problem_progress pp
            JOIN prep_problems pr ON pr.id = pp.problem_id
            JOIN prep_modules m ON m.id = pr.module_id
            WHERE m.track_id = t.id AND pp.state = 'solved' AND pp.user_id = :uid) AS problems_done,
          (SELECT COUNT(*) FROM prep_ctci_problems cp
            JOIN prep_modules m ON m.id = cp.module_id WHERE m.track_id = t.id) AS ctci_count,
          (SELECT COUNT(*) FROM prep_ctci_problem_progress cpp
            JOIN prep_ctci_problems cp ON cp.id = cpp.ctci_problem_id
            JOIN prep_modules m ON m.id = cp.module_id
            WHERE m.track_id = t.id AND cpp.state = 'solved' AND cpp.user_id = :uid) AS ctci_done
        FROM prep_tracks t
        ORDER BY t.sort_order, t.id
    """, {"uid": user_id}).fetchall()
    return [dict(r) for r in rows]


def prep_modules_for_track(conn: sqlite3.Connection, track_id: int,
                           user_id: str = LOCAL_USER_ID) -> list[dict]:
    rows = conn.execute("""
        SELECT
          m.id, m.slug, m.title, m.summary, m.source_refs, m.est_minutes,
          (SELECT COUNT(*) FROM prep_lessons l WHERE l.module_id = m.id) AS lesson_count,
          (SELECT COUNT(*) FROM prep_lesson_progress p
            JOIN prep_lessons l ON l.id = p.lesson_id
            WHERE l.module_id = m.id AND p.state = 'completed' AND p.user_id = :uid) AS lessons_done,
          (SELECT COUNT(*) FROM prep_problems pr WHERE pr.module_id = m.id) AS problem_count,
          (SELECT COUNT(*) FROM prep_problem_progress pp
            JOIN prep_problems pr ON pr.id = pp.problem_id
            WHERE pr.module_id = m.id AND pp.state = 'solved' AND pp.user_id = :uid) AS problems_done,
          (SELECT COUNT(*) FROM prep_ctci_problems cp WHERE cp.module_id = m.id) AS ctci_count,
          (SELECT COUNT(*) FROM prep_ctci_problem_progress cpp
            JOIN prep_ctci_problems cp ON cp.id = cpp.ctci_problem_id
            WHERE cp.module_id = m.id AND cpp.state = 'solved' AND cpp.user_id = :uid) AS ctci_done
        FROM prep_modules m
        WHERE m.track_id = :track_id
        ORDER BY m.sort_order, m.id
    """, {"track_id": track_id, "uid": user_id}).fetchall()
    return [dict(r) for r in rows]


def prep_module_detail(conn: sqlite3.Connection, module_slug: str,
                       user_id: str = LOCAL_USER_ID) -> dict | None:
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
        LEFT JOIN prep_lesson_progress p ON p.lesson_id = l.id AND p.user_id = :uid
        WHERE l.module_id = :mid
        ORDER BY l.sort_order, l.id
    """, {"mid": module["id"], "uid": user_id}).fetchall()
    problems = conn.execute("""
        SELECT pr.*, COALESCE(pp.state, 'not_started') AS state
        FROM prep_problems pr
        LEFT JOIN prep_problem_progress pp ON pp.problem_id = pr.id AND pp.user_id = :uid
        WHERE pr.module_id = :mid
        ORDER BY pr.sort_order, pr.id
    """, {"mid": module["id"], "uid": user_id}).fetchall()
    ctci_problems = conn.execute("""
        SELECT cp.id, cp.slug, cp.ctci_id, cp.title, cp.complexity, cp.sort_order,
               COALESCE(cpp.state, 'not_started') AS state
        FROM prep_ctci_problems cp
        LEFT JOIN prep_ctci_problem_progress cpp ON cpp.ctci_problem_id = cp.id AND cpp.user_id = :uid
        WHERE cp.module_id = :mid
        ORDER BY cp.sort_order, cp.id
    """, {"mid": module["id"], "uid": user_id}).fetchall()
    return {
        "module": dict(module),
        "lessons": [dict(r) for r in lessons],
        "problems": [dict(r) for r in problems],
        "ctci_problems": [dict(r) for r in ctci_problems],
    }


def prep_lesson_detail(conn: sqlite3.Connection, module_slug: str, lesson_slug: str,
                       user_id: str = LOCAL_USER_ID) -> dict | None:
    row = conn.execute("""
        SELECT
          l.*, m.slug AS module_slug, m.title AS module_title, m.id AS module_id,
          t.slug AS track_slug, t.title AS track_title,
          COALESCE(p.state, 'not_started') AS state,
          COALESCE(p.notes, '') AS notes
        FROM prep_lessons l
        JOIN prep_modules m ON m.id = l.module_id
        JOIN prep_tracks t ON t.id = m.track_id
        LEFT JOIN prep_lesson_progress p ON p.lesson_id = l.id AND p.user_id = :uid
        WHERE m.slug = :mslug AND l.slug = :lslug
    """, {"mslug": module_slug, "lslug": lesson_slug, "uid": user_id}).fetchone()
    if row is None:
        return None
    siblings = conn.execute("""
        SELECT id, slug, title, sort_order FROM prep_lessons
        WHERE module_id = ? ORDER BY sort_order, id
    """, (row["module_id"],)).fetchall()
    return {"lesson": dict(row), "siblings": [dict(r) for r in siblings]}


def set_lesson_state(conn: sqlite3.Connection, lesson_id: int, state: str,
                     notes: str | None = None,
                     user_id: str = LOCAL_USER_ID) -> None:
    if state not in LESSON_STATES:
        raise ValueError(f"invalid lesson state {state!r}")
    # Stale/unknown lesson_id: no-op rather than fail the progress FK on INSERT.
    _require_row(conn, "prep_lessons", lesson_id)
    now = utcnow()
    row = conn.execute(
        "SELECT id, state FROM prep_lesson_progress WHERE lesson_id = ? AND user_id = ?",
        (lesson_id, user_id)).fetchone()
    started_at = now if state in ("in_progress", "completed") else None
    completed_at = now if state == "completed" else None
    if row is None:
        conn.execute(
            """INSERT INTO prep_lesson_progress
                 (user_id, lesson_id, state, notes, started_at, completed_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, lesson_id, state, notes or "", started_at, completed_at, now))
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
        args.extend([lesson_id, user_id])
        conn.execute(
            f"UPDATE prep_lesson_progress SET {', '.join(sets)} "
            "WHERE lesson_id = ? AND user_id = ?", args)
    conn.commit()


def set_problem_state(conn: sqlite3.Connection, problem_id: int, state: str,
                      notes: str | None = None,
                      user_id: str = LOCAL_USER_ID) -> None:
    if state not in PROBLEM_STATES:
        raise ValueError(f"invalid problem state {state!r}")
    # Stale/unknown problem_id: no-op rather than fail the progress FK on INSERT.
    _require_row(conn, "prep_problems", problem_id)
    now = utcnow()
    row = conn.execute(
        "SELECT id, state FROM prep_problem_progress WHERE problem_id = ? AND user_id = ?",
        (problem_id, user_id)).fetchone()
    solved_at = now if state == "solved" else None
    if row is None:
        conn.execute(
            """INSERT INTO prep_problem_progress
                 (user_id, problem_id, state, notes, solved_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, problem_id, state, notes or "", solved_at, now))
    else:
        sets = ["state = ?", "updated_at = ?"]
        args: list = [state, now]
        if notes is not None:
            sets.append("notes = ?")
            args.append(notes)
        if state == "solved":
            sets.append("solved_at = ?")
            args.append(now)
        args.extend([problem_id, user_id])
        conn.execute(
            f"UPDATE prep_problem_progress SET {', '.join(sets)} "
            "WHERE problem_id = ? AND user_id = ?", args)
    conn.commit()


def prep_ctci_problem_detail(conn: sqlite3.Connection, module_slug: str,
                             problem_slug: str,
                             user_id: str = LOCAL_USER_ID) -> dict | None:
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
        LEFT JOIN prep_ctci_problem_progress cpp ON cpp.ctci_problem_id = cp.id AND cpp.user_id = :uid
        WHERE m.slug = :mslug AND cp.slug = :pslug
    """, {"mslug": module_slug, "pslug": problem_slug, "uid": user_id}).fetchone()
    if row is None:
        return None
    siblings = conn.execute("""
        SELECT id, slug, ctci_id, title, sort_order FROM prep_ctci_problems
        WHERE module_id = ? ORDER BY sort_order, id
    """, (row["module_id"],)).fetchall()
    return {"problem": dict(row), "siblings": [dict(r) for r in siblings]}


def set_ctci_problem_state(conn: sqlite3.Connection, ctci_problem_id: int,
                           state: str, notes: str | None = None,
                           user_id: str = LOCAL_USER_ID) -> None:
    if state not in PROBLEM_STATES:
        raise ValueError(f"invalid ctci problem state {state!r}")
    # Stale/unknown id: no-op rather than fail the progress FK on INSERT.
    _require_row(conn, "prep_ctci_problems", ctci_problem_id)
    now = utcnow()
    row = conn.execute(
        "SELECT id, state FROM prep_ctci_problem_progress "
        "WHERE ctci_problem_id = ? AND user_id = ?",
        (ctci_problem_id, user_id)).fetchone()
    solved_at = now if state == "solved" else None
    if row is None:
        conn.execute(
            """INSERT INTO prep_ctci_problem_progress
                 (user_id, ctci_problem_id, state, notes, solved_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, ctci_problem_id, state, notes or "", solved_at, now))
    else:
        sets = ["state = ?", "updated_at = ?"]
        args: list = [state, now]
        if notes is not None:
            sets.append("notes = ?")
            args.append(notes)
        if state == "solved":
            sets.append("solved_at = ?")
            args.append(now)
        args.extend([ctci_problem_id, user_id])
        conn.execute(
            f"UPDATE prep_ctci_problem_progress SET {', '.join(sets)} "
            "WHERE ctci_problem_id = ? AND user_id = ?", args)
    conn.commit()


def prep_resume_target(conn: sqlite3.Connection,
                       user_id: str = LOCAL_USER_ID) -> dict | None:
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
        WHERE p.state = 'in_progress' AND p.user_id = :uid
        ORDER BY p.updated_at DESC LIMIT 1
    """, {"uid": user_id}).fetchone()
    if row:
        return dict(row)
    row = conn.execute("""
        SELECT m.slug AS module_slug, l.slug AS lesson_slug, l.title AS lesson_title,
               m.title AS module_title, t.title AS track_title, 'next' AS source
        FROM prep_lessons l
        JOIN prep_modules m ON m.id = l.module_id
        JOIN prep_tracks t ON t.id = m.track_id
        LEFT JOIN prep_lesson_progress p ON p.lesson_id = l.id AND p.user_id = :uid
        WHERE COALESCE(p.state, 'not_started') = 'not_started'
        ORDER BY t.sort_order, m.sort_order, l.sort_order LIMIT 1
    """, {"uid": user_id}).fetchone()
    return dict(row) if row else None


def prep_overall_counts(conn: sqlite3.Connection,
                        user_id: str = LOCAL_USER_ID) -> dict[str, int]:
    """Headline numbers for the nav badge — total + completed lessons."""
    rows = conn.execute("""
        SELECT
          (SELECT COUNT(*) FROM prep_lessons) AS lessons_total,
          (SELECT COUNT(*) FROM prep_lesson_progress
             WHERE state = 'completed' AND user_id = :uid) AS lessons_done,
          (SELECT COUNT(*) FROM prep_problems) AS problems_total,
          (SELECT COUNT(*) FROM prep_problem_progress
             WHERE state = 'solved' AND user_id = :uid) AS problems_done,
          (SELECT COUNT(*) FROM prep_ctci_problems) AS ctci_total,
          (SELECT COUNT(*) FROM prep_ctci_problem_progress
             WHERE state = 'solved' AND user_id = :uid) AS ctci_done
    """, {"uid": user_id}).fetchone()
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


def companies_overview(conn: sqlite3.Connection,
                       user_id: str = LOCAL_USER_ID) -> list[dict]:
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
        LEFT JOIN company_problem_progress pr
          ON pr.company_problem_id = cp.id AND pr.user_id = :uid
        GROUP BY cp.company_key
        ORDER BY problem_count DESC, LOWER(MIN(cp.company))
    """, {"uid": user_id}).fetchall()
    return [dict(r) for r in rows]


def company_problems_for(conn: sqlite3.Connection, company_key: str,
                         difficulty: str = "", limit: int = 0,
                         user_id: str = LOCAL_USER_ID) -> list[dict]:
    """A company's questions (most-asked first) with solve state joined."""
    sql = ["""SELECT cp.*, COALESCE(pr.state, 'not_started') AS state
              FROM company_problems cp
              LEFT JOIN company_problem_progress pr
                ON pr.company_problem_id = cp.id AND pr.user_id = :uid
              WHERE cp.company_key = :ckey"""]
    params: dict = {"uid": user_id, "ckey": company_key}
    if difficulty in ("easy", "medium", "hard"):
        sql.append("AND cp.difficulty = :diff")
        params["diff"] = difficulty
    sql.append("ORDER BY cp.frequency DESC, cp.leetcode_number")
    if limit:
        sql.append("LIMIT :lim")
        params["lim"] = limit
    return [dict(r) for r in conn.execute(" ".join(sql), params).fetchall()]


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
                              state: str, notes: str | None = None,
                              user_id: str = LOCAL_USER_ID) -> None:
    if state not in PROBLEM_STATES:
        raise ValueError(f"invalid company problem state {state!r}")
    # Stale/unknown id: no-op rather than fail the progress FK on INSERT.
    _require_row(conn, "company_problems", problem_id)
    now = utcnow()
    row = conn.execute(
        "SELECT id FROM company_problem_progress "
        "WHERE company_problem_id = ? AND user_id = ?",
        (problem_id, user_id)).fetchone()
    solved_at = now if state == "solved" else None
    if row is None:
        conn.execute(
            """INSERT INTO company_problem_progress
                 (user_id, company_problem_id, state, notes, solved_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, problem_id, state, notes or "", solved_at, now))
    else:
        sets = ["state = ?", "updated_at = ?"]
        args: list = [state, now]
        if notes is not None:
            sets.append("notes = ?")
            args.append(notes)
        if state == "solved":
            sets.append("solved_at = ?")
            args.append(now)
        args.extend([problem_id, user_id])
        conn.execute(
            f"UPDATE company_problem_progress SET {', '.join(sets)} "
            "WHERE company_problem_id = ? AND user_id = ?", args)
    conn.commit()


def company_overall_counts(conn: sqlite3.Connection,
                           user_id: str = LOCAL_USER_ID) -> dict[str, int]:
    """Headline numbers for the nav badge — distinct companies + solved/total."""
    row = conn.execute("""
        SELECT
          (SELECT COUNT(DISTINCT company_key) FROM company_problems) AS companies,
          (SELECT COUNT(*) FROM company_problems) AS problems_total,
          (SELECT COUNT(*) FROM company_problem_progress
             WHERE state = 'solved' AND user_id = :uid) AS problems_done
    """, {"uid": user_id}).fetchone()
    return dict(row) if row else {"companies": 0, "problems_total": 0,
                                  "problems_done": 0}


# --- company question refresh runs (mirror referral_runs) -------------------
def start_company_refresh(conn: sqlite3.Connection, company_key: str = "") -> int:
    # RETURNING id works on both SQLite (3.35+) and Postgres; psycopg has no
    # cursor.lastrowid, so the new id is read back explicitly instead.
    row = conn.execute(
        "INSERT INTO company_refresh_runs (company_key, state, started_at) "
        "VALUES (?, 'running', ?) RETURNING id", (company_key, utcnow())).fetchone()
    conn.commit()
    return row["id"]


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


# ----------------------------------------------------- startup company facts ---
# Columns in startup_companies, grouped by how they encode at the DB boundary.
STARTUP_SCALAR = (
    "employees", "founded", "batch", "status", "stage", "last_round",
    "last_round_amount", "total_raised", "industry", "location", "website",
    "one_liner", "description", "yc_url", "source", "notes",
)
STARTUP_LIST = ("investors", "notable_people", "tags")
STARTUP_BOOL = ("top_company", "is_hiring")


def decode_startup_row(row: sqlite3.Row | None) -> dict | None:
    """A startup_companies row → a StartupMeta-shaped dict (JSON lists decoded,
    bools as Python bools). None passes through."""
    if row is None:
        return None
    out = {"company_key": row["company_key"], "name": row["name"],
           "user_edited": bool(row["user_edited"]), "updated_at": row["updated_at"]}
    for col in STARTUP_SCALAR:
        out[col] = row[col] or ""
    for col in STARTUP_LIST:
        try:
            out[col] = json.loads(row[col]) if row[col] else []
        except (ValueError, TypeError):
            out[col] = []
    for col in STARTUP_BOOL:
        out[col] = bool(row[col])
    return out


def _encode_startup(meta: dict) -> dict:
    """A StartupMeta-shaped dict → column values for the DB (lists→JSON,
    bools→int), keeping only known columns."""
    enc: dict = {}
    for col in STARTUP_SCALAR:
        enc[col] = str(meta.get(col) or "")
    for col in STARTUP_LIST:
        value = meta.get(col) or []
        enc[col] = json.dumps(value if isinstance(value, list) else [])
    for col in STARTUP_BOOL:
        enc[col] = 1 if meta.get(col) else 0
    return enc


def _merge_startup(existing: dict, fresh: dict) -> dict:
    """Fold a freshly-discovered metadata dict into the stored one: fresh
    non-empty scalars win (keep data current), list fields are unioned so a
    previously-known investor is never lost."""
    out = dict(existing)
    for col in STARTUP_SCALAR:
        if fresh.get(col):
            out[col] = fresh[col]
    for col in STARTUP_LIST:
        merged = list(existing.get(col) or [])
        seen = {v.lower() for v in merged if isinstance(v, str)}
        for value in fresh.get(col) or []:
            if isinstance(value, str) and value.lower() not in seen:
                merged.append(value)
                seen.add(value.lower())
        out[col] = merged
    for col in STARTUP_BOOL:
        out[col] = bool(existing.get(col)) or bool(fresh.get(col))
    return out


def upsert_startup_company(conn: sqlite3.Connection, meta: dict,
                           now: str | None = None, from_user: bool = False,
                           user_id: str = LOCAL_USER_ID) -> str:
    """Insert or update one startup's facts, scoped to ``user_id``. From ingest
    (from_user=False) a row a user has edited is left untouched; otherwise fresh
    scalars win and lists union. A user edit (from_user=True) overwrites with
    what was submitted and sets the user_edited guard. Returns
    'inserted' | 'updated' | 'skipped'."""
    now = now or utcnow()
    key = normalize_company_name(meta.get("name", ""))
    if not key:
        return "skipped"
    row = conn.execute(
        "SELECT * FROM startup_companies WHERE user_id = ? AND company_key = ?",
        (user_id, key)).fetchone()
    if row is not None and row["user_edited"] and not from_user:
        return "skipped"

    existing = decode_startup_row(row) or {}
    record = ({**existing, **meta} if from_user
              else _merge_startup(existing, meta))
    enc = _encode_startup(record)
    name = meta.get("name") or existing.get("name") or key
    cols = ["name", *STARTUP_SCALAR, *STARTUP_LIST, *STARTUP_BOOL,
            "user_edited", "updated_at"]
    values = {"name": name, **enc,
              "user_edited": 1 if (from_user or (row and row["user_edited"])) else 0,
              "updated_at": now}
    if row is None:
        placeholders = ", ".join(["?"] * (len(cols) + 2))
        conn.execute(
            f"INSERT INTO startup_companies (user_id, company_key, {', '.join(cols)}) "
            f"VALUES ({placeholders})",
            [user_id, key, *(values[c] for c in cols)])
        conn.commit()
        return "inserted"
    sets = ", ".join(f"{c} = ?" for c in cols)
    conn.execute(
        f"UPDATE startup_companies SET {sets} WHERE user_id = ? AND company_key = ?",
        [*(values[c] for c in cols), user_id, key])
    conn.commit()
    return "updated"


def startup_company(conn: sqlite3.Connection, company_key: str,
                    user_id: str = LOCAL_USER_ID) -> dict | None:
    return decode_startup_row(conn.execute(
        "SELECT * FROM startup_companies WHERE user_id = ? AND company_key = ?",
        (user_id, company_key)).fetchone())


def startup_company_for(conn: sqlite3.Connection, company_name: str,
                        user_id: str = LOCAL_USER_ID) -> dict | None:
    """The startup facts for a display company name (normalized to the key)."""
    key = normalize_company_name(company_name)
    return startup_company(conn, key, user_id) if key else None


def startup_keys(conn: sqlite3.Connection,
                 user_id: str = LOCAL_USER_ID) -> set[str]:
    """Every normalized company name we hold startup facts for."""
    return {r["company_key"] for r in conn.execute(
        "SELECT company_key FROM startup_companies WHERE user_id = ?",
        (user_id,)).fetchall()}


def list_startups(conn: sqlite3.Connection, q: str = "",
                  user_id: str = LOCAL_USER_ID) -> list[dict]:
    """All tracked startups (decoded), each annotated with how many active jobs
    and how many are still to-apply, ordered by open jobs then name. `q` filters
    on name / industry / investors substring."""
    counts = {}
    for r in conn.execute(
            """SELECT j.company, COUNT(*) AS n,
                      SUM(CASE WHEN a.status NOT IN
                          ('applied','confirmed','interviewing','offer','rejected',
                           'withdrawn','in_progress') THEN 1 ELSE 0 END) AS open_n
               FROM jobs j JOIN applications a ON a.job_id = j.id
               WHERE j.is_active = 1 AND j.is_startup = 1 AND j.user_id = ?
               GROUP BY j.company""", (user_id,)).fetchall():
        counts[normalize_company_name(r["company"])] = (r["n"], r["open_n"] or 0)
    out = []
    for row in conn.execute(
            "SELECT * FROM startup_companies WHERE user_id = ? ORDER BY LOWER(name)",
            (user_id,)).fetchall():
        meta = decode_startup_row(row)
        if q:
            hay = " ".join([meta["name"], meta["industry"],
                            " ".join(meta["investors"])]).lower()
            if q.lower() not in hay:
                continue
        meta["job_count"], meta["open_count"] = counts.get(meta["company_key"], (0, 0))
        out.append(meta)
    out.sort(key=lambda m: (-m["job_count"], m["name"].lower()))
    return out


def refresh_startup_flags(conn: sqlite3.Connection,
                          user_id: str = LOCAL_USER_ID) -> int:
    """Set jobs.is_startup for every job whose company is a known startup
    (matched on normalized name), clearing it otherwise, scoped to one user.
    Returns rows changed. Idempotent — safe to call after every ingest. The
    user_id scope is critical: without it, one tenant's startup roster would
    relabel another tenant's jobs."""
    keys = startup_keys(conn, user_id)
    changed = 0
    for r in conn.execute(
            "SELECT DISTINCT company FROM jobs WHERE user_id = ?",
            (user_id,)).fetchall():
        want = 1 if normalize_company_name(r["company"]) in keys else 0
        cur = conn.execute(
            "UPDATE jobs SET is_startup = ? "
            "WHERE user_id = ? AND company = ? AND is_startup != ?",
            (want, user_id, r["company"], want))
        changed += cur.rowcount
    conn.commit()
    return changed


# ------------------------------------------------- company registry ---
# The per-user, per-track set of companies the pipeline searches. Mirrors the
# YAML registries into queryable rows tagged curated/discovered, with
# search-state (last_searched_at, last_found_jobs) that later drives fresh,
# not-recently-searched discovery. Populated by ingest from each track's live
# registry; keyed by normalize_company_name so it joins jobs.company /
# startup_companies across spellings.

# Identity/config columns patched on re-sync. Search-state (last_searched_at,
# last_found_jobs) is stamped separately by touch_company_search;
# first_seen_at is never overwritten.
COMPANY_UPDATABLE = ("name", "ats", "careers_url", "tags", "params",
                     "source", "discovered_via", "enabled")


def _encode_company(record: dict) -> dict:
    """Company dict → column values: JSON-serialize tags/params, coerce the
    enabled flag to int. Values already strings/ints pass through."""
    enc = dict(record)
    # default=str so a non-JSON scalar (e.g. a YAML date that landed in params)
    # serializes instead of aborting the ingest — mirrors json.dumps(..., default=str)
    # used elsewhere in this module.
    if "tags" in enc and not isinstance(enc["tags"], str):
        enc["tags"] = json.dumps(list(enc.get("tags") or []), default=str)
    if "params" in enc and not isinstance(enc["params"], str):
        enc["params"] = json.dumps(dict(enc.get("params") or {}), default=str)
    if "enabled" in enc:
        enc["enabled"] = 1 if enc["enabled"] else 0
    return enc


def decode_company_row(row: sqlite3.Row | None) -> dict | None:
    """A companies row → a dict with tags/params JSON-decoded and
    enabled/user_edited as bools. None passes through."""
    if row is None:
        return None
    out = dict(row)
    for col, empty in (("tags", []), ("params", {})):
        raw = out.get(col)
        try:
            out[col] = json.loads(raw) if raw else empty
        except (ValueError, TypeError):
            out[col] = empty
    out["enabled"] = bool(out.get("enabled"))
    out["user_edited"] = bool(out.get("user_edited"))
    return out


def upsert_company(conn: sqlite3.Connection, record: dict,
                   user_id: str = LOCAL_USER_ID, track: str = "main",
                   now: str | None = None, from_user: bool = False) -> str:
    """Insert or update one company registry row for (user_id, track). Preserves
    first_seen_at and search-state; a row a user has edited in the UI is left
    untouched on a non-user sync (mirrors upsert_startup_company). Returns
    'inserted' | 'updated' | 'skipped'."""
    now = now or utcnow()
    key = normalize_company_name(record.get("name", ""))
    if not key:
        return "skipped"
    row = conn.execute(
        "SELECT * FROM companies WHERE user_id = ? AND track = ? AND company_key = ?",
        (user_id, track, key)).fetchone()
    if row is not None and row["user_edited"] and not from_user:
        return "skipped"
    enc = _encode_company(record)
    if row is None:
        conn.execute(
            "INSERT INTO companies (user_id, track, company_key, name, ats, "
            "careers_url, tags, params, source, discovered_via, enabled, "
            "first_seen_at, last_searched_at, last_found_jobs, user_edited, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, track, key, enc.get("name") or key, enc.get("ats", ""),
             enc.get("careers_url", ""), enc.get("tags", "") or "",
             enc.get("params", "") or "", enc.get("source", "curated"),
             enc.get("discovered_via", ""), int(enc.get("enabled", 1)),
             now, "", 0, 1 if from_user else 0, now))
        return "inserted"
    sets, vals = [], []
    for col in COMPANY_UPDATABLE:
        if col in enc:
            sets.append(f"{col} = ?")
            vals.append(enc[col])
    sets.append("user_edited = ?")
    vals.append(1 if (from_user or row["user_edited"]) else 0)
    sets.append("updated_at = ?")
    vals.append(now)
    vals += [user_id, track, key]
    conn.execute(
        f"UPDATE companies SET {', '.join(sets)} "
        "WHERE user_id = ? AND track = ? AND company_key = ?", vals)
    return "updated"


def touch_company_search(conn: sqlite3.Connection, user_id: str, track: str,
                         company_key: str, jobs_found: int,
                         now: str | None = None) -> None:
    """Stamp a company as searched in the current run (last_searched_at +
    last_found_jobs). No-op for an unknown key."""
    now = now or utcnow()
    conn.execute(
        "UPDATE companies SET last_searched_at = ?, last_found_jobs = ? "
        "WHERE user_id = ? AND track = ? AND company_key = ?",
        (now, int(jobs_found or 0), user_id, track, company_key))


def disable_absent_companies(conn: sqlite3.Connection, user_id: str, track: str,
                             keep_keys, now: str | None = None) -> int:
    """Disable (enabled=0) companies for (user_id, track) whose key is not in
    keep_keys, so the registry mirror never accumulates companies that dropped
    out of the live registry. User-edited rows are left alone. Returns the count
    disabled."""
    now = now or utcnow()
    keep = set(keep_keys)
    disabled = 0
    for r in conn.execute(
            "SELECT company_key FROM companies "
            "WHERE user_id = ? AND track = ? AND enabled = 1 AND user_edited = 0",
            (user_id, track)).fetchall():
        if r["company_key"] not in keep:
            conn.execute(
                "UPDATE companies SET enabled = 0, updated_at = ? "
                "WHERE user_id = ? AND track = ? AND company_key = ?",
                (now, user_id, track, r["company_key"]))
            disabled += 1
    return disabled


def get_company(conn: sqlite3.Connection, user_id: str, track: str,
                company_key: str) -> dict | None:
    return decode_company_row(conn.execute(
        "SELECT * FROM companies WHERE user_id = ? AND track = ? AND company_key = ?",
        (user_id, track, company_key)).fetchone())


def list_companies(conn: sqlite3.Connection, user_id: str = LOCAL_USER_ID,
                   track: str | None = None,
                   enabled_only: bool = False) -> list[dict]:
    """Company registry rows for a user (optionally one track), decoded and
    ordered by track then name."""
    sql = "SELECT * FROM companies WHERE user_id = ?"
    params: list = [user_id]
    if track is not None:
        sql += " AND track = ?"
        params.append(track)
    if enabled_only:
        sql += " AND enabled = 1"
    sql += " ORDER BY track, LOWER(name)"
    return [decode_company_row(r) for r in conn.execute(sql, params).fetchall()]


def record_company_search_run(conn: sqlite3.Connection, user_id: str, track: str,
                              source: str, companies_total: int,
                              companies_new: int, companies_disabled: int,
                              jobs_found: int, now: str | None = None) -> None:
    """Append a company_search_runs audit row (per-track freshness history)."""
    now = now or utcnow()
    conn.execute(
        "INSERT INTO company_search_runs (user_id, track, ran_at, source, "
        "companies_total, companies_new, companies_disabled, jobs_found) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, track, now, source, int(companies_total), int(companies_new),
         int(companies_disabled), int(jobs_found)))


# ------------------------------------------------------- per-user resume ---
def get_resume(conn: sqlite3.Connection, user_id: str = LOCAL_USER_ID) -> str | None:
    """The user's stored resume text, or None if they have none (caller then
    falls back to the file / bundled sample)."""
    row = conn.execute(
        "SELECT resume_text FROM user_resumes WHERE user_id = ?",
        (user_id,)).fetchone()
    return row["resume_text"] if row and row["resume_text"] else None


def get_resume_meta(conn: sqlite3.Connection,
                    user_id: str = LOCAL_USER_ID) -> dict | None:
    row = conn.execute(
        "SELECT * FROM user_resumes WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def set_resume(conn: sqlite3.Connection, user_id: str, text: str,
               pdf_name: str = "", now: str | None = None) -> None:
    """Store (or replace) a user's resume text. Select-then-write so it works on
    SQLite and Postgres without ON CONFLICT."""
    now = now or utcnow()
    exists = conn.execute(
        "SELECT 1 FROM user_resumes WHERE user_id = ?", (user_id,)).fetchone()
    if exists:
        conn.execute(
            "UPDATE user_resumes SET resume_text = ?, pdf_name = ?, updated_at = ? "
            "WHERE user_id = ?", (text, pdf_name, now, user_id))
    else:
        conn.execute(
            "INSERT INTO user_resumes (user_id, resume_text, pdf_name, updated_at) "
            "VALUES (?, ?, ?, ?)", (user_id, text, pdf_name, now))
    conn.commit()


# ------------------------------------------------------------ hosted accounts ---
# Used only in hosted mode (Supabase Auth); see webapp/auth.py. Local single-user
# mode never touches these.
def count_app_users(conn) -> int:
    """Number of accounts on record. 0 in local mode / before the first login."""
    return conn.execute("SELECT COUNT(*) AS n FROM app_users").fetchone()["n"]


def get_app_user(conn, user_id: str):
    return conn.execute("SELECT * FROM app_users WHERE id = ?", (user_id,)).fetchone()


def upsert_app_user(conn, user_id: str, email: str,
                    *, is_admin: bool | None = None) -> None:
    """Record or refresh an account (called on login). ``is_admin`` is applied
    only when explicitly passed — the first account to log in becomes the owner."""
    now = utcnow()
    if get_app_user(conn, user_id) is None:
        conn.execute(
            "INSERT INTO app_users (id, email, is_admin, created_at, last_login_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, email, 1 if is_admin else 0, now, now))
    else:
        conn.execute(
            "UPDATE app_users SET email = ?, last_login_at = ? WHERE id = ?",
            (email, now, user_id))
        if is_admin is not None:
            conn.execute("UPDATE app_users SET is_admin = ? WHERE id = ?",
                         (1 if is_admin else 0, user_id))
    conn.commit()
