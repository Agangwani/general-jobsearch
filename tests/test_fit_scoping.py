"""Stage 2b: per-user résumé-fit isolation.

fit_score/rank_score/cluster were single-user columns on jobs; they now live in
user_job_fit keyed by (user_id, job_id) so each account sees its own matches.
The dashboard reads fit through that table LEFT JOINed on the current user. The
local owner's fit mirrors the pipeline's (owner) scores, copied in on ingest, so
single-user mode is unchanged. These run on SQLite (the default backend)."""

import pytest

from webapp import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "fit.db")
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


def _jid(conn, key):
    return conn.execute("SELECT id FROM jobs WHERE key = ?", (key,)).fetchone()["id"]


def test_upsert_job_mirrors_pipeline_fit_into_local(conn):
    # The pipeline's (owner) fit lands in jobs AND is mirrored into the local
    # user's per-user fit, so single-user reads resolve from user_job_fit.
    db.upsert_job(conn, _job(fit_score=80.0, rank_score=60.0, cluster=2))
    jid = _jid(conn, "greenhouse:Acme:1")
    row = conn.execute(
        "SELECT * FROM user_job_fit WHERE user_id = 'local' AND job_id = ?",
        (jid,)).fetchone()
    assert row["fit_score"] == 80.0 and row["rank_score"] == 60.0 and row["cluster"] == 2
    # And job_with_application (default local) reads that fit back.
    view = db.job_with_application(conn, jid)
    assert view["fit_score"] == 80.0 and view["rank_score"] == 60.0 and view["cluster"] == 2


def test_fit_is_isolated_per_user(conn):
    db.upsert_job(conn, _job())
    jid = _jid(conn, "greenhouse:Acme:1")
    db.upsert_user_fit(conn, "u1", jid, 90.0, 88.0, 3)
    db.upsert_user_fit(conn, "u2", jid, 40.0, 30.0, 1)

    assert db.job_with_application(conn, jid, "u1")["fit_score"] == 90.0
    assert db.job_with_application(conn, jid, "u2")["fit_score"] == 40.0
    # A user with no fit row sees no score (NULL), not another user's.
    assert db.job_with_application(conn, jid, "u3")["fit_score"] is None


def test_upsert_user_fit_is_idempotent(conn):
    db.upsert_job(conn, _job())
    jid = _jid(conn, "greenhouse:Acme:1")
    db.upsert_user_fit(conn, "u1", jid, 50.0, 40.0, 0)
    db.upsert_user_fit(conn, "u1", jid, 75.0, 70.0, 2)  # overwrite, not duplicate
    rows = conn.execute(
        "SELECT fit_score, cluster FROM user_job_fit WHERE user_id = 'u1' AND job_id = ?",
        (jid,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["fit_score"] == 75.0 and rows[0]["cluster"] == 2


def test_min_fit_and_sort_are_per_user(conn):
    db.upsert_job(conn, _job("greenhouse:Acme:1"))
    db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta", url="https://beta.co/2"))
    acme, beta = _jid(conn, "greenhouse:Acme:1"), _jid(conn, "greenhouse:Beta:2")
    # u1 fits Acme better; u2 fits Beta better.
    db.upsert_user_fit(conn, "u1", acme, 90.0, 90.0, 0)
    db.upsert_user_fit(conn, "u1", beta, 50.0, 50.0, 0)
    db.upsert_user_fit(conn, "u2", acme, 40.0, 40.0, 0)
    db.upsert_user_fit(conn, "u2", beta, 85.0, 85.0, 0)

    # min_fit filters on the *current user's* fit.
    assert [r["company"] for r in db.search_jobs(conn, min_fit=70.0, user_id="u1")] == ["Acme"]
    assert [r["company"] for r in db.search_jobs(conn, min_fit=70.0, user_id="u2")] == ["Beta"]
    # Default order (rank_score desc) is per-user too.
    assert [r["company"] for r in db.search_jobs(conn, user_id="u1")] == ["Acme", "Beta"]
    assert [r["company"] for r in db.search_jobs(conn, user_id="u2")] == ["Beta", "Acme"]
    # Explicit sort-by-fit likewise.
    assert [r["company"] for r in db.search_jobs(conn, sort_by="fit", user_id="u2")] == ["Beta", "Acme"]


def test_top_fit_to_apply_uses_per_user_fit(conn):
    db.upsert_job(conn, _job("greenhouse:Acme:1"))
    db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta", url="https://beta.co/2"))
    acme, beta = _jid(conn, "greenhouse:Acme:1"), _jid(conn, "greenhouse:Beta:2")
    db.upsert_user_fit(conn, "u1", acme, 30.0, 30.0, 0)
    db.upsert_user_fit(conn, "u1", beta, 95.0, 95.0, 0)
    top = db.top_fit_to_apply(conn, 5, "u1")
    assert [r["company"] for r in top] == ["Beta", "Acme"]  # u1's best fit first


def test_local_mode_fit_unchanged(conn):
    # Single-user mode: fit read via the default 'local' user matches the job's
    # ingested pipeline scores exactly.
    db.upsert_job(conn, _job(fit_score=72.5, rank_score=61.0, cluster=4))
    jid = _jid(conn, "greenhouse:Acme:1")
    assert db.search_jobs(conn, min_fit=70.0)[0]["fit_score"] == 72.5
    assert db.search_jobs(conn, min_fit=80.0) == []  # 72.5 < 80 → filtered out
