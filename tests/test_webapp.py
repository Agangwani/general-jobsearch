"""Webapp tests: database semantics, ingest, email scaffold, apply heuristics,
and route smoke tests. Everything runs against a temp SQLite DB."""

import gzip
import json
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
    assert counts == {"inserted": 2, "updated": 0, "unchanged": 0}
    acme = conn.execute("SELECT * FROM jobs WHERE key = 'greenhouse:Acme:1'").fetchone()
    assert acme["description"] == "Full description here."  # joined from corpus
    beta = conn.execute("SELECT * FROM jobs WHERE key = 'lever:Beta:2'").fetchone()
    assert beta["filter_reason"] == "UNLEVELED_TITLE" and beta["posted_at"] is None

    counts2 = ingest_latest(root, conn)  # idempotent re-run
    assert counts2["inserted"] == 0 and len(conn.execute("SELECT * FROM jobs").fetchall()) == 2
    assert len(conn.execute("SELECT * FROM runs").fetchall()) == 2


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
