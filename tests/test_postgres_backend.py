"""Live parity tests: the real db.py code paths run against Postgres.

Gated on ``JOBSEARCH_TEST_DATABASE_URL`` (a throwaway Postgres database) — when
unset, the whole module skips, so CI without Postgres still passes. Locally:

    JOBSEARCH_TEST_DATABASE_URL=postgresql://jobsearch:jobsearch@127.0.0.1/jobsearch_test \
        python -m pytest -q tests/test_postgres_backend.py

Each test gets a freshly recreated ``public`` schema, then goes through the
same ``db.connect()`` routing the hosted app uses (``JOBSEARCH_DATABASE_URL``),
exercising the placeholder translation, the schema transform, and every
SQLite-only construct that was ported (RETURNING, ON CONFLICT, LOWER ordering).
"""

import os

import pytest

PG_URL = os.environ.get("JOBSEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="set JOBSEARCH_TEST_DATABASE_URL to run the Postgres parity tests",
)


@pytest.fixture
def pgconn(monkeypatch, tmp_path):
    from webapp import db
    from webapp.pgcompat import connect_postgres

    # Clean slate: drop and recreate the public schema on the test database.
    admin = connect_postgres(PG_URL)
    admin.execute("DROP SCHEMA IF EXISTS public CASCADE")
    admin.execute("CREATE SCHEMA public")
    admin.commit()
    admin.close()

    # Route db.connect() to Postgres exactly like a hosted deployment would.
    monkeypatch.setenv("JOBSEARCH_DATABASE_URL", PG_URL)
    conn = db.connect(tmp_path / "unused.db")
    try:
        yield conn
    finally:
        conn.close()


def _job(key="greenhouse:Acme:1", **kw):
    base = {
        "key": key, "source": "greenhouse", "company": "Acme",
        "title": "Senior Software Engineer", "url": "https://acme.example/1",
        "description": "Build resilient systems.", "fit_score": 87.5,
        "rank_score": 80.0,
    }
    base.update(kw)
    return base


def test_connect_creates_full_schema(pgconn):
    # Every table in the SQLite schema exists in Postgres after connect().
    rows = pgconn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public'").fetchall()
    names = {r["table_name"] for r in rows}
    for expected in ("jobs", "applications", "profile_fields", "prep_tracks",
                     "company_problems", "startup_companies", "referral_runs"):
        assert expected in names


def test_jobs_lifecycle_and_search(pgconn):
    from webapp import db

    assert db.upsert_job(pgconn, _job()) == "inserted"
    assert db.upsert_job(pgconn, _job()) == "unchanged"
    assert db.upsert_job(pgconn, _job(title="Staff Engineer")) == "updated"

    row = pgconn.execute(
        "SELECT * FROM jobs WHERE key = ?", ("greenhouse:Acme:1",)).fetchone()
    assert row["title"] == "Staff Engineer"
    assert row["fit_score"] == 87.5  # DOUBLE PRECISION round-trips a float

    app = db.job_with_application(pgconn, row["id"])
    assert app["status"] == "not_applied"  # auto-created on insert
    db.set_application_status(pgconn, app["application_id"], "applied")

    assert len(db.search_jobs(pgconn, stack="applied")) == 1
    assert len(db.search_jobs(pgconn, stack="to_apply")) == 0
    assert db.stack_counts(pgconn)["applied"] == 1


def test_returning_id_paths(pgconn):
    from jobsearch.referrals import store
    from webapp import db

    # db.start_company_refresh — INSERT ... RETURNING id (was cursor.lastrowid)
    rid = db.start_company_refresh(pgconn, "acme")
    assert isinstance(rid, int) and rid > 0
    db.finish_company_refresh(pgconn, rid, added=2, updated=1)
    assert db.latest_company_refresh(pgconn, "acme")["state"] == "done"

    # store.start_run — same RETURNING-id port, needs a real job FK
    db.upsert_job(pgconn, _job())
    job_id = pgconn.execute(
        "SELECT id FROM jobs WHERE key = ?", ("greenhouse:Acme:1",)).fetchone()["id"]
    run_id = store.start_run(pgconn, job_id)
    assert isinstance(run_id, int) and run_id > 0
    store.finish_run(pgconn, run_id, "ok")
    assert store.latest_run(pgconn, job_id)["state"] == "done"


def test_profile_on_conflict(pgconn):
    from webapp import profile

    profile.ensure_fields(pgconn)            # INSERT ... ON CONFLICT DO NOTHING
    profile.set_field(pgconn, "full_name", "Ada Lovelace")
    profile.set_field(pgconn, "full_name", "Ada L.")  # ON CONFLICT DO UPDATE
    fields = {r["field"]: r["value"] for r in profile.all_fields(pgconn)}
    assert fields["full_name"] == "Ada L."


def test_company_problems_lower_ordering(pgconn):
    from webapp import db

    db.seed_company_problems(pgconn, [
        {"company": "Zeta", "company_key": "zeta", "leetcode_slug": "two-sum",
         "title": "Two Sum", "difficulty": "easy", "frequency": 90},
        {"company": "alpha", "company_key": "alpha", "leetcode_slug": "lru-cache",
         "title": "LRU Cache", "difficulty": "medium", "frequency": 50},
    ])
    overview = db.companies_overview(pgconn)  # ORDER BY ... LOWER(MIN(cp.company))
    assert {o["company_key"] for o in overview} == {"zeta", "alpha"}
    probs = db.company_problems_for(pgconn, "zeta")
    assert probs[0]["title"] == "Two Sum"


def test_startup_upsert_and_list(pgconn):
    from webapp import db

    db.upsert_startup_company(pgconn, {
        "name": "Wibble", "industry": "AI", "investors": ["YC"], "is_hiring": True})
    items = db.list_startups(pgconn)          # ORDER BY LOWER(name) + JSON decode
    wibble = next(s for s in items if s["name"] == "Wibble")
    assert wibble["investors"] == ["YC"]
    assert wibble["is_hiring"] is True


def test_two_user_job_isolation(pgconn):
    from webapp import db

    # Same pipeline key under two owners must coexist (composite UNIQUE(user_id,key)).
    assert db.upsert_job(pgconn, _job(), user_id="user-a") == "inserted"
    assert db.upsert_job(pgconn, _job(), user_id="user-b") == "inserted"
    assert [r["company"] for r in db.search_jobs(pgconn, user_id="user-a")] == ["Acme"]
    assert len(db.search_jobs(pgconn, user_id="user-b")) == 1
    # startup roster scoping (the cross-tenant relabel guard) on Postgres.
    db.upsert_startup_company(pgconn, {"name": "Acme"}, user_id="user-a")
    assert db.refresh_startup_flags(pgconn, "user-a") == 1
    assert db.refresh_startup_flags(pgconn, "user-b") == 0
    a_id = db.job_with_application(
        pgconn, db.search_jobs(pgconn, user_id="user-a")[0]["id"], "user-a")["application_id"]
    with pytest.raises(ValueError):
        db.set_application_status(pgconn, a_id, "applied", user_id="user-b")


def test_companies_registry_roundtrip(pgconn):
    from webapp import db

    assert db.upsert_company(pgconn, {
        "name": "Ramp", "ats": "ashby", "careers_url": "https://ramp",
        "tags": ["discovered"], "params": {"org": "ramp"},
        "source": "discovered"}, track="startups") == "inserted"
    db.touch_company_search(pgconn, db.LOCAL_USER_ID, "startups", "ramp", 4)
    row = db.get_company(pgconn, db.LOCAL_USER_ID, "startups", "ramp")
    assert row["tags"] == ["discovered"] and row["params"] == {"org": "ramp"}  # TEXT JSON
    assert row["last_found_jobs"] == 4 and row["enabled"] is True
    # UNIQUE(user_id, track, company_key): same key, other track is independent.
    assert db.upsert_company(pgconn, {"name": "Ramp", "ats": "greenhouse"},
                             track="main") == "inserted"
    assert db.disable_absent_companies(pgconn, db.LOCAL_USER_ID, "startups", set()) == 1
    assert db.get_company(pgconn, db.LOCAL_USER_ID, "startups", "ramp")["enabled"] is False
    assert db.get_company(pgconn, db.LOCAL_USER_ID, "main", "ramp")["enabled"] is True
    db.record_company_search_run(pgconn, db.LOCAL_USER_ID, "main", "ingest", 1, 1, 0, 4)
    assert len(db.list_companies(pgconn)) == 2  # LOWER(name) ordering runs on PG


def test_prep_seed_named_params(pgconn):
    from jobsearch.prep.seed import seed_into_db
    from webapp import db

    summary = seed_into_db(pgconn)            # many :named-param inserts + lookups
    assert summary
    assert db.prep_tracks_overview(pgconn)
    assert db.prep_overall_counts(pgconn)["lessons_total"] > 0
    # Idempotent re-seed (content hash short-circuits) must not error.
    seed_into_db(pgconn)


def test_applications_are_per_user_on_postgres(pgconn):
    """Stage 2b application isolation, on Postgres: jobs are per-user rows
    (Stage 2a), each seeded with its owner's application, and
    get_or_create_application behaves as on SQLite."""
    from webapp import db

    db.upsert_job(pgconn, _job(), user_id="u1")
    db.upsert_job(pgconn, _job(), user_id="u2")
    j1 = pgconn.execute(
        "SELECT id FROM jobs WHERE user_id = ? AND key = ?",
        ("u1", "greenhouse:Acme:1")).fetchone()["id"]

    # u1 engages; u2 never does.
    a1 = db.get_or_create_application(pgconn, j1, "u1")
    assert a1 == db.get_or_create_application(pgconn, j1, "u1")  # idempotent
    db.set_application_status(pgconn, a1, "applied", user_id="u1")

    assert db.job_with_application(pgconn, j1, "u1")["status"] == "applied"
    # u1's job id reads as not-found for u2 (tenant isolation)...
    assert db.job_with_application(pgconn, j1, "u2") is None
    assert db.get_or_create_application(pgconn, j1, "u2") is None

    # Per-user stacks and counts.
    assert [r["company"] for r in db.search_jobs(pgconn, stack="applied", user_id="u1")] == ["Acme"]
    assert db.search_jobs(pgconn, stack="applied", user_id="u2") == []
    assert [r["company"] for r in db.search_jobs(pgconn, stack="to_apply", user_id="u2")] == ["Acme"]
    assert db.stack_counts(pgconn, "u1")["applied"] == 1
    assert db.stack_counts(pgconn, "u2")["to_apply"] == 1

    # An unknown/out-of-range job id never violates the FK — returns None.
    assert db.get_or_create_application(pgconn, 999999, "u1") is None
    assert db.get_or_create_application(pgconn, 2 ** 63, "u1") is None


def test_fit_is_per_user_on_postgres(pgconn):
    """Stage 2b per-user fit, on Postgres: fit lives on each user's own job
    rows (Stage 2a), so scores round-trip per user with no overlay table."""
    from webapp import db

    db.upsert_job(pgconn, _job(fit_score=87.5, rank_score=80.0))
    jid = pgconn.execute(
        "SELECT id FROM jobs WHERE user_id = ? AND key = ?",
        ("local", "greenhouse:Acme:1")).fetchone()["id"]

    # The pipeline's scores land on the owner's row.
    local = db.job_with_application(pgconn, jid)  # default user_id='local'
    assert local["fit_score"] == 87.5 and local["rank_score"] == 80.0

    # Per-user fit is isolated: each account's rows carry its own scores.
    db.upsert_job(pgconn, _job(fit_score=90.0, rank_score=88.0), user_id="u1")
    db.upsert_job(pgconn, _job(fit_score=40.0, rank_score=30.0), user_id="u2")
    # min_fit filters on the current user's fit.
    assert len(db.search_jobs(pgconn, min_fit=70.0, user_id="u1")) == 1
    assert db.search_jobs(pgconn, min_fit=70.0, user_id="u2") == []


def test_rescore_user_on_postgres(pgconn):
    """Stage 2b part 4b on Postgres: per-user résumé storage + rescore_user
    write onto the user's job rows, and the daily-worker
    rescore_all_active_users skips 'local'."""
    from webapp import db, fit

    db.upsert_job(pgconn, _job(
        fit_score=None, rank_score=None,
        description="python postgres backend distributed systems services api"),
        user_id="u1")
    jid = pgconn.execute(
        "SELECT id FROM jobs WHERE user_id = ? AND key = ?",
        ("u1", "greenhouse:Acme:1")).fetchone()["id"]

    db.set_resume(pgconn, "u1", "python backend engineer postgres distributed systems")
    assert db.get_resume(pgconn, "u1").startswith("python")
    assert db.users_with_resume(pgconn) == ["u1"]

    n = fit.rescore_user(pgconn, "u1", db.get_resume(pgconn, "u1"))
    assert n == 1
    assert pgconn.execute(
        "SELECT fit_score FROM jobs WHERE id = ?",
        (jid,)).fetchone()["fit_score"] is not None

    # The worker skips the 'local' pipeline sentinel.
    db.set_resume(pgconn, "local", "should be skipped")
    results = fit.rescore_all_active_users(pgconn)
    assert "u1" in results and "local" not in results


def test_state_setters_stale_id_no_op_on_postgres(pgconn):
    """The state-change setters guard a stale/unknown parent id by raising
    ValueError up front (webapp/db._require_row) instead of letting the FK
    INSERT fail. On Postgres a failed INSERT also poisons the open transaction,
    so the pre-check matters even more than on SQLite. This proves the guard is
    truly dialect-agnostic: a stale id raises ValueError (not psycopg.Error),
    the connection stays usable, and a subsequent valid write still commits."""
    import pytest

    from jobsearch.prep.seed import seed_into_db
    from webapp import db

    seed_into_db(pgconn)
    db.upsert_job(pgconn, _job())
    job_id = pgconn.execute("SELECT id FROM jobs WHERE key = ?",
                            ("greenhouse:Acme:1",)).fetchone()["id"]
    app = db.job_with_application(pgconn, job_id)

    # Each stale id raises ValueError (the dialect-agnostic no-op signal), not a
    # raw psycopg.Error, and never aborts the transaction.
    with pytest.raises(ValueError):
        db.set_application_status(pgconn, 99999999, "applied")
    lesson_id = pgconn.execute("SELECT id FROM prep_lessons LIMIT 1").fetchone()["id"]
    problem_id = pgconn.execute("SELECT id FROM prep_problems LIMIT 1").fetchone()["id"]
    with pytest.raises(ValueError):
        db.set_lesson_state(pgconn, 99999999, "completed")
    with pytest.raises(ValueError):
        db.set_problem_state(pgconn, 99999999, "solved")

    # The connection is still healthy and a valid write persists (would fail with
    # "current transaction is aborted" if a poisoned INSERT had leaked).
    db.set_application_status(pgconn, app["application_id"], "applied")
    assert db.job_with_application(pgconn, job_id)["status"] == "applied"
    db.set_lesson_state(pgconn, lesson_id, "completed")
    assert pgconn.execute(
        "SELECT state FROM prep_lesson_progress WHERE lesson_id = ?",
        (lesson_id,)).fetchone()["state"] == "completed"
    db.set_problem_state(pgconn, problem_id, "solved")
    assert pgconn.execute(
        "SELECT state FROM prep_problem_progress WHERE problem_id = ?",
        (problem_id,)).fetchone()["state"] == "solved"
