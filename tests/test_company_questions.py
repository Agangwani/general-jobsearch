"""Tests for the company-specific LeetCode question feature: bundled seed
(idempotent + progress-preserving), DB queries, the tolerant CSV refresh
parser, and route smoke tests. All offline — the refresh network call is
never made here."""

import pytest

from jobsearch.company_questions import (
    bundled_records,
    canonical_key,
)
from jobsearch.company_questions.refresh import RefreshError, parse_csv
from webapp import company_questions, db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


# ------------------------------------------------------------- canonical keys
def test_canonical_key_folds_aliases_and_suffixes():
    assert canonical_key("Facebook") == "meta"
    assert canonical_key("Meta Platforms, Inc.") == "meta"
    assert canonical_key("Amazon Web Services") == "amazon"
    assert canonical_key("The Goldman Sachs Group") == "goldman sachs"
    assert canonical_key("Datadog, Inc.") == "datadog"  # plain normalize


def test_bundled_records_are_well_formed():
    recs = bundled_records()
    assert recs, "bundled dataset should not be empty"
    keys = {r["company_key"] for r in recs}
    assert "amazon" in keys and "meta" in keys
    for r in recs:
        assert r["leetcode_slug"] and r["title"]
        assert r["difficulty"] in ("easy", "medium", "hard")
        assert r["url"].startswith("https://leetcode.com/problems/")
        assert 0 <= r["frequency"] <= 100
    # Facebook content is stored under the canonical "meta" key.
    assert all(canonical_key(r["company"]) == r["company_key"] for r in recs)


# --------------------------------------------------------------- bundled seed
def test_seed_is_idempotent_and_preserves_progress(conn):
    first = company_questions.seed_bundled(conn)
    assert first["seeded"] and first["total"] > 0
    total = conn.execute("SELECT COUNT(*) AS n FROM company_problems").fetchone()["n"]

    # Mark one problem solved, then re-seed: count stable, progress intact.
    pid = conn.execute("SELECT id FROM company_problems LIMIT 1").fetchone()["id"]
    db.set_company_problem_state(conn, pid, "solved")
    second = company_questions.seed_bundled(conn)
    assert second["seeded"] is False  # content hash short-circuits
    assert conn.execute("SELECT COUNT(*) AS n FROM company_problems").fetchone()["n"] == total
    state = conn.execute(
        "SELECT state FROM company_problem_progress WHERE company_problem_id = ?",
        (pid,)).fetchone()
    assert state["state"] == "solved"


def test_overview_and_query(conn):
    company_questions.seed_bundled(conn)
    overview = db.companies_overview(conn)
    assert overview and overview[0]["problem_count"] >= overview[-1]["problem_count"]
    amazon = next(c for c in overview if c["company_key"] == "amazon")
    assert amazon["company"] == "Amazon"
    assert amazon["easy"] + amazon["medium"] + amazon["hard"] == amazon["problem_count"]

    probs = db.company_problems_for(conn, "amazon")
    assert probs and probs[0]["frequency"] >= probs[-1]["frequency"]  # most-asked first
    mediums = db.company_problems_for(conn, "amazon", difficulty="medium")
    assert mediums and all(p["difficulty"] == "medium" for p in mediums)


def test_set_state_validation(conn):
    company_questions.seed_bundled(conn)
    row = conn.execute(
        "SELECT id, company_key FROM company_problems LIMIT 1").fetchone()
    db.set_company_problem_state(conn, row["id"], "attempted")
    got = db.company_problems_for(conn, row["company_key"])
    assert any(p["id"] == row["id"] and p["state"] == "attempted" for p in got)
    with pytest.raises(ValueError):
        db.set_company_problem_state(conn, row["id"], "bogus")


def test_upsert_overwrites_metadata_keeps_progress(conn):
    company_questions.seed_bundled(conn)
    row = conn.execute(
        "SELECT id, leetcode_slug FROM company_problems WHERE company_key = 'amazon' LIMIT 1"
    ).fetchone()
    db.set_company_problem_state(conn, row["id"], "solved")
    # A refresh-style upsert with new frequency/difficulty must keep the id (so
    # progress survives) and overwrite the measured fields.
    res = db.upsert_company_problem(conn, {
        "company": "Amazon", "company_key": "amazon",
        "leetcode_number": 1, "leetcode_slug": row["leetcode_slug"],
        "title": "Two Sum", "difficulty": "hard", "frequency": 88.0,
        "timeframe": "alltime", "topics": "", "url": "x", "source": "github_csv",
    })
    conn.commit()
    assert res == "updated"
    after = conn.execute("SELECT * FROM company_problems WHERE id = ?",
                         (row["id"],)).fetchone()
    assert after["frequency"] == 88.0 and after["source"] == "github_csv"
    prog = conn.execute(
        "SELECT state FROM company_problem_progress WHERE company_problem_id = ?",
        (row["id"],)).fetchone()
    assert prog["state"] == "solved"


# --------------------------------------------------------------- CSV refresh
def test_parse_csv_krishnadey_layout():
    csv_text = (
        "Difficulty,Title,Frequency,Acceptance Rate,Link\n"
        "MEDIUM,Number of Islands,92.5,55.1,https://leetcode.com/problems/number-of-islands\n"
        "EASY,Two Sum,87.2,49.8,https://leetcode.com/problems/two-sum/\n"
    )
    recs = parse_csv(csv_text, "Amazon")
    assert len(recs) == 2
    assert recs[0]["leetcode_slug"] == "number-of-islands"
    assert recs[0]["difficulty"] == "medium" and recs[0]["frequency"] == 92.5
    assert all(r["company_key"] == "amazon" for r in recs)


def test_parse_csv_alternate_layout_and_fraction_freq():
    # Different column names + frequency as a 0..1 fraction + numeric id column.
    csv_text = (
        "ID,Name,URL,Difficulty,Freq\n"
        "146,LRU Cache,https://leetcode.com/problems/lru-cache/,Hard,0.81\n"
    )
    recs = parse_csv(csv_text, "Meta")
    assert recs[0]["title"] == "LRU Cache" and recs[0]["leetcode_number"] == 146
    assert recs[0]["frequency"] == 81.0  # 0.81 → 81.0
    assert recs[0]["company_key"] == "meta"


def test_parse_csv_rejects_bad_layout():
    with pytest.raises(RefreshError):
        parse_csv("Foo,Bar\n1,2\n", "Amazon")


def test_parse_csv_skips_rows_without_slug():
    csv_text = ("Title,Link\nGood,https://leetcode.com/problems/two-sum/\n"
                "Bad,https://example.com/not-a-problem\n")
    recs = parse_csv(csv_text, "Amazon")
    assert [r["leetcode_slug"] for r in recs] == ["two-sum"]


def test_parse_csv_problem_link_header_is_link_not_title():
    # "Problem Link" contains 'problem' (a title keyword) but is the URL column;
    # link detection must win so the CSV parses instead of erroring.
    csv_text = ("Difficulty,Title,Problem Link\n"
                "Easy,Two Sum,https://leetcode.com/problems/two-sum/\n")
    recs = parse_csv(csv_text, "Amazon")
    assert recs[0]["title"] == "Two Sum"
    assert recs[0]["leetcode_slug"] == "two-sum"


def test_parse_frequency_does_not_inflate_low_percentages():
    # A '1' on a 0..100 dataset must stay 1.0, not become 100.0 (which would
    # wrongly sort the least-asked problem to the top).
    csv_text = ("Title,Frequency,Link\n"
                "Top,90,https://leetcode.com/problems/two-sum/\n"
                "Rare,1,https://leetcode.com/problems/lru-cache/\n")
    recs = {r["leetcode_slug"]: r["frequency"] for r in parse_csv(csv_text, "Amazon")}
    assert recs["two-sum"] == 90.0 and recs["lru-cache"] == 1.0


def test_set_company_problem_state_route_tolerates_stale_id(tmp_path):
    from fastapi.testclient import TestClient

    from webapp.app import create_app

    root = tmp_path
    (root / "data").mkdir()
    (root / "config").mkdir()
    (root / "data" / "resume.txt").write_text("U\nSenior Software Engineer, NYC\n\nX\nY")
    (root / "config" / "settings.yaml").write_text(
        "search:\n  query: x\n  locations: [nyc]\nranking:\n  half_life_days: 7\n")
    (root / "config" / "companies.yaml").write_text("companies: []\nmanual_check: []\n")
    app = create_app(root, db_path=root / "data" / "test.db")
    client = TestClient(app)
    # A non-existent problem id must redirect (303), not 500 on the FK failure.
    resp = client.post("/company-problems/999999/state",
                       data={"state": "solved"}, follow_redirects=False)
    assert resp.status_code == 303


# --------------------------------------------------------------- route smoke
def test_company_routes(tmp_path):
    from fastapi.testclient import TestClient

    from webapp.app import create_app

    root = tmp_path
    (root / "data").mkdir()
    (root / "config").mkdir()
    (root / "data" / "resume.txt").write_text(
        "Test User\nSenior Software Engineer, New York, NY\n\nEXPERIENCE\nDid things.")
    (root / "config" / "settings.yaml").write_text(
        "search:\n  query: x\n  locations: [new york]\nranking:\n  half_life_days: 7\n")
    (root / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\nmanual_check: []\n")

    app = create_app(root, db_path=root / "data" / "test.db")
    client = TestClient(app)

    landing = client.get("/companies")
    assert landing.status_code == 200 and "Amazon" in landing.text

    detail = client.get("/companies/amazon")
    assert detail.status_code == 200 and "Two Sum" in detail.text
    assert "Refresh questions" in detail.text

    # difficulty filter narrows the list
    easy = client.get("/companies/amazon?difficulty=easy")
    assert easy.status_code == 200

    # mark a problem solved via the state endpoint
    pid = app.state.conn.execute(
        "SELECT id FROM company_problems WHERE company_key = 'amazon' LIMIT 1"
    ).fetchone()["id"]
    resp = client.post(f"/company-problems/{pid}/state",
                       data={"state": "solved", "next": "/companies/amazon"},
                       follow_redirects=False)
    assert resp.status_code == 303
    state = app.state.conn.execute(
        "SELECT state FROM company_problem_progress WHERE company_problem_id = ?",
        (pid,)).fetchone()
    assert state["state"] == "solved"

    # refresh-status JSON is well-formed for a company with no run yet
    status = client.get("/api/companies/amazon/refresh-status").json()
    assert status["problem_count"] > 0 and status["running"] is False

    # nav badge counts render on every page
    assert "Companies" in client.get("/").text

    # a job at Amazon surfaces its company questions on the detail page
    db.upsert_job(app.state.conn, {
        "key": "greenhouse:Amazon:1", "source": "greenhouse", "company": "Amazon",
        "title": "Senior Software Engineer", "location": "NYC",
        "url": "https://amazon.jobs/1", "description": "Build.", "posted_at": "2026-06-10",
        "fit_score": 80.0, "rank_score": 60.0, "cluster": 1})
    job_id = app.state.conn.execute(
        "SELECT id FROM jobs WHERE company = 'Amazon'").fetchone()["id"]
    jd = client.get(f"/jobs/{job_id}")
    assert jd.status_code == 200 and "LeetCode questions Amazon asks" in jd.text
