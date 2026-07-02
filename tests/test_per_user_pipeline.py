"""Stage 2b: per-user pipeline foundation — resume stored in the DB, per-user
report/registry/seen-state paths, and ingest attributing to the right user.
Local (single-user) mode is unchanged: every default is 'local'.
"""

import json

import pytest

from jobsearch.config import load_settings
from jobsearch.resume import load_resume_text
from jobsearch.tracks import build_track
from webapp import db
from webapp.ingest import ingest_latest


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "data" / "jobsearch.db")
    yield c
    c.close()


# ------------------------------------------------------------- resume in DB ---
def test_resume_store_roundtrip_per_user(conn):
    assert db.get_resume(conn, "alice") is None
    db.set_resume(conn, "alice", "Alice is a data engineer.", pdf_name="alice.pdf")
    db.set_resume(conn, "bob", "Bob does frontend.")
    assert db.get_resume(conn, "alice") == "Alice is a data engineer."
    assert db.get_resume(conn, "bob") == "Bob does frontend."
    assert db.get_resume_meta(conn, "alice")["pdf_name"] == "alice.pdf"
    db.set_resume(conn, "alice", "Alice now does ML.")   # replace
    assert db.get_resume(conn, "alice") == "Alice now does ML."


def test_load_resume_local_file_is_source_of_truth(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sample_resume.txt").write_text("SAMPLE resume text")
    settings = load_settings(tmp_path / "config" / "settings.yaml")

    # Local: no file → bundled sample.
    assert load_resume_text(tmp_path, settings, "local") == ("SAMPLE resume text", True)
    # Local: data/resume.txt is the source of truth (a hand-edit must win).
    (tmp_path / "data" / "resume.txt").write_text("FILE resume text")
    assert load_resume_text(tmp_path, settings, "local") == ("FILE resume text", False)
    # A DB row must NOT override the local file (resume.txt stays authoritative).
    c = db.connect(tmp_path / "data" / "jobsearch.db")
    db.set_resume(c, "local", "STALE db text")
    c.close()
    assert load_resume_text(tmp_path, settings, "local")[0] == "FILE resume text"


def test_load_resume_nonlocal_uses_db_never_the_shared_file(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sample_resume.txt").write_text("SAMPLE resume text")
    (tmp_path / "data" / "resume.txt").write_text("OWNER resume")   # the local owner's
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    c = db.connect(tmp_path / "data" / "jobsearch.db")

    # A non-local user with no DB resume must fall back to the neutral SAMPLE —
    # never the owner's shared data/resume.txt (cross-tenant contamination).
    assert load_resume_text(tmp_path, settings, "alice") == ("SAMPLE resume text", True)
    # Their own DB resume wins.
    db.set_resume(c, "alice", "ALICE db resume")
    c.close()
    assert load_resume_text(tmp_path, settings, "alice") == ("ALICE db resume", False)


# ------------------------------------------------------ per-user track paths ---
def test_build_track_namespaces_paths_per_user(tmp_path):
    settings = load_settings(tmp_path / "config" / "settings.yaml")

    local = build_track(tmp_path, settings, "main", "local")
    assert local.reports_dir == tmp_path / "reports"          # unchanged
    assert local.state_file == tmp_path / "data" / "seen_jobs.tsv"

    alice = build_track(tmp_path, settings, "main", "alice")
    assert alice.reports_dir == tmp_path / "reports" / "users" / "alice"
    assert alice.state_file == tmp_path / "data" / "users" / "alice" / "seen_jobs.tsv"
    assert alice.corpus_dir == tmp_path / "data" / "users" / "alice" / "corpus"
    # Curated seed is SHARED across users (not namespaced).
    assert alice.curated_file == tmp_path / "config" / "companies.yaml"
    assert alice.user_id == "alice"

    su = build_track(tmp_path, settings, "startups", "alice")
    assert su.reports_dir == tmp_path / "reports" / "users" / "alice" / "startups"
    assert su.state_file == tmp_path / "data" / "users" / "alice" / "seen_jobs.startups.tsv"


# ------------------------------------------------------- per-user ingest ---
def test_ingest_latest_attributes_jobs_to_user(tmp_path, conn):
    root = tmp_path
    # Report lives under the per-user path build_track(alice) reads from.
    reports = root / "reports" / "users" / "alice"
    reports.mkdir(parents=True)
    (root / "data" / "users" / "alice" / "corpus").mkdir(parents=True)
    (reports / "latest.json").write_text(json.dumps({
        "generated": "2026-06-12T00:00:00+00:00", "company_fit": {},
        "jobs": [{"key": "greenhouse:Acme:1", "company": "Acme",
                  "title": "Data Engineer", "location": "NYC",
                  "url": "https://acme/1", "fit": 80.0, "rank_score": 60.0}],
        "near_miss": [],
    }))
    counts = ingest_latest(root, conn, user_id="alice")
    assert counts["inserted"] == 1
    # The job belongs to alice, not to the local owner.
    assert [j["company"] for j in db.search_jobs(conn, user_id="alice")] == ["Acme"]
    assert db.search_jobs(conn, user_id="local") == []
    # The company_search_runs audit row is attributed to alice too.
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM company_search_runs WHERE user_id = 'alice'"
    ).fetchone()["n"] >= 1
