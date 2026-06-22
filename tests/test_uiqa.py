"""Tests for the uiqa harness.

The pure-logic tests (persona inference, finding dedup, action classification,
report consolidation) run everywhere with no browser. The end-to-end test boots
the real app + Chromium and is skipped automatically when a browser can't be
launched (e.g. Playwright's browser isn't installed), mirroring how the rest of
the suite degrades without Chromium.
"""

from __future__ import annotations

import json
import os

import pytest

from uiqa import actions, explore, findings, persona
from uiqa.report import RunDir


# ----------------------------------------------------------------- persona
def test_persona_value_inference():
    p = persona.Persona()
    assert "@" in p.value_for(input_type="email")
    assert p.value_for(name="phone") == p.profile["phone"]
    assert p.value_for(name="linkedin_url") == p.profile["linkedin"]
    assert p.value_for(input_type="number").isdigit()
    assert p.value_for(name="q", input_type="search") == p.search_terms[0]


def test_persona_loads_sample_resume(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sample_resume.txt").write_text("SAMPLE RESUME BODY")
    p = persona.Persona.load(tmp_path, "sample")
    assert "SAMPLE RESUME BODY" in p.resume_text


# ----------------------------------------------------------------- findings
def test_signature_collapses_volatile_ids():
    a = findings.make_finding(area="jobs", route="/jobs/12", kind="page_error",
                              severity="high", title="boom", detail="TypeError at row 12")
    b = findings.make_finding(area="jobs", route="/jobs/87", kind="page_error",
                              severity="high", title="boom", detail="TypeError at row 87")
    assert a["id"] == b["id"]  # same bug on different rows → one id


def test_merge_dedups_and_keeps_highest_severity():
    lo = findings.make_finding(area="dashboard", route="/", kind="console_error",
                               severity="low", title="x", detail="same thing",
                               discovered_by="crawler")
    hi = findings.make_finding(area="dashboard", route="/", kind="console_error",
                               severity="high", title="x", detail="same thing",
                               discovered_by="ui-explorer", evidence=["shot.png"])
    merged = findings.merge([lo, hi])
    assert len(merged) == 1
    assert merged[0]["severity"] == "high"
    assert "ui-explorer" in merged[0]["discovered_by"] and "crawler" in merged[0]["discovered_by"]
    assert "shot.png" in merged[0]["evidence"]


def test_route_template():
    assert findings.route_template("/jobs/42?x=1") == "/jobs/{id}"
    assert findings.route_template("/clusters/job/7") == "/clusters/job/{id}"


# ------------------------------------------------------------------ actions
def test_classify_marks_side_effecting_and_external():
    apply_btn = {"role": "widget", "id": "", "selector": "button[data-apply-btn]",
                 "href": "", "action": "", "label": "Auto-fill"}
    actions._classify(apply_btn, "http://127.0.0.1:8000")
    assert apply_btn["side_effecting"] is True

    ext = {"role": "link", "href": "https://example.com/x", "target": "_blank",
           "id": "", "selector": "a", "action": "", "label": "Open posting"}
    actions._classify(ext, "http://127.0.0.1:8000")
    assert ext["external"] is True

    internal = {"role": "link", "href": "/jobs/1", "id": "", "selector": "a",
                "action": "", "label": "A job", "target": ""}
    actions._classify(internal, "http://127.0.0.1:8000")
    assert internal["external"] is False and internal["navigates"] is True


def test_area_for():
    assert explore.area_for("/jobs/1") == "jobs"
    assert explore.area_for("/clusters/job/1") == "clusters"
    assert explore.area_for("/?stack=applied") == "dashboard"
    assert explore.area_for("/prep/module/x") == "prep"


# ------------------------------------------------------------------- report
def test_consolidate_merges_jsonl_and_incoming(tmp_path):
    rd = RunDir(tmp_path, run_id="testrun")
    findings.append_jsonl(rd.findings_jsonl, findings.make_finding(
        area="dashboard", route="/", kind="server_error", severity="high",
        title="A", detail="crash one"))
    # An explorer sub-agent drops a finding as a file rather than appending.
    (rd.base / "incoming" / "f1.json").write_text(json.dumps(findings.make_finding(
        area="resume", route="/resume", kind="page_error", severity="high",
        title="B", detail="crash two", discovered_by="ui-explorer")))
    merged = rd.consolidate()
    assert len(merged) == 2
    assert json.loads(rd.findings_json.read_text())
    rd.write_summary(action_index={"/": [{"role": "link"}]}, findings=merged)
    assert "UI-QA run testrun" in (rd.base / "summary.md").read_text()


# ----------------------------------------------------------- browser e2e
def _browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    for cand in ("/opt/pw-browsers", os.path.expanduser("~/.cache/ms-playwright")):
        if os.path.isdir(cand):
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", cand)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _browser_available(),
                    reason="Playwright Chromium not launchable in this environment")
def test_end_to_end_detects_the_min_fit_500():
    """Boot the real app + a real browser, drive a scenario, and confirm the
    harness catches the /?min_fit=abc server 500 (the bug Stage 3 fixes)."""
    from pathlib import Path

    from uiqa.appserver import AppServer
    from uiqa.browser import BrowserSession
    from uiqa.persona import Persona
    from uiqa.scenario import ScenarioRunner

    repo_root = Path(__file__).resolve().parent.parent
    p = Persona.load(repo_root)
    with AppServer(repo_root, p) as server, \
            BrowserSession(headless=True, base_url=server.base_url) as browser:
        runner = ScenarioRunner(server, browser, p, server.root)
        ok = runner.run({"name": "home loads", "steps": [
            {"action": "goto", "path": "/"}, {"action": "expect_no_error"}]})
        bad = runner.run({"name": "min_fit junk", "steps": [
            {"action": "goto", "path": "/?min_fit=abc"},
            {"action": "expect_status", "code": 200}]})
    assert ok["ok"] is True, "the home page should load cleanly"
    assert bad["problem_count"] > 0, "min_fit=abc should surface a 500"
    kinds = {pr["kind"] for s in bad["steps"] for pr in s["problems"]}
    assert {"http_error_5xx", "server_error"} & kinds
