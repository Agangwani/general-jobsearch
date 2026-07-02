"""Stage 2a: per-user data isolation for jobs / applications / startups.

Two users must not see or mutate each other's job data, the same pipeline key
must be able to coexist under two owners, and the startup-flag pass must never
relabel another tenant's jobs. Local single-user callers keep the default
LOCAL_USER_ID and are unaffected (covered by the rest of the suite).
"""

import pytest

from webapp import db

A = "user-a"
B = "user-b"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "iso.db")
    yield c
    c.close()


def _job(conn, key, company, user_id, **kw):
    rec = {"key": key, "source": key.split(":")[0], "company": company,
           "title": "Engineer", "location": "NYC", "url": f"https://x/{key}",
           "fit_score": 80.0}
    rec.update(kw)
    return db.upsert_job(conn, rec, user_id=user_id)


def _app_id(conn, user_id):
    job = db.search_jobs(conn, user_id=user_id)[0]
    return db.job_with_application(conn, job["id"], user_id)["application_id"]


def test_same_key_two_users_coexist(conn):
    # The pipeline key is unique only WITHIN an owner now (composite UNIQUE):
    # before Stage 2a the inline UNIQUE(key) made the 2nd insert an 'update'.
    assert _job(conn, "greenhouse:Acme:1", "Acme", A) == "inserted"
    assert _job(conn, "greenhouse:Acme:1", "Acme", B) == "inserted"
    assert len(conn.execute("SELECT * FROM jobs").fetchall()) == 2


def test_search_and_counts_isolated(conn):
    _job(conn, "g:Acme:1", "Acme", A)
    _job(conn, "g:Beta:2", "Beta", B)
    assert [r["company"] for r in db.search_jobs(conn, user_id=A)] == ["Acme"]
    assert [r["company"] for r in db.search_jobs(conn, user_id=B)] == ["Beta"]
    assert db.stack_counts(conn, A)["to_apply"] == 1
    assert db.stack_counts(conn, B)["to_apply"] == 1
    assert db.companies_for_stack(conn, user_id=A) == ["Acme"]
    assert db.top_fit_to_apply(conn, user_id=B)[0]["company"] == "Beta"


def test_job_with_application_scoped(conn):
    _job(conn, "g:Acme:1", "Acme", A)
    job_id = db.search_jobs(conn, user_id=A)[0]["id"]
    assert db.job_with_application(conn, job_id, A) is not None
    assert db.job_with_application(conn, job_id, B) is None   # B can't see A's job


def test_set_application_status_cross_tenant_blocked(conn):
    _job(conn, "g:Acme:1", "Acme", A)
    app_id = _app_id(conn, A)
    db.set_application_status(conn, app_id, "applied", user_id=A)      # owner ok
    with pytest.raises(ValueError):                                    # forged id → no-op
        db.set_application_status(conn, app_id, "rejected", user_id=B)
    assert db.job_with_application(
        conn, db.search_jobs(conn, user_id=A)[0]["id"], A)["status"] == "applied"


def test_refresh_startup_flags_scoped(conn):
    # A knows Acme is a startup; B has an Acme job but an empty startup roster.
    _job(conn, "g:Acme:1", "Acme", A)
    _job(conn, "g:Acme:9", "Acme", B)
    db.upsert_startup_company(conn, {"name": "Acme"}, user_id=A)
    assert db.refresh_startup_flags(conn, A) == 1     # only A's job flagged
    assert db.refresh_startup_flags(conn, B) == 0     # B's roster is empty
    flags = {(r["user_id"], r["company"]): r["is_startup"]
             for r in conn.execute("SELECT user_id, company, is_startup FROM jobs")}
    assert flags[(A, "Acme")] == 1
    assert flags[(B, "Acme")] == 0                    # NOT relabelled by A's roster


def test_startup_facts_scoped(conn):
    db.upsert_startup_company(conn, {"name": "Acme", "employees": "50"}, user_id=A)
    assert db.startup_company_for(conn, "Acme", A)["employees"] == "50"
    assert db.startup_company_for(conn, "Acme", B) is None
    assert len(db.startup_keys(conn, A)) == 1 and db.startup_keys(conn, B) == set()
    assert [s["name"] for s in db.list_startups(conn, user_id=A)] == ["Acme"]
    assert db.list_startups(conn, user_id=B) == []


def test_same_company_two_users_startup_independent(conn):
    db.upsert_startup_company(conn, {"name": "Acme", "employees": "10"}, user_id=A)
    db.upsert_startup_company(conn, {"name": "Acme", "employees": "999"}, user_id=B)
    assert db.startup_company_for(conn, "Acme", A)["employees"] == "10"
    assert db.startup_company_for(conn, "Acme", B)["employees"] == "999"
