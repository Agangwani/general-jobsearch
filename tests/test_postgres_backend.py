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
    """Stage 2b lazy-application isolation, on Postgres: the LEFT JOIN +
    COALESCE(status,'not_applied') read path, the composite UNIQUE(user_id,
    job_id), and get_or_create_application all behave as on SQLite."""
    from webapp import db

    db.upsert_job(pgconn, _job())
    jid = pgconn.execute(
        "SELECT id FROM jobs WHERE key = ?", ("greenhouse:Acme:1",)).fetchone()["id"]

    # u1 engages; u2 never does.
    a1 = db.get_or_create_application(pgconn, jid, "u1")
    assert a1 == db.get_or_create_application(pgconn, jid, "u1")  # idempotent
    db.set_application_status(pgconn, a1, "applied")

    assert db.job_with_application(pgconn, jid, "u1")["status"] == "applied"
    u2 = db.job_with_application(pgconn, jid, "u2")
    assert u2["status"] == "not_applied" and u2["application_id"] is None

    # Per-user stacks and counts.
    assert [r["company"] for r in db.search_jobs(pgconn, stack="applied", user_id="u1")] == ["Acme"]
    assert db.search_jobs(pgconn, stack="applied", user_id="u2") == []
    assert [r["company"] for r in db.search_jobs(pgconn, stack="to_apply", user_id="u2")] == ["Acme"]
    assert db.stack_counts(pgconn, "u1")["applied"] == 1
    assert db.stack_counts(pgconn, "u2")["to_apply"] == 1

    # An unknown/out-of-range job id never violates the FK — returns None.
    assert db.get_or_create_application(pgconn, 999999, "u1") is None
    assert db.get_or_create_application(pgconn, 2 ** 63, "u1") is None
