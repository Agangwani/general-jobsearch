"""Stage 2b: per-user application isolation (the lazy-application model).

An application is one user's engagement with one posting. Two accounts must
never see each other's apply status or notes, and a job a user hasn't touched
sits in their to-apply pile (no application row yet — created lazily on first
engagement). These run against SQLite (the default backend) and exercise the
same db functions the routes call."""

import pytest

from webapp import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "appscope.db")
    yield c
    c.close()


def _job(key="greenhouse:Acme:1", **kw):
    base = {
        "key": key, "source": "greenhouse", "company": "Acme",
        "title": "Senior Software Engineer", "location": "New York, NY",
        "url": "https://acme.com/jobs/1", "description": "Build backend systems.",
        "posted_at": "2026-06-10", "fit_score": 80.0, "rank_score": 60.0,
        "cluster": 1, "filter_reason": "", "validation": "", "validation_note": "",
    }
    base.update(kw)
    return base


def _job_id(conn, key):
    return conn.execute("SELECT id FROM jobs WHERE key = ?", (key,)).fetchone()["id"]


def test_status_is_isolated_per_user(conn):
    db.upsert_job(conn, _job())
    jid = _job_id(conn, "greenhouse:Acme:1")

    # u1 applies; u2 has done nothing.
    a1 = db.get_or_create_application(conn, jid, "u1")
    db.set_application_status(conn, a1, "applied", detail="sent", via="ui")

    assert db.job_with_application(conn, jid, "u1")["status"] == "applied"
    # u2 sees the to-apply default and has no application row of their own.
    u2_view = db.job_with_application(conn, jid, "u2")
    assert u2_view["status"] == "not_applied"
    assert u2_view["application_id"] is None
    # The owner ('local') auto-application is likewise untouched by u1's apply.
    assert db.job_with_application(conn, jid, "local")["status"] == "not_applied"


def test_notes_do_not_leak_between_users(conn):
    db.upsert_job(conn, _job())
    jid = _job_id(conn, "greenhouse:Acme:1")
    a1 = db.get_or_create_application(conn, jid, "u1")
    conn.execute("UPDATE applications SET notes = ? WHERE id = ?", ("call recruiter", a1))
    conn.commit()
    assert db.job_with_application(conn, jid, "u1")["notes"] == "call recruiter"
    # u2's lazily-absent application carries no notes.
    assert db.job_with_application(conn, jid, "u2")["notes"] is None


def test_application_is_created_lazily_and_idempotently(conn):
    db.upsert_job(conn, _job())
    jid = _job_id(conn, "greenhouse:Acme:1")

    # No row for a brand-new user until they engage.
    assert conn.execute(
        "SELECT COUNT(*) c FROM applications WHERE user_id = 'u9'").fetchone()["c"] == 0

    first = db.get_or_create_application(conn, jid, "u9")
    second = db.get_or_create_application(conn, jid, "u9")
    assert first == second  # idempotent — one row per (user, job)
    assert conn.execute(
        "SELECT COUNT(*) c FROM applications WHERE user_id = 'u9'").fetchone()["c"] == 1


def test_get_or_create_returns_none_for_unknown_job(conn):
    # A stale/out-of-range job id must not violate the applications->jobs FK; the
    # helper returns None so the route degrades to a redirect instead of a 500.
    assert db.get_or_create_application(conn, 999999, "u1") is None
    assert db.get_or_create_application(conn, 2**63, "u1") is None
    assert conn.execute("SELECT COUNT(*) c FROM applications").fetchone()["c"] == 0


def test_stack_counts_are_per_user(conn):
    db.upsert_job(conn, _job("greenhouse:Acme:1"))
    db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta"))
    jid = _job_id(conn, "greenhouse:Acme:1")

    a1 = db.get_or_create_application(conn, jid, "u1")
    db.set_application_status(conn, a1, "applied")

    c1 = db.stack_counts(conn, "u1")
    assert c1["applied"] == 1 and c1["to_apply"] == 1
    # u2 engaged nothing — every active job counts as to-apply for them.
    c2 = db.stack_counts(conn, "u2")
    assert c2["applied"] == 0 and c2["to_apply"] == 2


def test_search_jobs_stacks_are_per_user(conn):
    db.upsert_job(conn, _job("greenhouse:Acme:1"))
    db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta", url="https://beta.co/2"))
    jid = _job_id(conn, "greenhouse:Acme:1")
    db.set_application_status(conn, db.get_or_create_application(conn, jid, "u1"), "applied")

    assert [r["company"] for r in db.search_jobs(conn, stack="applied", user_id="u1")] == ["Acme"]
    assert db.search_jobs(conn, stack="applied", user_id="u2") == []
    # u2 sees both jobs in their to-apply pile; u1 sees only the one they haven't applied to.
    assert {r["company"] for r in db.search_jobs(conn, stack="to_apply", user_id="u2")} == {"Acme", "Beta"}
    assert {r["company"] for r in db.search_jobs(conn, stack="to_apply", user_id="u1")} == {"Beta"}


def test_top_fit_to_apply_is_per_user(conn):
    db.upsert_job(conn, _job("greenhouse:Acme:1", fit_score=90.0))
    jid = _job_id(conn, "greenhouse:Acme:1")
    # Before u1 applies, the job is applyable for both users.
    assert [r["id"] for r in db.top_fit_to_apply(conn, 5, "u1")] == [jid]
    assert [r["id"] for r in db.top_fit_to_apply(conn, 5, "u2")] == [jid]
    # After u1 applies it drops out of u1's pile but stays in u2's.
    db.set_application_status(conn, db.get_or_create_application(conn, jid, "u1"), "applied")
    assert db.top_fit_to_apply(conn, 5, "u1") == []
    assert [r["id"] for r in db.top_fit_to_apply(conn, 5, "u2")] == [jid]


def test_local_mode_still_has_an_application_per_job(conn):
    # The local owner keeps an auto-created application on insert, so single-user
    # mode is wholly unchanged — job_with_application resolves an application_id.
    db.upsert_job(conn, _job())
    jid = _job_id(conn, "greenhouse:Acme:1")
    local_view = db.job_with_application(conn, jid)  # default user_id='local'
    assert local_view["application_id"] is not None
    assert local_view["status"] == "not_applied"
