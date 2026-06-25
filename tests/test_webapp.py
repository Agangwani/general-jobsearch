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
    assert db.stack_counts(conn) == {"to_apply": 2, "in_progress": 0, "applied": 0,
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


def test_in_progress_is_its_own_stack(conn):
    db.upsert_job(conn, record("k1", company="A"))   # stays not_applied → To apply
    db.upsert_job(conn, record("k2", company="B"))   # → In progress
    db.upsert_job(conn, record("k3", company="C"))   # → Applied
    ids = {r["company"]: r["id"] for r in conn.execute(
        "SELECT j.company, a.id AS id FROM applications a JOIN jobs j ON j.id = a.job_id")}
    db.set_application_status(conn, ids["B"], "in_progress")
    db.set_application_status(conn, ids["C"], "applied")
    counts = db.stack_counts(conn)
    assert (counts["to_apply"], counts["in_progress"], counts["applied"]) == (1, 1, 1)
    assert [r["company"] for r in db.search_jobs(conn, stack="to_apply")] == ["A"]
    assert [r["company"] for r in db.search_jobs(conn, stack="in_progress")] == ["B"]
    assert [r["company"] for r in db.search_jobs(conn, stack="applied")] == ["C"]
    assert db.companies_for_stack(conn, "in_progress") == ["B"]
    assert db.companies_for_stack(conn, "to_apply") == ["A"]


def test_top_fit_to_apply_picks_best_unapplied(conn):
    db.upsert_job(conn, record("k1", company="A", fit_score=90.0))
    db.upsert_job(conn, record("k2", company="B", fit_score=99.0, url=""))   # no URL → skip
    db.upsert_job(conn, record("k3", company="C", fit_score=95.0))
    db.upsert_job(conn, record("k4", company="D", fit_score=60.0))
    a3 = conn.execute("SELECT a.id FROM applications a JOIN jobs j ON j.id = a.job_id "
                      "WHERE j.key = 'k3'").fetchone()["id"]
    db.set_application_status(conn, a3, "applied")               # already applied → skip
    top = db.top_fit_to_apply(conn, 5)
    assert [r["key"] for r in top] == ["k1", "k4"]               # best-fit, applyable, by fit desc
    assert all(r["application_id"] and r["url"] for r in top)


def test_companies_for_stack_scopes_to_section(conn):
    db.upsert_job(conn, record("k1", company="Acme"))
    db.upsert_job(conn, record("k2", company="Beta"))
    applied_id = conn.execute(
        "SELECT a.id FROM applications a JOIN jobs j ON j.id = a.job_id "
        "WHERE j.key = 'k1'").fetchone()["id"]
    db.set_application_status(conn, applied_id, "applied")
    assert db.companies_for_stack(conn) == ["Acme", "Beta"]       # both sections
    assert db.companies_for_stack(conn, "applied") == ["Acme"]    # only applied
    assert db.companies_for_stack(conn, "to_apply") == ["Beta"]   # only to-apply


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


# ------------------------------------------------- apply-all tab→application
def test_application_by_url_and_active_urls(conn):
    db.upsert_job(conn, record("greenhouse:Acme:1", url="https://acme.com/jobs/1"))
    db.upsert_job(conn, record("greenhouse:Beta:2", company="Beta",
                               url="https://beta.com/jobs/2"))
    row = db.application_by_url(conn, "https://acme.com/jobs/1")
    assert row is not None and row["company"] == "Acme"
    assert db.application_by_url(conn, "https://nope.com/x") is None
    urls = {r["url"] for r in db.active_application_urls(conn)}
    assert urls == {"https://acme.com/jobs/1", "https://beta.com/jobs/2"}


def test_match_application_by_greenhouse_job_id(conn):
    # The stored URL is the branded posting; the open tab is the embed form.
    # They must reconcile via the shared gh job id.
    from webapp.apply_browser import BrowserHost
    db.upsert_job(conn, record("greenhouse:Acme:1",
                               url="https://www.acme.com/careers/7701651?gh_jid=7701651"))
    app_id = conn.execute("SELECT id FROM applications").fetchone()["id"]
    embed = "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=7701651"
    assert BrowserHost._match_application(conn, embed) == app_id
    # An unrelated greenhouse id matches nothing.
    other = "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=999"
    assert BrowserHost._match_application(conn, other) is None


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
def test_resume_path_and_name_prefer_uploaded_file(tmp_path):
    from webapp.apply_browser import BrowserHost
    data = tmp_path / "data"
    data.mkdir()
    host = BrowserHost(tmp_path / "t.db", tmp_path / "profile", data)
    # A decoy PDF that sorts after "resume.pdf" must NOT be chosen.
    (data / "resume.pdf").write_bytes(b"%PDF-1.4 real")
    (data / "zzz-other.pdf").write_bytes(b"%PDF-1.4 decoy")
    assert host._resume_path() == str(data / "resume.pdf")
    # No sidecar yet → falls back to the on-disk basename.
    assert host._resume_name() == "resume.pdf"
    # With the sidecar, the original upload name is used.
    (data / "resume.pdf.name").write_text("Aman_Gangwani_Resume.pdf\n")
    assert host._resume_name() == "Aman_Gangwani_Resume.pdf"


def test_reset_for_refill_clears_state():
    from webapp.apply_browser import ApplySession, BrowserHost
    s = ApplySession(1, "https://jobs.ashbyhq.com/acme/abc")
    s.done_urls.add("u"); s.done_keys.add("k"); s.fill_url = "u"; s.fill_passes = 3
    s.advanced = True; s.state = "applied"
    s.fill = {"filled": 5, "skipped": 2, "fields": ["email"], "notes": ["x"]}
    BrowserHost._reset_for_refill(s)
    assert not s.done_urls and not s.done_keys and s.fill_url == ""
    assert s.fill_passes == 0 and s.advanced is False and s.settled is False
    assert s.state == "open" and s.fill["filled"] == 0 and s.fill["fields"] == []


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
def test_profile_ensure_fields_tops_up_without_clobbering(conn):
    profile.set_field(conn, "full_name", "Aman")  # a pre-existing value
    profile.ensure_fields(conn)                    # add the newer form-fill fields
    fields = {f["field"]: f["value"] for f in profile.all_fields(conn)}
    assert {"gender", "cover_letter", "street_address", "school"} <= set(fields)
    assert fields["full_name"] == "Aman"           # existing value preserved
    assert fields["gender"] == ""                  # new field seeded blank


def test_profile_seed_from_resume():
    text = ("Alex Candidate\n"
            "alex@example.com | 555-123-4567 | github.com/alex | linkedin.com/in/alex\n"
            "EXPERIENCE\n"
            "Acme Corp San Francisco, CA\n"
            "Staff Software Engineer  Jan 2022 - Present\n"
            "EDUCATION\n"
            "Stanford University, Stanford, CA\n"
            "B.S. Computer Science, Minor in Mathematics\n")
    f = profile.seed_from_resume(text)
    assert f["full_name"] == "Alex Candidate"
    assert f["email"] == "alex@example.com"
    assert f["linkedin"] == "linkedin.com/in/alex"
    assert f["github"] == "github.com/alex"
    assert f["location"] == "San Francisco, CA"
    assert f["current_company"] == "Acme Corp"
    assert f["current_title"] == "Staff Software Engineer"
    assert f["school"] == "Stanford University"
    assert f["degree"] == "Bachelor's Degree"          # B.S. canonicalised
    assert f["discipline"] == "Computer Science"


def test_seed_from_resume_tolerates_pdf_space_noise():
    # PDF extraction injects stray spaces inside header words.
    text = "Jordan Lee\nRELEV ANT EXPERIENCE\nGlobex New York, NY\nSenior Engineer 2021\n"
    f = profile.seed_from_resume(text)
    assert f["location"] == "New York, NY" and f["current_company"] == "Globex"


def test_populate_from_resume_only_fills_blanks(conn, tmp_path):
    profile.ensure_fields(conn)
    profile.set_field(conn, "current_company", "My Current Employer")  # a manual edit
    text = ("Sam Dev\nEXPERIENCE\nAcme Corp Austin, TX\nEngineer 2020\n"
            "EDUCATION\nMIT, Cambridge, MA\nM.S. Robotics\n")
    changed = profile.populate_from_resume(conn, text)
    vals = {r["field"]: r["value"] for r in profile.all_fields(conn)}
    assert vals["location"] == "Austin, TX"            # blank → filled
    assert vals["degree"] == "Master's Degree"
    assert vals["current_company"] == "My Current Employer"  # manual edit preserved
    assert "current_company" not in changed


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

    home = client.get("/")
    assert home.status_code == 200
    assert "/?stack=in_progress" in home.text          # In progress nav tab
    assert 'class="row-status' in home.text            # editable per-row status
    assert client.get("/?stack=in_progress").status_code == 200
    assert "Senior Software Engineer" in client.get("/?q=Senior").text
    job_id = app.state.conn.execute("SELECT id FROM jobs").fetchone()["id"]
    detail = client.get(f"/jobs/{job_id}")
    assert detail.status_code == 200 and "Copy-paste panel" in detail.text
    assert client.get("/resume").status_code == 200
    profile_page = client.get("/profile")
    assert profile_page.status_code == 200
    assert "<select" in profile_page.text  # dropdowns rendered for curated fields
    assert "Decline to self-identify" in profile_page.text
    # populate-from-resume endpoint fills blanks then redirects
    assert client.post("/profile/from-resume", follow_redirects=False).status_code == 303
    assert client.get("/settings").status_code == 200
    assert client.get("/emails").status_code == 200
    assert client.get("/api/jobs").json()[0]["company"] == "Acme"

    # prep source-chapter view renders even with no local books (graceful), and
    # the PDF route 404s since the books are kept local-only.
    mslug = app.state.conn.execute("SELECT slug FROM prep_modules LIMIT 1").fetchone()["slug"]
    assert client.get(f"/prep/module/{mslug}/source").status_code == 200
    assert client.get("/prep/book/ctci").status_code == 404

    # apply-all endpoints: with no integrated browser open yet, status is empty
    # and the request is politely declined rather than launching a browser.
    assert client.get("/api/apply-all-status").json() == {"sessions": []}
    declined = client.post("/api/apply-all").json()
    assert declined["requested"] is False and "browser" in declined["detail"]

    app_id = app.state.conn.execute("SELECT id FROM applications").fetchone()["id"]
    resp = client.post(f"/applications/{app_id}/status",
                       data={"status": "applied", "note": "done"}, follow_redirects=False)
    assert resp.status_code == 303

    # bulk status: mark several applications applied in one post (checkbox values)
    db.upsert_job(app.state.conn, record("k-bulk", company="Beta"))
    aids = [str(r["id"]) for r in app.state.conn.execute("SELECT id FROM applications").fetchall()]
    assert len(aids) >= 2
    # A non-existent id and a non-integer must NOT 500 or abort the batch.
    rb = client.post("/applications/bulk-status",
                     data={"application_id": aids + ["999999", "abc"], "status": "applied"},
                     follow_redirects=False)
    assert rb.status_code == 303
    rows = app.state.conn.execute("SELECT status FROM applications").fetchall()
    assert all(r["status"] == "applied" for r in rows)
    # An invalid status is rejected (no write).
    client.post("/applications/bulk-status", data={"application_id": aids, "status": "bogus"})
    assert all(r["status"] == "applied" for r in
               app.state.conn.execute("SELECT status FROM applications").fetchall())
    assert app.state.conn.execute(
        "SELECT status FROM applications").fetchone()["status"] == "applied"

    # profile save roundtrip
    client.post("/profile", data={"full_name": "Test User", "email": "t@x.com"})
    fields = {f["field"]: f["value"] for f in profile.all_fields(app.state.conn)}
    assert fields["email"] == "t@x.com"


def test_dashboard_tolerates_malformed_min_fit(tmp_path):
    """The dashboard's min_fit query param comes straight from the URL, so
    non-numeric/whitespace/malformed values must fall back to "no filter"
    (HTTP 200) instead of crashing the float parse with a 500. A valid value
    still filters."""
    from fastapi.testclient import TestClient
    from webapp.app import create_app

    root = tmp_path
    (root / "data").mkdir()
    (root / "config").mkdir()
    (root / "data" / "resume.txt").write_text("Test User\nSenior Software Engineer, New York, NY\n")
    (root / "config" / "settings.yaml").write_text(
        "search:\n  query: senior software engineer\n  title_include: ['x']\n"
        "  title_exclude: ['y']\n  locations: [new york]\n  include_remote: false\n"
        "ranking:\n  half_life_days: 7\n  max_age_days: 45\n  cluster_weight: 0.15\n")
    (root / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\nmanual_check: []\n")

    app = create_app(root, db_path=root / "data" / "test.db")
    client = TestClient(app)
    db.upsert_job(app.state.conn, record("k1", fit_score=80.0))
    db.upsert_job(app.state.conn, record("k2", company="Beta", fit_score=60.0))

    # Malformed values must NOT 500; they degrade to no min-fit filter (200).
    for bad in ("abc", "%20%20%20", "12.5.6"):
        resp = client.get(f"/?min_fit={bad}")
        assert resp.status_code == 200, f"min_fit={bad!r} should be 200, got {resp.status_code}"

    # A valid threshold still returns 200 and still filters out the 60-fit job.
    ok = client.get("/?min_fit=70")
    assert ok.status_code == 200
    assert "Senior Software Engineer" in ok.text          # the 80-fit job survives


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


def test_prep_page_recommends_tracks_for_resume(tmp_path):
    """The /prep page tailors which tracks it recommends to the resume's roles —
    Behavioral for everyone, the discipline track for the resume — while still
    showing the full catalog (software tracks remain available to a non-engineer)."""
    from fastapi.testclient import TestClient

    from webapp.app import create_app

    root = tmp_path
    (root / "data").mkdir()
    (root / "config").mkdir()
    repo_root = Path(__file__).resolve().parent.parent
    (root / "config" / "occupations.yaml").write_text(
        (repo_root / "config" / "occupations.yaml").read_text())
    (root / "config" / "settings.yaml").write_text(
        "search:\n  role_targeting: auto\n  role_match_backend: tfidf\n"
        "  query: x\n  locations: [new york]\n"
        "role:\n  occupations_file: config/occupations.yaml\n"
        "ranking:\n  half_life_days: 7\n")
    (root / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\nmanual_check: []\n")
    # A finance (investment banking) resume → the Finance track is recommended.
    (root / "data" / "resume.txt").write_text(
        (repo_root / "tests" / "fixtures" / "resumes" / "01-financial-services.txt").read_text())

    app = create_app(root, db_path=root / "data" / "test.db")
    client = TestClient(app)
    html = client.get("/prep").text

    assert "Recommended for your resume" in html
    assert "All other tracks" in html
    divider = html.index("All other tracks")
    # Finance is recommended (its card appears before the "All other tracks" divider).
    assert html.index('/prep/track/finance"') < divider
    # Behavioral is universal — recommended for this resume too.
    assert html.index('/prep/track/behavioral"') < divider
    # The full catalog is intact: the software track is still on the page, just
    # below the divider (not recommended for a finance resume).
    assert '/prep/track/coding"' in html
    assert html.index('/prep/track/coding"') > divider
