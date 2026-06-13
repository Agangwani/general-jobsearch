"""Webapp tests: database semantics, ingest, email scaffold, apply heuristics,
and route smoke tests. Everything runs against a temp SQLite DB."""

import gzip
import json
import time
from pathlib import Path

import pytest

from webapp import db, emailmod, profile
from webapp.apply_browser import looks_like_confirmation
from webapp.ingest import ingest_latest


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def record(key="greenhouse:Acme:1", **kw):
    base = {
        "key": key, "source": "greenhouse", "company": "Acme",
        "title": "Senior Software Engineer", "location": "New York, NY",
        "url": "https://acme.com/jobs/1", "description": "Build backend systems.",
        "posted_at": "2026-06-10", "fit_score": 80.0, "rank_score": 60.0,
        "cluster": 2, "filter_reason": "", "validation": "", "validation_note": "",
    }
    base.update(kw)
    return base


# ------------------------------------------------------------------ database
def test_insert_sets_insertion_timestamp_and_application(conn):
    assert db.upsert_job(conn, record(), now="2026-06-12T10:00:00+00:00") == "inserted"
    row = conn.execute("SELECT * FROM jobs").fetchone()
    assert row["first_seen_at"] == "2026-06-12T10:00:00+00:00"  # exact run time
    assert row["last_seen_at"] == row["first_seen_at"]
    app_row = conn.execute("SELECT * FROM applications").fetchone()
    assert app_row["status"] == "not_applied"
    events = conn.execute("SELECT event_type FROM job_events").fetchall()
    assert [e["event_type"] for e in events] == ["inserted"]


def test_rerun_same_day_does_not_duplicate(conn):
    db.upsert_job(conn, record(), now="2026-06-12T10:00:00+00:00")
    assert db.upsert_job(conn, record(), now="2026-06-12T15:00:00+00:00") == "unchanged"
    rows = conn.execute("SELECT * FROM jobs").fetchall()
    assert len(rows) == 1
    assert rows[0]["first_seen_at"] == "2026-06-12T10:00:00+00:00"  # preserved
    assert rows[0]["last_seen_at"] == "2026-06-12T15:00:00+00:00"   # bumped


def test_patch_records_diff_event(conn):
    db.upsert_job(conn, record(fit_score=80.0))
    assert db.upsert_job(conn, record(fit_score=85.5, validation="verified")) == "updated"
    event = conn.execute(
        "SELECT payload FROM job_events WHERE event_type = 'updated'").fetchone()
    changes = json.loads(event["payload"])
    assert changes["fit_score"] == [80.0, 85.5]
    assert changes["validation"] == ["", "verified"]


def test_patch_never_erases_description(conn):
    db.upsert_job(conn, record(description="Long description."))
    db.upsert_job(conn, record(description=""))  # re-run without corpus snapshot
    assert conn.execute("SELECT description FROM jobs").fetchone()[0] == "Long description."


def test_status_lifecycle_and_stacks(conn):
    db.upsert_job(conn, record("greenhouse:Acme:1"))
    db.upsert_job(conn, record("greenhouse:Beta:2", company="Beta"))
    assert db.stack_counts(conn) == {"to_apply": 2, "applied": 0,
                                     "by_status": {"not_applied": 2}}
    app_id = conn.execute("SELECT id FROM applications LIMIT 1").fetchone()["id"]
    db.set_application_status(conn, app_id, "applied", via="integrated_browser")
    counts = db.stack_counts(conn)
    assert counts["to_apply"] == 1 and counts["applied"] == 1
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    assert row["applied_at"] and row["submitted_via"] == "integrated_browser"
    history = conn.execute(
        "SELECT status FROM application_events WHERE application_id = ?", (app_id,)).fetchall()
    assert [h["status"] for h in history] == ["applied"]


def test_search(conn):
    db.upsert_job(conn, record("k1", title="Senior Backend Engineer", description="payments fraud"))
    db.upsert_job(conn, record("k2", company="Beta", title="Senior ML Engineer"))
    assert len(db.search_jobs(conn, q="fraud")) == 1
    assert len(db.search_jobs(conn, company="Beta")) == 1
    assert len(db.search_jobs(conn, stack="applied")) == 0


def test_sort_by_fit(conn):
    db.upsert_job(conn, record("k1", fit_score=80.0))
    db.upsert_job(conn, record("k2", company="Beta", fit_score=60.0))
    desc = db.search_jobs(conn, sort_by="fit", sort_dir="desc")
    assert desc[0]["fit_score"] == 80.0 and desc[1]["fit_score"] == 60.0
    asc = db.search_jobs(conn, sort_by="fit", sort_dir="asc")
    assert asc[0]["fit_score"] == 60.0 and asc[1]["fit_score"] == 80.0


def test_sort_by_company(conn):
    db.upsert_job(conn, record("k1", company="Zebra"))
    db.upsert_job(conn, record("k2", company="Alpha"))
    asc = db.search_jobs(conn, sort_by="company", sort_dir="asc")
    assert asc[0]["company"] == "Alpha"
    desc = db.search_jobs(conn, sort_by="company", sort_dir="desc")
    assert desc[0]["company"] == "Zebra"


def test_min_fit_filter(conn):
    db.upsert_job(conn, record("k1", fit_score=80.0))
    db.upsert_job(conn, record("k2", company="Beta", fit_score=60.0))
    assert len(db.search_jobs(conn, min_fit=70.0)) == 1
    assert db.search_jobs(conn, min_fit=70.0)[0]["fit_score"] == 80.0
    assert len(db.search_jobs(conn, min_fit=50.0)) == 2


def test_status_filter(conn):
    db.upsert_job(conn, record("k1"))
    db.upsert_job(conn, record("k2", company="Beta"))
    app_id = conn.execute("SELECT id FROM applications WHERE job_id = "
                          "(SELECT id FROM jobs WHERE key = 'k1')").fetchone()["id"]
    db.set_application_status(conn, app_id, "applied")
    assert len(db.search_jobs(conn, status_filter="applied")) == 1
    assert len(db.search_jobs(conn, status_filter="not_applied")) == 1
    assert len(db.search_jobs(conn, status_filter="interviewing")) == 0


# -------------------------------------------------------------------- ingest
def test_ingest_latest(tmp_path, conn):
    root = tmp_path
    (root / "reports").mkdir()
    (root / "data" / "corpus").mkdir(parents=True)
    (root / "reports" / "latest.json").write_text(json.dumps({
        "generated": "2026-06-12T15:00:00+00:00",
        "company_fit": {},
        "jobs": [{"key": "greenhouse:Acme:1", "company": "Acme",
                  "title": "Senior Software Engineer", "location": "NYC",
                  "url": "https://acme.com/1", "posted": "2026-06-10",
                  "fit": 80.0, "rank_score": 60.0, "new": True, "cluster": 1,
                  "filter_reason": "", "validation": "", "validation_note": ""}],
        "near_miss": [{"key": "lever:Beta:2", "company": "Beta",
                       "title": "Backend Engineer", "location": "NYC",
                       "url": "https://beta.com/2", "posted": "unknown",
                       "fit": 70.0, "rank_score": 0, "new": False, "cluster": 2,
                       "filter_reason": "UNLEVELED_TITLE"}],
    }))
    with gzip.open(root / "data" / "corpus" / "2026-06-12.jsonl.gz", "wt") as fh:
        fh.write(json.dumps({"key": "greenhouse:Acme:1",
                             "description": "Full description here."}) + "\n")

    counts = ingest_latest(root, conn)
    assert (counts["inserted"], counts["updated"], counts["unchanged"]) == (2, 0, 0)
    assert counts["stale_unapplied"] == 0  # everything in the DB is in this report
    acme = conn.execute("SELECT * FROM jobs WHERE key = 'greenhouse:Acme:1'").fetchone()
    assert acme["description"] == "Full description here."  # joined from corpus
    beta = conn.execute("SELECT * FROM jobs WHERE key = 'lever:Beta:2'").fetchone()
    assert beta["filter_reason"] == "UNLEVELED_TITLE" and beta["posted_at"] is None

    counts2 = ingest_latest(root, conn)  # idempotent re-run
    assert counts2["inserted"] == 0 and len(conn.execute("SELECT * FROM jobs").fetchall()) == 2
    assert len(conn.execute("SELECT * FROM runs").fetchall()) == 2


def test_search_jobs_since_scopes_to_apply_but_keeps_engaged(conn):
    """`since` (the latest-run boundary) hides stale not-applied jobs but keeps
    any job the user has already started/applied to, regardless of run."""
    db.upsert_job(conn, record(key="greenhouse:Old:1", company="Old",
                               title="Senior Software Engineer"),
                  now="2026-06-10T10:00:00+00:00")
    db.upsert_job(conn, record(key="greenhouse:OldApplied:2", company="Old",
                               title="Staff Software Engineer"),
                  now="2026-06-10T10:00:00+00:00")
    db.upsert_job(conn, record(key="greenhouse:Fresh:3", company="Gainsight",
                               title="Senior Customer Success Manager"),
                  now="2026-06-13T10:00:00+00:00")
    # Mark the second old job as applied.
    app2 = conn.execute(
        "SELECT a.id FROM applications a JOIN jobs j ON j.id = a.job_id "
        "WHERE j.key = 'greenhouse:OldApplied:2'").fetchone()["id"]
    db.set_application_status(conn, app2, "applied", detail="x", via="test")

    boundary = "2026-06-13T10:00:00+00:00"
    scoped = {r["key"] for r in db.search_jobs(conn, since=boundary)}
    assert "greenhouse:Fresh:3" in scoped         # this run's to-apply job
    assert "greenhouse:OldApplied:2" in scoped     # engaged job kept across runs
    assert "greenhouse:Old:1" not in scoped        # stale not-applied: hidden

    everything = {r["key"] for r in db.search_jobs(conn, since="")}
    assert "greenhouse:Old:1" in everything        # all-runs view shows it


def test_ingest_flags_stale_to_apply_jobs(tmp_path, conn):
    """A later run targeting different roles leaves the earlier run's unapplied
    jobs in the DB; ingest reports them as stale so the dashboard's leftovers
    are explained, not mysterious."""
    root = tmp_path
    (root / "reports").mkdir()
    (root / "data" / "corpus").mkdir(parents=True)

    def write_report(job):
        (root / "reports" / "latest.json").write_text(json.dumps({
            "generated": "2026-06-12T15:00:00+00:00", "company_fit": {},
            "jobs": [job], "near_miss": []}))

    swe = {"key": "greenhouse:Acme:1", "company": "Acme",
           "title": "Senior Software Engineer", "location": "NYC",
           "url": "https://acme.com/1", "posted": "2026-06-10", "fit": 80.0,
           "rank_score": 60.0, "new": True, "cluster": 1, "filter_reason": "",
           "validation": "", "validation_note": ""}
    write_report(swe)
    assert ingest_latest(root, conn)["stale_unapplied"] == 0

    # Second run targets a Customer Success role — the SWE job is now stale.
    csm = {**swe, "key": "greenhouse:Gainsight:9", "company": "Gainsight",
           "title": "Senior Customer Success Manager"}
    write_report(csm)
    counts = ingest_latest(root, conn)
    assert counts["inserted"] == 1
    assert counts["stale_unapplied"] == 1  # the leftover SWE job from run one


# ----------------------------------------------------- apply browser heuristic
def test_confirmation_detection():
    assert looks_like_confirmation("https://x.com/apply/confirmation")
    assert looks_like_confirmation("https://x.com/thank-you")
    assert looks_like_confirmation("https://x.com/jobs/1", body_text="Thank you for applying to Acme!")
    assert looks_like_confirmation("https://x.com/jobs/1", body_text="Your application has been submitted.")
    assert not looks_like_confirmation("https://x.com/jobs/1/apply", title="Apply now",
                                       body_text="Submit your application below.")


# --------------------------------------------------------------- email module
def test_email_classify_and_match(conn):
    db.upsert_job(conn, record(company="Datadog", key="greenhouse:Datadog:9"))
    app_id = conn.execute("SELECT id FROM applications").fetchone()["id"]
    db.set_application_status(conn, app_id, "applied")

    outcome = emailmod.store_message(conn, {
        "message_id": "m1", "from_addr": "no-reply@datadog.com",
        "subject": "Your application was received",
        "body": "Thanks for applying to Datadog.", "sent_at": "2026-06-12T16:00:00Z",
    })
    assert outcome == "confirmation"
    msg = conn.execute("SELECT * FROM email_messages").fetchone()
    assert msg["application_id"] == app_id  # auto-linked by sender domain
    status = conn.execute("SELECT status FROM applications WHERE id = ?", (app_id,)).fetchone()
    assert status["status"] == "confirmed"  # confirmation advanced the lifecycle
    assert emailmod.store_message(conn, {"message_id": "m1"}) == "duplicate"


def test_email_classifier_labels():
    assert emailmod.classify("Interview availability", "When are you free for a phone screen?") == "interview"
    assert emailmod.classify("Update on your application", "we decided to pursue other candidates") == "rejection"
    assert emailmod.classify("Newsletter", "engineering blog digest") == "other"


# -------------------------------------------------------------------- profile
def test_profile_seed_from_resume():
    text = ("Alex Candidate\nSenior Software Engineer, New York, NY\n"
            "alex@example.com | 555-123-4567 | linkedin.com/in/alex | github.com/alex\n")
    fields = profile.seed_from_resume(text)
    assert fields["full_name"] == "Alex Candidate"
    assert fields["current_title"] == "Senior Software Engineer"
    assert fields["email"] == "alex@example.com"
    assert fields["linkedin"] == "linkedin.com/in/alex"


# ------------------------------------------------------------ route smoke test
def test_routes(tmp_path):
    from fastapi.testclient import TestClient
    from webapp.app import create_app

    root = tmp_path
    (root / "data").mkdir()
    (root / "config").mkdir()
    (root / "data" / "resume.txt").write_text("Test User\nSenior Software Engineer, New York, NY\n\nEXPERIENCE\nDid things.")
    (root / "config" / "settings.yaml").write_text(
        "search:\n  query: senior software engineer\n  title_include: ['x']\n"
        "  title_exclude: ['y']\n  locations: [new york]\n  include_remote: false\n"
        "ranking:\n  half_life_days: 7\n  max_age_days: 45\n  cluster_weight: 0.15\n")
    (root / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\nmanual_check: []\n")

    app = create_app(root, db_path=root / "data" / "test.db")
    client = TestClient(app)
    db.upsert_job(app.state.conn, record())

    assert client.get("/").status_code == 200
    assert "Senior Software Engineer" in client.get("/?q=Senior").text
    job_id = app.state.conn.execute("SELECT id FROM jobs").fetchone()["id"]
    detail = client.get(f"/jobs/{job_id}")
    assert detail.status_code == 200 and "Copy-paste panel" in detail.text
    assert client.get("/resume").status_code == 200
    assert client.get("/profile").status_code == 200
    assert client.get("/settings").status_code == 200
    assert client.get("/emails").status_code == 200
    assert client.get("/api/jobs").json()[0]["company"] == "Acme"

    app_id = app.state.conn.execute("SELECT id FROM applications").fetchone()["id"]
    resp = client.post(f"/applications/{app_id}/status",
                       data={"status": "applied", "note": "done"}, follow_redirects=False)
    assert resp.status_code == 303
    assert app.state.conn.execute(
        "SELECT status FROM applications").fetchone()["status"] == "applied"

    # profile save roundtrip
    client.post("/profile", data={"full_name": "Test User", "email": "t@x.com"})
    fields = {f["field"]: f["value"] for f in profile.all_fields(app.state.conn)}
    assert fields["email"] == "t@x.com"


def test_resume_role_panel_and_run_trigger(tmp_path, monkeypatch):
    """The /resume page shows the resume's target roles, and the run button
    triggers the pipeline (mocked) in the background."""
    from fastapi.testclient import TestClient

    from jobsearch import pipeline
    from webapp.app import create_app

    root = tmp_path
    (root / "data").mkdir()
    (root / "config").mkdir()
    repo_config = Path(__file__).resolve().parent.parent / "config"
    (root / "config" / "occupations.yaml").write_text(
        (repo_config / "occupations.yaml").read_text())
    (root / "config" / "settings.yaml").write_text(
        "search:\n  role_targeting: auto\n  role_match_backend: tfidf\n"
        "  query: senior software engineer\n  locations: [new york]\n"
        "role:\n  occupations_file: config/occupations.yaml\n"
        "ranking:\n  half_life_days: 7\n")
    (root / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\nmanual_check: []\n")
    (root / "data" / "resume.txt").write_text(
        "Senior Customer Success Specialist. 20 years EdTech, cloud, consulting. "
        "Agile project manager, scrum, stakeholder management, trusted advisor, "
        "customer success, account management, transformation roadmaps. Director.")

    app = create_app(root, db_path=root / "data" / "test.db")
    client = TestClient(app)

    page = client.get("/resume")
    assert page.status_code == 200
    assert "Target roles for this resume" in page.text
    # The CS resume must surface a customer-facing role, never Software Engineer.
    assert "Customer Success Manager" in page.text
    assert "Run pipeline for these roles" in page.text

    calls = []
    monkeypatch.setattr(pipeline, "run", lambda r: calls.append(r) or 0)
    resp = client.post("/resume/run", follow_redirects=False)
    assert resp.status_code == 303
    # Background thread runs the (mocked) pipeline.
    for _ in range(50):
        if calls:
            break
        time.sleep(0.02)
    assert calls == [root]
