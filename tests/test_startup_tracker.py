"""Startup tracker integration: DB metadata + flags, the startup/non-startup
toggle, two-track ingest, and the startup web routes."""

import gzip
import json

import pytest

from webapp import db
from webapp.ingest import ingest_latest


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def _job(conn, key, company, **kw):
    rec = {"key": key, "source": key.split(":")[0], "company": company,
           "title": "Senior Engineer", "location": "New York, NY",
           "url": f"https://x/{key}", "fit_score": 80.0}
    rec.update(kw)
    db.upsert_job(conn, rec)


# ------------------------------------------------------------- metadata ---
def test_upsert_and_decode_startup(conn):
    db.upsert_startup_company(conn, {
        "name": "Ramp, Inc.", "employees": "900", "stage": "Series D",
        "investors": ["Y Combinator", "Founders Fund"], "top_company": True})
    su = db.startup_company_for(conn, "Ramp")     # normalized lookup
    assert su["employees"] == "900"
    assert su["investors"] == ["Y Combinator", "Founders Fund"]   # JSON decoded
    assert su["top_company"] is True


def test_ingest_merge_unions_investors_but_user_edit_wins(conn):
    db.upsert_startup_company(conn, {"name": "Ramp", "investors": ["Y Combinator"]})
    # a later discovery sees another investor → unioned
    db.upsert_startup_company(conn, {"name": "Ramp", "investors": ["Sequoia"],
                                     "employees": "950"})
    su = db.startup_company_for(conn, "Ramp")
    assert su["investors"] == ["Y Combinator", "Sequoia"]
    assert su["employees"] == "950"
    # user edits, then re-ingest must not clobber
    db.upsert_startup_company(conn, {"name": "Ramp", "employees": "1000"}, from_user=True)
    assert db.upsert_startup_company(conn, {"name": "Ramp", "employees": "5"}) == "skipped"
    assert db.startup_company_for(conn, "Ramp")["employees"] == "1000"


# ----------------------------------------------------------- flags + scope ---
def test_refresh_flags_and_startup_scope(conn):
    _job(conn, "ashby:Ramp:1", "Ramp")
    _job(conn, "greenhouse:Google:2", "Google")
    db.upsert_startup_company(conn, {"name": "Ramp"})
    assert db.refresh_startup_flags(conn) == 1            # only Ramp flagged
    flags = {r["company"]: r["is_startup"] for r in conn.execute(
        "SELECT company, is_startup FROM jobs")}
    assert flags == {"Ramp": 1, "Google": 0}

    only = db.search_jobs(conn, startup_scope="only")
    hide = db.search_jobs(conn, startup_scope="hide")
    both = db.search_jobs(conn, startup_scope="")
    assert [r["company"] for r in only] == ["Ramp"]
    assert [r["company"] for r in hide] == ["Google"]
    assert len(both) == 2


def test_stack_counts_split(conn):
    _job(conn, "ashby:Ramp:1", "Ramp")
    _job(conn, "greenhouse:Google:2", "Google")
    db.upsert_startup_company(conn, {"name": "Ramp"})
    db.refresh_startup_flags(conn)
    counts = db.stack_counts(conn)
    assert counts["to_apply"] == 2
    assert counts["startup_total"] == 1 and counts["other_total"] == 1
    assert counts["startup"]["to_apply"] == 1
    assert counts["other"]["to_apply"] == 1


def test_list_startups_with_job_counts(conn):
    _job(conn, "ashby:Ramp:1", "Ramp")
    db.upsert_startup_company(conn, {"name": "Ramp", "employees": "900",
                                     "industry": "Fintech"})
    db.refresh_startup_flags(conn)
    rows = db.list_startups(conn)
    assert rows[0]["name"] == "Ramp"
    assert rows[0]["job_count"] == 1 and rows[0]["open_count"] == 1
    assert db.list_startups(conn, q="fintech")        # matches on industry
    assert db.list_startups(conn, q="nomatch") == []


# --------------------------------------------------------- two-track ingest ---
def test_ingest_both_tracks_and_flags(tmp_path, conn):
    root = tmp_path
    (root / "reports" / "startups").mkdir(parents=True)
    (root / "data" / "corpus").mkdir(parents=True)
    (root / "data" / "corpus-startups").mkdir(parents=True)

    (root / "reports" / "latest.json").write_text(json.dumps({
        "generated": "2026-06-12T15:00:00+00:00", "company_fit": {},
        "jobs": [{"key": "greenhouse:Google:1", "company": "Google",
                  "title": "SWE", "location": "NYC", "url": "https://g/1",
                  "posted": "2026-06-10", "fit": 80.0}],
        "near_miss": []}))
    (root / "reports" / "startups" / "latest.json").write_text(json.dumps({
        "generated": "2026-06-12T15:00:00+00:00", "company_fit": {},
        "jobs": [{"key": "ashby:Ramp:1", "company": "Ramp",
                  "title": "Backend Engineer", "location": "NYC",
                  "url": "https://r/1", "posted": "2026-06-11", "fit": 90.0}],
        "near_miss": []}))
    (root / "data" / "startup_meta.json").write_text(json.dumps({
        "generated": "2026-06-12T15:00:00+00:00",
        "companies": {"ramp": {"name": "Ramp", "employees": "900",
                               "stage": "Series D", "source": "ycombinator"}}}))

    counts = ingest_latest(root, conn)
    assert counts["inserted"] == 2                      # both tracks ingested
    assert counts["startups_loaded"] == 1
    flags = {r["company"]: r["is_startup"] for r in conn.execute(
        "SELECT company, is_startup FROM jobs")}
    assert flags == {"Google": 0, "Ramp": 1}           # Ramp flagged as startup
    assert db.startup_company_for(conn, "Ramp")["stage"] == "Series D"


# ---------------------------------------------------------------- routes ---
def test_startup_routes(tmp_path):
    from fastapi.testclient import TestClient

    from webapp.app import create_app

    root = tmp_path
    (root / "data").mkdir()
    (root / "config").mkdir()
    (root / "data" / "resume.txt").write_text("Engineer, NYC\n\nEXPERIENCE\nBuilt APIs.")
    (root / "config" / "settings.yaml").write_text("startups:\n  location: New York, NY\n")
    (root / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\nmanual_check: []\n")

    app = create_app(root, db_path=root / "data" / "test.db")
    client = TestClient(app)
    conn = app.state.conn
    _job(conn, "ashby:Ramp:1", "Ramp")
    db.upsert_startup_company(conn, {"name": "Ramp", "employees": "900",
                                     "stage": "Series D",
                                     "investors": ["Y Combinator"]})
    db.refresh_startup_flags(conn)

    # nav + dashboard split + toggle
    home = client.get("/")
    assert home.status_code == 200
    assert "Startups" in home.text
    assert "startup_scope=only" in home.text            # toggle present
    assert "🚀" in home.text

    # toggle filters the job table (the company dropdown still lists everything,
    # so assert on the row link, not a bare name match)
    job_id = conn.execute("SELECT id FROM jobs WHERE company='Ramp'").fetchone()["id"]
    only = client.get("/?startup_scope=only")
    assert f"/jobs/{job_id}" in only.text
    hide = client.get("/?startup_scope=hide")
    assert f"/jobs/{job_id}" not in hide.text          # startup row hidden

    # startup directory + detail
    directory = client.get("/startups")
    assert directory.status_code == 200 and "Ramp" in directory.text
    detail = client.get("/startups/ramp")
    assert detail.status_code == 200
    assert "Series D" in detail.text and "Edit facts" in detail.text

    # editing sets user_edited and persists
    r = client.post("/startups/ramp/edit",
                    data={"employees": "1234", "notes": "great team"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert db.startup_company_for(conn, "Ramp")["employees"] == "1234"

    # the job detail page shows the startup panel
    job_id = conn.execute("SELECT id FROM jobs WHERE company='Ramp'").fetchone()["id"]
    jd = client.get(f"/jobs/{job_id}")
    assert "Startup facts" in jd.text and "1234" in jd.text

    # fit map accepts the startups track without error
    assert client.get("/clusters?track=startups").status_code == 200
