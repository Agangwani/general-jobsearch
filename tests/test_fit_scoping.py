"""Stage 2b: per-user résumé-fit isolation.

Jobs are per-user rows (Stage 2a), so fit_score/rank_score/cluster on a row
already belong to exactly one account — each user's matches are theirs alone.
webapp/fit.py re-scores a user's résumé against their own active rows (on
upload, on "refresh matches", and via the daily worker). These run on SQLite
(the default backend)."""

import pytest

from webapp import db, fit


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


def _jid(conn, key, user_id="local"):
    return conn.execute("SELECT id FROM jobs WHERE user_id = ? AND key = ?",
                        (user_id, key)).fetchone()["id"]


def test_upsert_job_stores_pipeline_fit_on_the_row(conn):
    # The pipeline's scores land on the owner's job row and read straight back.
    db.upsert_job(conn, _job(fit_score=80.0, rank_score=60.0, cluster=2))
    jid = _jid(conn, "greenhouse:Acme:1")
    view = db.job_with_application(conn, jid)
    assert view["fit_score"] == 80.0 and view["rank_score"] == 60.0 and view["cluster"] == 2


def test_fit_is_isolated_per_user(conn):
    # The same posting held by two users = two rows, each carrying its own fit.
    db.upsert_job(conn, _job(fit_score=90.0), user_id="u1")
    db.upsert_job(conn, _job(fit_score=40.0), user_id="u2")
    j1, j2 = _jid(conn, "greenhouse:Acme:1", "u1"), _jid(conn, "greenhouse:Acme:1", "u2")

    assert db.job_with_application(conn, j1, "u1")["fit_score"] == 90.0
    assert db.job_with_application(conn, j2, "u2")["fit_score"] == 40.0
    # Another user can't read either row at all (tenant isolation).
    assert db.job_with_application(conn, j1, "u3") is None


def test_min_fit_and_sort_are_per_user(conn):
    # u1 fits Acme better; u2 fits Beta better — on their own rows.
    db.upsert_job(conn, _job("greenhouse:Acme:1", fit_score=90.0, rank_score=90.0), user_id="u1")
    db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta", url="https://beta.co/2",
                             fit_score=50.0, rank_score=50.0), user_id="u1")
    db.upsert_job(conn, _job("greenhouse:Acme:1", fit_score=40.0, rank_score=40.0), user_id="u2")
    db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta", url="https://beta.co/2",
                             fit_score=85.0, rank_score=85.0), user_id="u2")

    # min_fit filters on the *current user's* fit.
    assert [r["company"] for r in db.search_jobs(conn, min_fit=70.0, user_id="u1")] == ["Acme"]
    assert [r["company"] for r in db.search_jobs(conn, min_fit=70.0, user_id="u2")] == ["Beta"]
    # Default order (rank_score desc) is per-user too.
    assert [r["company"] for r in db.search_jobs(conn, user_id="u1")] == ["Acme", "Beta"]
    assert [r["company"] for r in db.search_jobs(conn, user_id="u2")] == ["Beta", "Acme"]
    # Explicit sort-by-fit likewise.
    assert [r["company"] for r in db.search_jobs(conn, sort_by="fit", user_id="u2")] == ["Beta", "Acme"]


def test_top_fit_to_apply_uses_per_user_fit(conn):
    db.upsert_job(conn, _job("greenhouse:Acme:1", fit_score=30.0, rank_score=30.0), user_id="u1")
    db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta", url="https://beta.co/2",
                             fit_score=95.0, rank_score=95.0), user_id="u1")
    top = db.top_fit_to_apply(conn, 5, "u1")
    assert [r["company"] for r in top] == ["Beta", "Acme"]  # u1's best fit first


def test_local_mode_fit_unchanged(conn):
    # Single-user mode: fit read via the default 'local' user matches the job's
    # ingested pipeline scores exactly.
    db.upsert_job(conn, _job(fit_score=72.5, rank_score=61.0, cluster=4))
    assert db.search_jobs(conn, min_fit=70.0)[0]["fit_score"] == 72.5
    assert db.search_jobs(conn, min_fit=80.0) == []  # 72.5 < 80 → filtered out


# ---------------------------------------------------- part 4b: rescoring engine


def test_user_resume_storage(conn):
    assert db.get_resume(conn, "u1") is None
    db.set_resume(conn, "u1", "my résumé text", "cv.pdf")
    assert db.get_resume(conn, "u1") == "my résumé text"
    db.set_resume(conn, "u1", "updated text", "cv2.pdf")  # idempotent overwrite
    assert db.get_resume(conn, "u1") == "updated text"
    assert db.users_with_resume(conn) == ["u1"]
    # The 'local' sentinel is never a re-score target (its fit is the pipeline's).
    db.set_resume(conn, "local", "local résumé")
    assert "local" not in db.users_with_resume(conn)


def test_rescore_user_writes_fit_onto_the_users_rows(conn):
    db.upsert_job(conn, _job("greenhouse:Acme:1", company="Acme", title="Backend Engineer",
                             fit_score=None, rank_score=None,
                             description="python postgres backend distributed systems api services"),
                  user_id="u1")
    db.upsert_job(conn, _job("greenhouse:Beta:2", company="Beta", title="Frontend Engineer",
                             url="https://beta.co/2", fit_score=None, rank_score=None,
                             description="react typescript css frontend ui visual design layout"),
                  user_id="u1")
    acme = _jid(conn, "greenhouse:Acme:1", "u1")
    beta = _jid(conn, "greenhouse:Beta:2", "u1")

    n = fit.rescore_user(conn, "u1", "python backend engineer with postgres and distributed systems")
    assert n == 2
    fa = conn.execute("SELECT fit_score FROM jobs WHERE id = ?", (acme,)).fetchone()["fit_score"]
    fb = conn.execute("SELECT fit_score FROM jobs WHERE id = ?", (beta,)).fetchone()["fit_score"]
    assert fa is not None and fb is not None
    assert fa >= fb                 # the backend résumé fits the backend job best
    assert max(fa, fb) == 100.0     # scores are scaled so the top match is 100
    # Isolated: another user's rows are untouched (they have none here).
    assert conn.execute(
        "SELECT COUNT(*) c FROM jobs WHERE user_id = 'u2'").fetchone()["c"] == 0


def test_rescore_user_blank_resume_is_noop(conn):
    db.upsert_job(conn, _job(fit_score=80.0, description="python backend postgres"),
                  user_id="u1")
    assert fit.rescore_user(conn, "u1", "   ") == 0
    jid = _jid(conn, "greenhouse:Acme:1", "u1")
    assert conn.execute("SELECT fit_score FROM jobs WHERE id = ?",
                        (jid,)).fetchone()["fit_score"] == 80.0  # unchanged


def test_rescore_only_touches_that_users_rows(conn):
    db.upsert_job(conn, _job(fit_score=80.0,
                             description="python backend postgres distributed systems"),
                  user_id="u1")
    db.upsert_job(conn, _job(fit_score=80.0,
                             description="python backend postgres distributed systems"),
                  user_id="u2")
    fit.rescore_user(conn, "u1", "python backend engineer postgres distributed systems")
    j2 = _jid(conn, "greenhouse:Acme:1", "u2")
    assert conn.execute("SELECT fit_score FROM jobs WHERE id = ?",
                        (j2,)).fetchone()["fit_score"] == 80.0  # u2 untouched


def test_rescore_all_active_users_skips_local(conn):
    db.upsert_job(conn, _job(description="python backend postgres distributed systems services"),
                  user_id="u1")
    db.set_resume(conn, "u1", "python backend engineer postgres distributed systems")
    db.set_resume(conn, "local", "should be skipped — local fit is the pipeline's")
    results = fit.rescore_all_active_users(conn)
    assert "u1" in results and "local" not in results
    assert results["u1"] == 1


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
    db.upsert_job(conn, _job(fit_score=80.0,
                             description="python backend postgres distributed systems services"))
    jid = _jid(conn, "greenhouse:Acme:1")
    resume = ("Jane Engineer\nSenior Backend Engineer\n\nEXPERIENCE\n"
              "Built python postgres distributed backend systems and services for years.\n")
    resp = client.post("/resume/upload",
                       files={"file": ("resume.txt", resume.encode(), "text/plain")},
                       follow_redirects=False)
    assert resp.status_code == 303 and "uploaded=1" in resp.headers["location"]
    # Résumé persisted for the local user and matches were re-scored (the sole
    # job in the corpus becomes the top match, scaled to 100).
    assert db.get_resume(conn, "local").startswith("Jane Engineer")
    assert conn.execute("SELECT fit_score FROM jobs WHERE id = ?",
                        (jid,)).fetchone()["fit_score"] == 100.0


def test_matches_refresh_route(tmp_path):
    app, client = _fit_client(tmp_path)
    conn = app.state.conn
    db.upsert_job(conn, _job(description="python backend postgres distributed systems services"))
    db.set_resume(conn, "local", "python backend engineer postgres distributed systems")
    resp = client.post("/matches/refresh", headers={"accept": "application/json"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] == 1 and body["has_resume"] is True
