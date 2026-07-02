"""Stage 1: companies tracked in the DB.

Covers the config-side registry reader (`registry_entries`), the DB registry
helpers (`upsert_company` / search-state / reconcile / listing), and the
ingest-side sync (`_ingest_registry` + `ingest_latest`) that mirrors each
track's live YAML registry into the `companies` table with per-run search-state.
"""

import gzip
import json

import pytest
import yaml

from jobsearch.config import load_settings, registry_entries
from jobsearch.tracks import build_track
from webapp import db
from webapp.ingest import _ingest_registry, ingest_latest


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def _write_companies_yaml(root, entries, manual=None, name="companies.yaml"):
    (root / "config").mkdir(parents=True, exist_ok=True)
    payload = {"companies": entries}
    if manual is not None:
        payload["manual_check"] = manual
    (root / "config" / name).write_text(yaml.safe_dump(payload))


def _write_discovered_yaml(root, entries, path="data/companies.discovered.yaml"):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump({"companies": entries}))


# --------------------------------------------------------- registry_entries ---
def test_registry_entries_curated_wins_and_excludes(tmp_path):
    _write_companies_yaml(tmp_path, [
        {"name": "Apple", "ats": "apple", "tags": ["faang"],
         "careers_url": "https://apple/jobs"},
        # curated AND on the exclude list: exclude must NOT drop it (load_registry
        # parity — exclude gates only the generated registry, curated wins).
        {"name": "Capital One", "ats": "greenhouse", "board": "capitalone"},
    ])
    _write_discovered_yaml(tmp_path, [
        # same company as curated → curated wins, discovered copy dropped
        {"name": "Apple", "ats": "greenhouse", "board": "apple-wrong",
         "tags": ["discovered"], "discovered_via": "hn_hiring (probe)"},
        # genuinely new discovered company
        {"name": "Ramp", "ats": "ashby", "org": "ramp", "tags": ["discovered"],
         "discovered_via": "hn_hiring (url)"},
        # discovered AND excluded → this copy IS dropped
        {"name": "Capital One", "ats": "greenhouse", "board": "capitalone-disc"},
    ])
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    settings["discovery"] = {"exclude_companies": ["Capital One"]}
    entries = registry_entries(tmp_path, settings, build_track(tmp_path, settings, "main"))

    by_name = {e["name"]: e for e in entries}
    # exclude gates the generated registry but NOT the curated seed.
    assert set(by_name) == {"Apple", "Ramp", "Capital One"}
    assert by_name["Capital One"]["source"] == "curated"     # curated, not excluded
    assert by_name["Capital One"]["params"] == {"board": "capitalone"}
    assert by_name["Apple"]["source"] == "curated"           # curated wins
    assert by_name["Apple"]["ats"] == "apple"                # not the discovered dupe
    assert by_name["Apple"]["params"] == {}                  # apple carries no board
    assert by_name["Ramp"]["source"] == "discovered"
    assert by_name["Ramp"]["params"] == {"org": "ramp"}      # non-reserved keys → params
    assert by_name["Ramp"]["discovered_via"] == "hn_hiring (url)"


def test_registry_entries_excludes_only_discovered(tmp_path):
    """A discovered-only excluded company is dropped; the same name curated is
    kept — the precedence that keeps the mirror matching what run() fetches."""
    _write_companies_yaml(tmp_path, [{"name": "Foo", "ats": "greenhouse", "board": "foo"}])
    _write_discovered_yaml(tmp_path, [{"name": "Bar", "ats": "ashby", "org": "bar"}])
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    settings["discovery"] = {"exclude_companies": ["Foo", "Bar"]}
    names = {e["name"] for e in registry_entries(tmp_path, settings)}
    assert names == {"Foo"}          # curated Foo kept, discovered Bar excluded


def test_registry_entries_scalar_tag_coerced(tmp_path):
    _write_companies_yaml(tmp_path, [{"name": "Foo", "ats": "greenhouse",
                                      "tags": "discovered"}])
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    entries = registry_entries(tmp_path, settings)
    assert entries[0]["tags"] == ["discovered"]   # scalar coerced, not dropped


def test_registry_entries_manual_check_blocks_discovered(tmp_path):
    _write_companies_yaml(tmp_path, [{"name": "Apple", "ats": "apple"}],
                          manual=[{"name": "Stripe", "careers_url": "https://stripe"}])
    _write_discovered_yaml(tmp_path, [{"name": "Stripe", "ats": "greenhouse",
                                       "board": "stripe"}])
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    entries = registry_entries(tmp_path, settings)
    assert {e["name"] for e in entries} == {"Apple"}  # Stripe blocked by manual_check


def test_registry_entries_missing_files_is_empty(tmp_path):
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    assert registry_entries(tmp_path, settings) == []  # no crash, no companies


# ------------------------------------------------------------ upsert_company ---
def test_upsert_company_insert_update_and_json_roundtrip(conn):
    assert db.upsert_company(conn, {
        "name": "Ramp", "ats": "ashby", "careers_url": "https://ramp",
        "tags": ["discovered"], "params": {"org": "ramp"},
        "source": "discovered", "discovered_via": "hn (url)"}) == "inserted"
    row = db.get_company(conn, db.LOCAL_USER_ID, "main", "ramp")
    assert row["ats"] == "ashby"
    assert row["tags"] == ["discovered"]          # JSON decoded
    assert row["params"] == {"org": "ramp"}       # JSON decoded
    assert row["enabled"] is True and row["source"] == "discovered"
    first_seen = row["first_seen_at"]

    # Re-sync patches config but preserves first_seen_at.
    assert db.upsert_company(conn, {"name": "Ramp", "ats": "greenhouse",
                                    "careers_url": "https://ramp2"}) == "updated"
    row2 = db.get_company(conn, db.LOCAL_USER_ID, "main", "ramp")
    assert row2["ats"] == "greenhouse"
    assert row2["first_seen_at"] == first_seen


def test_upsert_company_user_edit_protected(conn):
    db.upsert_company(conn, {"name": "Ramp", "ats": "ashby"}, from_user=True)
    # a background sync must not clobber a user-edited row
    assert db.upsert_company(conn, {"name": "Ramp", "ats": "greenhouse"}) == "skipped"
    assert db.get_company(conn, db.LOCAL_USER_ID, "main", "ramp")["ats"] == "ashby"


def test_upsert_company_non_json_param_does_not_crash(conn):
    import datetime
    # An unquoted YAML date lands in params as a datetime.date; it must
    # serialize (default=str), not raise TypeError and abort the ingest.
    assert db.upsert_company(conn, {
        "name": "Foo", "ats": "greenhouse",
        "params": {"since": datetime.date(2024, 1, 15)}}) == "inserted"
    assert db.get_company(conn, db.LOCAL_USER_ID, "main", "foo")["params"] == {"since": "2024-01-15"}


def test_upsert_company_track_scoped(conn):
    db.upsert_company(conn, {"name": "Ramp", "ats": "ashby"}, track="main")
    db.upsert_company(conn, {"name": "Ramp", "ats": "greenhouse"}, track="startups")
    assert db.get_company(conn, db.LOCAL_USER_ID, "main", "ramp")["ats"] == "ashby"
    assert db.get_company(conn, db.LOCAL_USER_ID, "startups", "ramp")["ats"] == "greenhouse"
    assert db.upsert_company(conn, {"name": ""}) == "skipped"  # unkeyable → skipped


# ------------------------------------------- search-state + reconcile ---
def test_touch_and_disable_absent(conn):
    for name in ("Apple", "Ramp"):
        db.upsert_company(conn, {"name": name, "ats": "x"})
    db.touch_company_search(conn, db.LOCAL_USER_ID, "main", "ramp", 7, now="2026-07-01T00:00:00+00:00")
    ramp = db.get_company(conn, db.LOCAL_USER_ID, "main", "ramp")
    assert ramp["last_found_jobs"] == 7 and ramp["last_searched_at"].startswith("2026-07-01")

    # Ramp drops out of the registry → disabled; Apple kept.
    disabled = db.disable_absent_companies(conn, db.LOCAL_USER_ID, "main", {"apple"})
    assert disabled == 1
    assert db.get_company(conn, db.LOCAL_USER_ID, "main", "ramp")["enabled"] is False
    assert db.get_company(conn, db.LOCAL_USER_ID, "main", "apple")["enabled"] is True
    assert [c["name"] for c in db.list_companies(conn, enabled_only=True)] == ["Apple"]


def test_disable_absent_skips_user_edited(conn):
    db.upsert_company(conn, {"name": "Ramp", "ats": "ashby"}, from_user=True)
    assert db.disable_absent_companies(conn, db.LOCAL_USER_ID, "main", set()) == 0
    assert db.get_company(conn, db.LOCAL_USER_ID, "main", "ramp")["enabled"] is True


# ------------------------------------------------------------ _ingest_registry ---
def test_ingest_registry_syncs_and_reconciles(tmp_path, conn):
    _write_companies_yaml(tmp_path, [{"name": "Apple", "ats": "apple"}])
    _write_discovered_yaml(tmp_path, [{"name": "Ramp", "ats": "ashby", "org": "ramp",
                                       "tags": ["discovered"],
                                       "discovered_via": "hn (url)"}])
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    track = build_track(tmp_path, settings, "main")

    summary = _ingest_registry(tmp_path, conn, settings, track,
                               {"ramp": 3}, db.utcnow())
    assert summary == {"total": 2, "new": 2, "disabled": 0}
    tracked = {c["name"]: c for c in db.list_companies(conn, track="main")}
    assert set(tracked) == {"Apple", "Ramp"}
    assert tracked["Ramp"]["source"] == "discovered"
    assert tracked["Ramp"]["last_found_jobs"] == 3
    assert tracked["Apple"]["source"] == "curated"
    assert len(conn.execute("SELECT * FROM company_search_runs").fetchall()) == 1

    # Ramp falls out of the discovered registry next run → reconciled to disabled.
    _write_discovered_yaml(tmp_path, [])
    summary2 = _ingest_registry(tmp_path, conn, settings, track, {}, db.utcnow())
    assert summary2 == {"total": 1, "new": 0, "disabled": 1}
    assert db.get_company(conn, db.LOCAL_USER_ID, "main", "ramp")["enabled"] is False
    assert [c["name"] for c in db.list_companies(conn, track="main", enabled_only=True)] == ["Apple"]


def test_ingest_registry_survives_malformed_yaml(tmp_path, conn):
    """A hand-edit syntax error in a registry YAML must degrade to a no-op, not
    abort the ingest (graceful degradation — the pipeline fetch already ran)."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "companies.yaml").write_text("a: b: c\n")  # invalid YAML
    settings = load_settings(tmp_path / "config" / "settings.yaml")
    track = build_track(tmp_path, settings, "main")
    summary = _ingest_registry(tmp_path, conn, settings, track, {}, db.utcnow())
    assert summary == {"total": 0, "new": 0, "disabled": 0}   # no raise


def test_ingest_latest_populates_companies(tmp_path, conn):
    """End-to-end wiring: a run's report + curated registry → companies rows
    stamped with this run's per-company job counts."""
    root = tmp_path
    _write_companies_yaml(root, [{"name": "Acme", "ats": "greenhouse", "board": "acme"}])
    (root / "reports").mkdir(exist_ok=True)
    (root / "data" / "corpus").mkdir(parents=True, exist_ok=True)
    (root / "reports" / "latest.json").write_text(json.dumps({
        "generated": "2026-06-12T15:00:00+00:00", "company_fit": {},
        "jobs": [{"key": "greenhouse:Acme:1", "company": "Acme",
                  "title": "Senior Software Engineer", "location": "NYC",
                  "url": "https://acme.com/1", "posted": "2026-06-10", "fit": 80.0,
                  "rank_score": 60.0, "new": True, "cluster": 1}],
        "near_miss": [],
    }))
    with gzip.open(root / "data" / "corpus" / "2026-06-12.jsonl.gz", "wt") as fh:
        fh.write(json.dumps({"key": "greenhouse:Acme:1", "description": "x"}) + "\n")

    counts = ingest_latest(root, conn)
    assert counts["companies_synced"] == 1 and counts["companies_new"] == 1
    acme = db.get_company(conn, db.LOCAL_USER_ID, "main", "acme")
    assert acme["ats"] == "greenhouse" and acme["params"] == {"board": "acme"}
    assert acme["source"] == "curated" and acme["enabled"] is True
    assert acme["last_found_jobs"] == 1          # one posting seen this run
    assert acme["last_searched_at"]              # stamped
