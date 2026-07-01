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


# ---------------------------------------------------- part 4b: rescoring engine
from webapp import fit  # noqa: E402


def test_user_resume_storage(conn):
    assert db.get_user_resume(conn, "u1") == ""
    db.set_user_resume(conn, "u1", "my résumé text", "cv.pdf")
    assert db.get_user_resume(conn, "u1") == "my résumé text"
    db.set_user_resume(conn, "u1", "updated text", "cv2.pdf")  # idempotent overwrite
    assert db.get_user_resume(conn, "u1") == "updated text"
    assert db.users_with_resume(conn) == ["u1"]
    # The 'local' sentinel is never a re-score target (its fit is the pipeline's).
    db.set_user_resume(conn, "local", "local résumé")
    assert "local" not in db.users_with_resume(conn)


def test_rescore_user_writes_per_user_fit(conn):
    db.upsert_job(conn, _job("greenhouse:Acme:1", company="Acme", title="Backend Engineer",
                             description="python postgres backend distributed systems api services"))
    db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta", title="Frontend Engineer",
                             url="https://beta.co/2",
                             description="react typescript css frontend ui visual design layout"))
    acme, beta = _jid(conn, "greenhouse:Acme:1"), _jid(conn, "greenhouse:Beta:2")

    n = fit.rescore_user(conn, "u1", "python backend engineer with postgres and distributed systems")
    assert n == 2
    fa = conn.execute("SELECT fit_score FROM user_job_fit WHERE user_id='u1' AND job_id=?",
                      (acme,)).fetchone()["fit_score"]
    fb = conn.execute("SELECT fit_score FROM user_job_fit WHERE user_id='u1' AND job_id=?",
                      (beta,)).fetchone()["fit_score"]
    assert fa is not None and fb is not None
    assert fa >= fb                 # the backend résumé fits the backend job best
    assert max(fa, fb) == 100.0     # scores are scaled so the top match is 100
    # Isolated: another user with no re-score has no fit rows.
    assert conn.execute("SELECT COUNT(*) c FROM user_job_fit WHERE user_id='u2'").fetchone()["c"] == 0


def test_rescore_user_blank_resume_is_noop(conn):
    db.upsert_job(conn, _job(description="python backend postgres"))
    assert fit.rescore_user(conn, "u1", "   ") == 0
    assert conn.execute("SELECT COUNT(*) c FROM user_job_fit WHERE user_id='u1'").fetchone()["c"] == 0


def test_rescore_all_active_users_skips_local(conn):
    db.upsert_job(conn, _job(description="python backend postgres distributed systems services"))
    db.set_user_resume(conn, "u1", "python backend engineer postgres distributed systems")
    db.set_user_resume(conn, "local", "should be skipped — local fit is the pipeline's")
    results = fit.rescore_all_active_users(conn)
    assert "u1" in results and "local" not in results
    assert results["u1"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM user_job_fit WHERE user_id='u1'").fetchone()["c"] == 1


def _fit_client(tmp_path):
    from fastapi.testclient import TestClient
    from webapp.app import create_app
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "resume.txt").write_text("Test User\nSenior Software Engineer\n")
    (tmp_path / "config" / "settings.yaml").write_text(
        "search:\n  query: senior software engineer\n  locations: [new york]\n"
        "ranking:\n  half_life_days: 7\n")
    (tmp_path / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\nmanual_check: []\n")
    app = create_app(tmp_path, db_path=tmp_path / "data" / "test.db")
    return app, TestClient(app)


def test_upload_stores_resume_and_rescores(tmp_path):
    app, client = _fit_client(tmp_path)
    conn = app.state.conn
    db.upsert_job(conn, _job(description="python backend postgres distributed systems services"))
    jid = _jid(conn, "greenhouse:Acme:1")
    resume = ("Jane Engineer\nSenior Backend Engineer\n\nEXPERIENCE\n"
              "Built python postgres distributed backend systems and services for years.\n")
    resp = client.post("/resume/upload",
                       files={"file": ("resume.txt", resume.encode(), "text/plain")},
                       follow_redirects=False)
    assert resp.status_code == 303 and "uploaded=1" in resp.headers["location"]
    # Résumé persisted for the local user and matches were re-scored.
    assert db.get_user_resume(conn, "local").startswith("Jane Engineer")
    assert conn.execute(
        "SELECT COUNT(*) c FROM user_job_fit WHERE user_id='local' AND job_id=? "
        "AND fit_score IS NOT NULL", (jid,)).fetchone()["c"] == 1


def test_matches_refresh_route(tmp_path):
    app, client = _fit_client(tmp_path)
    conn = app.state.conn
    db.upsert_job(conn, _job(description="python backend postgres distributed systems services"))
    db.set_user_resume(conn, "local", "python backend engineer postgres distributed systems")
    resp = client.post("/matches/refresh", headers={"accept": "application/json"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] == 1 and body["has_resume"] is True
