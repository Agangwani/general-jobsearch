"""Stage 2b: per-user application isolation.

An application is one user's engagement with one posting. Jobs are per-user
rows (Stage 2a) and each row is seeded with its owner's application at insert,
so two accounts never see each other's apply status or notes — another
tenant's job id simply reads as not-found. These run against SQLite (the
default backend) and exercise the same db functions the routes call."""

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


def _job_id(conn, key, user_id="local"):
    return conn.execute("SELECT id FROM jobs WHERE user_id = ? AND key = ?",
                        (user_id, key)).fetchone()["id"]


def test_status_is_isolated_per_user(conn):
    # The same posting held by three owners = three job rows, each with its own
    # seeded application.
    for uid in ("local", "u1", "u2"):
        db.upsert_job(conn, _job(), user_id=uid)
    j1 = _job_id(conn, "greenhouse:Acme:1", "u1")

    # u1 applies; u2 and the owner have done nothing.
    a1 = db.get_or_create_application(conn, j1, "u1")
    db.set_application_status(conn, a1, "applied", detail="sent", via="ui", user_id="u1")

    assert db.job_with_application(conn, j1, "u1")["status"] == "applied"
    # u2's own copy of the posting still sits in their to-apply pile...
    j2 = _job_id(conn, "greenhouse:Acme:1", "u2")
    assert db.job_with_application(conn, j2, "u2")["status"] == "not_applied"
    # ...and u1's job id reads as not-found for u2 (tenant isolation).
    assert db.job_with_application(conn, j1, "u2") is None
    # The owner's copy is likewise untouched by u1's apply.
    jl = _job_id(conn, "greenhouse:Acme:1", "local")
    assert db.job_with_application(conn, jl, "local")["status"] == "not_applied"


def test_notes_do_not_leak_between_users(conn):
    db.upsert_job(conn, _job(), user_id="u1")
    db.upsert_job(conn, _job(), user_id="u2")
    j1 = _job_id(conn, "greenhouse:Acme:1", "u1")
    a1 = db.get_or_create_application(conn, j1, "u1")
    conn.execute("UPDATE applications SET notes = ? WHERE id = ?", ("call recruiter", a1))
    conn.commit()
    assert db.job_with_application(conn, j1, "u1")["notes"] == "call recruiter"
    # u2's own application carries no notes, and u1's row is invisible to them.
    j2 = _job_id(conn, "greenhouse:Acme:1", "u2")
    assert not db.job_with_application(conn, j2, "u2")["notes"]
    assert db.job_with_application(conn, j1, "u2") is None


def test_application_ids_are_stable_and_self_healing(conn):
    db.upsert_job(conn, _job(), user_id="u9")
    jid = _job_id(conn, "greenhouse:Acme:1", "u9")

    first = db.get_or_create_application(conn, jid, "u9")
    second = db.get_or_create_application(conn, jid, "u9")
    assert first == second  # idempotent — one row per job
    assert conn.execute(
        "SELECT COUNT(*) c FROM applications WHERE job_id = ?",
        (jid,)).fetchone()["c"] == 1

    # Robustness fallback: a row missing its seeded application (e.g. created
    # before seeding existed) gets one lazily instead of 500ing.
    conn.execute("DELETE FROM applications WHERE job_id = ?", (jid,))
    conn.commit()
    recreated = db.get_or_create_application(conn, jid, "u9")
    assert recreated is not None
    assert conn.execute(
        "SELECT COUNT(*) c FROM applications WHERE job_id = ?",
        (jid,)).fetchone()["c"] == 1


def test_get_or_create_returns_none_for_unknown_job(conn):
    # A stale/out-of-range job id must not violate the applications->jobs FK; the
    # helper returns None so the route degrades to a redirect instead of a 500.
    assert db.get_or_create_application(conn, 999999, "u1") is None
    assert db.get_or_create_application(conn, 2**63, "u1") is None
    # Another tenant's job id likewise reads as not-found.
    db.upsert_job(conn, _job(), user_id="u1")
    j1 = _job_id(conn, "greenhouse:Acme:1", "u1")
    assert db.get_or_create_application(conn, j1, "u2") is None
    assert conn.execute(
        "SELECT COUNT(*) c FROM applications").fetchone()["c"] == 1  # u1's seed only


def test_stack_counts_are_per_user(conn):
    for uid in ("u1", "u2"):
        db.upsert_job(conn, _job("greenhouse:Acme:1"), user_id=uid)
        db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta"), user_id=uid)
    j1 = _job_id(conn, "greenhouse:Acme:1", "u1")

    a1 = db.get_or_create_application(conn, j1, "u1")
    db.set_application_status(conn, a1, "applied", user_id="u1")

    c1 = db.stack_counts(conn, "u1")
    assert c1["applied"] == 1 and c1["to_apply"] == 1
    # u2 engaged nothing — every active job counts as to-apply for them.
    c2 = db.stack_counts(conn, "u2")
    assert c2["applied"] == 0 and c2["to_apply"] == 2


def test_search_jobs_stacks_are_per_user(conn):
    for uid in ("u1", "u2"):
        db.upsert_job(conn, _job("greenhouse:Acme:1"), user_id=uid)
        db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta",
                                 url="https://beta.co/2"), user_id=uid)
    j1 = _job_id(conn, "greenhouse:Acme:1", "u1")
    db.set_application_status(conn, db.get_or_create_application(conn, j1, "u1"), "applied", user_id="u1")

    assert [r["company"] for r in db.search_jobs(conn, stack="applied", user_id="u1")] == ["Acme"]
    assert db.search_jobs(conn, stack="applied", user_id="u2") == []
    # u2 sees both jobs in their to-apply pile; u1 sees only the one they haven't applied to.
    assert {r["company"] for r in db.search_jobs(conn, stack="to_apply", user_id="u2")} == {"Acme", "Beta"}
    assert {r["company"] for r in db.search_jobs(conn, stack="to_apply", user_id="u1")} == {"Beta"}


def test_top_fit_to_apply_is_per_user(conn):
    db.upsert_job(conn, _job("greenhouse:Acme:1", fit_score=90.0), user_id="u1")
    db.upsert_job(conn, _job("greenhouse:Acme:1", fit_score=90.0), user_id="u2")
    j1 = _job_id(conn, "greenhouse:Acme:1", "u1")
    j2 = _job_id(conn, "greenhouse:Acme:1", "u2")
    # Before u1 applies, the posting is applyable for both users.
    assert [r["id"] for r in db.top_fit_to_apply(conn, 5, "u1")] == [j1]
    assert [r["id"] for r in db.top_fit_to_apply(conn, 5, "u2")] == [j2]
    # After u1 applies it drops out of u1's pile but stays in u2's.
    db.set_application_status(conn, db.get_or_create_application(conn, j1, "u1"), "applied", user_id="u1")
    assert db.top_fit_to_apply(conn, 5, "u1") == []
    assert [r["id"] for r in db.top_fit_to_apply(conn, 5, "u2")] == [j2]


def test_local_mode_still_has_an_application_per_job(conn):
    # The local owner keeps an auto-created application on insert, so single-user
    # mode is wholly unchanged — job_with_application resolves an application_id.
    db.upsert_job(conn, _job())
    jid = _job_id(conn, "greenhouse:Acme:1")
    local_view = db.job_with_application(conn, jid)  # default user_id='local'
    assert local_view["application_id"] is not None
    assert local_view["status"] == "not_applied"
