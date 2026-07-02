"""Stage 2b: per-user data isolation at the db layer.

Profile, prep progress, and company progress must each be scoped by user_id so
two accounts never see each other's data. These run against SQLite (the default
backend) and exercise the same functions the routes call."""

import pytest

from jobsearch.prep.seed import seed_into_db
from webapp import db, profile


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "scope.db")
    yield c
    c.close()


def test_profile_scoped_by_user(conn):
    profile.set_field(conn, "full_name", "Alice", user_id="u1")
    profile.set_field(conn, "full_name", "Bob", user_id="u2")
    a = {r["field"]: r["value"] for r in profile.all_fields(conn, "u1")}
    b = {r["field"]: r["value"] for r in profile.all_fields(conn, "u2")}
    assert a["full_name"] == "Alice"
    assert b["full_name"] == "Bob"


def test_prep_progress_scoped_by_user(conn):
    seed_into_db(conn)
    lid = conn.execute("SELECT id FROM prep_lessons LIMIT 1").fetchone()["id"]
    db.set_lesson_state(conn, lid, "completed", user_id="u1")

    # Counts are per-user.
    assert db.prep_overall_counts(conn, "u1")["lessons_done"] == 1
    assert db.prep_overall_counts(conn, "u2")["lessons_done"] == 0

    # Module detail reflects each user's own state for the same lesson.
    slug = conn.execute(
        "SELECT m.slug FROM prep_modules m JOIN prep_lessons l ON l.module_id = m.id "
        "WHERE l.id = ?", (lid,)).fetchone()["slug"]
    s1 = {l["id"]: l["state"] for l in db.prep_module_detail(conn, slug, "u1")["lessons"]}
    s2 = {l["id"]: l["state"] for l in db.prep_module_detail(conn, slug, "u2")["lessons"]}
    assert s1[lid] == "completed"
    assert s2[lid] == "not_started"


def test_company_progress_scoped_by_user(conn):
    db.seed_company_problems(conn, [
        {"company": "Acme", "company_key": "acme", "leetcode_slug": "two-sum",
         "title": "Two Sum", "difficulty": "easy", "frequency": 90}])
    pid = conn.execute(
        "SELECT id FROM company_problems WHERE leetcode_slug = 'two-sum'").fetchone()["id"]
    db.set_company_problem_state(conn, pid, "solved", user_id="u1")

    assert db.company_overall_counts(conn, "u1")["problems_done"] == 1
    assert db.company_overall_counts(conn, "u2")["problems_done"] == 0
    assert db.company_problems_for(conn, "acme", user_id="u1")[0]["state"] == "solved"
    assert db.company_problems_for(conn, "acme", user_id="u2")[0]["state"] == "not_started"
