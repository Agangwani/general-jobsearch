"""Stage 1, deterministic floor: crawl every route, index every action, and run
a curated set of combination journeys.

Two phases:

  A. BFS GET-crawl from the nav + seeded routes. Visits each route template a
     couple of times, indexes all of its actions (the coverage guarantee), and
     turns any load-time browser/server error or non-OK status into a finding.
     Following in-origin links is how sub-pages (job detail, prep lessons,
     cluster drill-downs, company pages) get discovered and opened.

  B. A curated battery of *combination* scenarios — filter×sort permutations,
     edge inputs, a valid and an invalid resume upload, profile save, an
     in-place status change — run through the scenario runner so multi-step
     interactions (not just page loads) are exercised too.

Explorer sub-agents pick up where this leaves off, using the action index to try
the open-ended, intuitive combinations a fixed battery can't enumerate. Anything
with real side effects (launching the apply browser, running the pipeline,
connecting Gmail) is indexed but never auto-fired here.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import findings as F
from .actions import index_actions
from .appserver import AppServer
from .browser import BrowserSession
from .persona import Persona
from .report import RunDir
from .scenario import ScenarioRunner

# Map a route to a human "area" so findings group the way the agents are split.
_AREAS = [
    ("/jobs", "jobs"), ("/clusters", "clusters"), ("/prep", "prep"),
    ("/companies", "companies"), ("/resume", "resume"), ("/profile", "profile"),
    ("/settings", "settings"), ("/emails", "emails"), ("/api", "api"),
]


def area_for(route: str) -> str:
    path = urlsplit(route).path
    for prefix, area in _AREAS:
        if path.startswith(prefix):
            return area
    return "dashboard"


def seed_routes(job_ids: dict[str, int]) -> list[str]:
    routes = ["/", "/?stack=to_apply", "/?stack=in_progress", "/?stack=applied",
              "/prep", "/clusters", "/companies", "/resume", "/profile",
              "/settings", "/emails"]
    for jid in list(job_ids.values())[:3]:
        routes += [f"/jobs/{jid}", f"/jobs/{jid}/referrals", f"/clusters/job/{jid}"]
    return routes


# --------------------------------------------------------------------- Phase A
def crawl(server: AppServer, browser: BrowserSession, rundir: RunDir,
          *, max_pages: int = 60, per_template: int = 2) -> dict[str, list]:
    """BFS the site; return {route: [action descriptors]} and append findings."""
    action_index: dict[str, list] = {}
    visited: set[str] = set()
    template_counts: dict[str, int] = {}
    queue: deque[tuple[str, bool]] = deque((r, True) for r in seed_routes(server.job_ids))

    while queue and len(visited) < max_pages:
        path, is_seed = queue.popleft()
        if path in visited:
            continue
        tmpl = F.route_template(path)
        if not is_seed and template_counts.get(tmpl, 0) >= per_template:
            continue
        visited.add(path)
        template_counts[tmpl] = template_counts.get(tmpl, 0) + 1

        try:
            status = browser.goto(path)
        except Exception as exc:  # a slow/flaky nav must not abort the whole crawl
            # Drain and reset cursors so the failed load can't bleed into the next
            # route, record it as a finding (Stage 2 replay rules a genuine hang
            # `confirmed` and a transient `flaky`), and keep crawling.
            browser.drain()
            server.server_errors_since()
            msg = str(exc).splitlines()[0]
            rundir.log_step({"phase": "crawl", "route": path, "status": None,
                             "title": "", "n_actions": 0,
                             "events": [{"kind": "page_error", "severity": "medium",
                                         "text": f"navigation failed: {msg}",
                                         "url": path, "page_url": path,
                                         "external": False}],
                             "server_errors": []})
            rundir.add_finding(F.make_finding(
                area=area_for(path), route=path, kind="page_error", severity="medium",
                title=f"{path} failed to load (navigation error)",
                detail=f"Navigating to {path} raised {type(exc).__name__}: {msg}",
                repro={"name": f"load {path}",
                       "steps": [{"action": "goto", "path": path}]}))
            continue
        events = [e.to_dict() for e in browser.drain()]
        server_errs, _ = server.server_errors_since()
        actions = index_actions(browser.page)
        action_index[path] = actions
        rundir.log_step({"phase": "crawl", "route": path, "status": status,
                         "title": browser.title(), "n_actions": len(actions),
                         "events": events, "server_errors": server_errs})

        _findings_from_load(rundir, path, status, events, server_errs)

        # Enqueue in-origin, non-side-effecting link targets to discover sub-pages.
        for a in actions:
            if a.get("role") == "link" and a.get("navigates") and not a.get("external") \
                    and not a.get("side_effecting"):
                href = a["href"]
                if href.startswith("/") and href not in visited:
                    queue.append((href, False))

    return action_index


def _findings_from_load(rundir: RunDir, route: str, status: int,
                        events: list[dict], server_errs: list[str]) -> None:
    area = area_for(route)
    repro = {"name": f"load {route}", "steps": [{"action": "goto", "path": route}]}
    if status and status >= 400:
        rundir.add_finding(F.make_finding(
            area=area, route=route,
            kind="http_error_5xx" if status >= 500 else "http_error_4xx",
            severity="high" if status >= 500 else "medium",
            title=f"{route} returned HTTP {status}",
            detail=f"Navigating to {route} returned status {status}.", repro=repro))
    for e in events:
        if e["severity"] in ("high", "medium"):
            rundir.add_finding(F.make_finding(
                area=area, route=route, kind=e["kind"], severity=e["severity"],
                title=f"{e['kind']} on {route}", detail=e["text"], repro=repro))
    for msg in server_errs:
        rundir.add_finding(F.make_finding(
            area=area, route=route, kind="server_error", severity="high",
            title=f"server error on {route}", detail=msg, repro=repro))


# --------------------------------------------------------------------- Phase B
def interaction_scenarios(job_ids: dict[str, int]) -> list[dict[str, Any]]:
    """Curated multi-step journeys exercising action *combinations*."""
    jid = next(iter(job_ids.values()), None)
    scns: list[dict[str, Any]] = [
        {"name": "dashboard filter+sort permutation", "steps": [
            {"action": "goto", "path": "/?stack=to_apply&sort_by=fit&sort_dir=asc"},
            {"action": "goto", "path": "/?sort_by=company&sort_dir=desc&min_fit=50"},
            {"action": "goto", "path": "/?q=engineer&near_miss=1&run_scope=all"},
            {"action": "expect_no_error"}]},
        {"name": "dashboard edge inputs", "steps": [
            {"action": "goto", "path": "/?min_fit=999&status_filter=interviewing"},
            {"action": "goto", "path": "/?min_fit=-5&sort_by=bogus&stack=nonsense"},
            {"action": "expect_no_error"}]},
        # A user typing letters into the "min fit" box (or fuzzing the URL) —
        # the kind of unexpected input human-like exploration surfaces.
        {"name": "non-numeric min_fit", "steps": [
            {"action": "goto", "path": "/?min_fit=abc"},
            {"action": "expect_status", "code": 200},
            {"action": "expect_no_error"}]},
        {"name": "search then clear", "steps": [
            {"action": "goto", "path": "/"},
            {"action": "fill", "selector": "input[name=q]", "value": "$persona"},
            {"action": "click", "selector": ".filters button"},
            {"action": "expect_no_error"}]},
        {"name": "valid resume upload", "steps": [
            {"action": "goto", "path": "/resume"},
            {"action": "upload", "selector": "input[type=file]", "file": "$resume"},
            {"action": "click", "text": "Upload"},
            {"action": "expect_no_error"}]},
        {"name": "invalid (tiny) resume upload is rejected gracefully", "steps": [
            {"action": "goto", "path": "/resume"},
            {"action": "upload", "selector": "input[type=file]", "file": "$tiny"},
            {"action": "click", "text": "Upload"},
            {"action": "expect_no_error"}]},
        {"name": "profile save round-trip", "steps": [
            {"action": "goto", "path": "/profile"},
            {"action": "fill", "selector": "input[name=full_name]", "value": "$persona"},
            {"action": "fill", "selector": "input[name=email]", "value": "$persona"},
            {"action": "click", "text": "Save"},
            {"action": "expect_no_error"}]},
        {"name": "prep drill-down track→module", "steps": [
            {"action": "goto", "path": "/prep"},
            {"action": "index"},
            {"action": "expect_no_error"}]},
        {"name": "theme toggle persists", "steps": [
            {"action": "goto", "path": "/"},
            {"action": "click", "selector": "#theme-toggle"},
            {"action": "goto", "path": "/prep"},
            {"action": "expect_no_error"}]},
    ]
    if jid is not None:
        scns.append({"name": "open job → why-this-fit → back", "steps": [
            {"action": "goto", "path": f"/jobs/{jid}"},
            {"action": "click", "text": "Why this fit"},
            {"action": "back"},
            {"action": "expect_no_error"}]})
        scns.append({"name": "change status in place on dashboard", "steps": [
            {"action": "goto", "path": "/"},
            {"action": "select", "selector": ".row-status", "value": "$first"},
            {"action": "expect_no_error"}]})
    return scns


def run_interactions(runner: ScenarioRunner, scenarios: list[dict[str, Any]],
                     rundir: RunDir) -> None:
    for scn in scenarios:
        result = runner.run(scn)
        rundir.log_step({"phase": "interaction", "scenario": scn["name"],
                         "ok": result["ok"], "problem_count": result["problem_count"]})
        if result["ok"]:
            continue
        scn_path = rundir.save_scenario(scn)
        for step in result["steps"]:
            for prob in step["problems"]:
                route = _route_of(step) or scn["name"]
                rundir.add_finding(F.make_finding(
                    area=area_for(route), route=route,
                    kind=_finding_kind(prob), severity=prob.get("severity", "medium"),
                    title=f"{scn['name']}: {prob.get('kind', 'problem')}",
                    detail=prob.get("text", ""), repro=scn,
                    evidence=[str(scn_path)] + ([step["screenshot"]]
                                                if step.get("screenshot") else [])))


def _route_of(step: dict[str, Any]) -> str:
    url = step.get("url", "")
    return urlsplit(url).path + (("?" + urlsplit(url).query) if urlsplit(url).query else "") if url else ""


def _finding_kind(prob: dict[str, Any]) -> str:
    kind = prob.get("kind", "")
    return kind if kind in F.VALID_KINDS else "broken_ui"


# --------------------------------------------------------------------- driver
def explore(repo_root: Path, *, persona_name: str = "sample", run_id: str | None = None,
            max_pages: int = 60, headless: bool = True) -> dict[str, Any]:
    """Full deterministic Stage-1 pass. Returns a small summary dict."""
    persona = Persona.load(repo_root, persona_name)
    rundir = RunDir(repo_root, run_id)
    with AppServer(repo_root, persona) as server, \
            BrowserSession(headless=headless, base_url=server.base_url) as browser:
        action_index = crawl(server, browser, rundir, max_pages=max_pages)
        rundir.write_action_index(action_index)
        runner = ScenarioRunner(server, browser, persona, rundir.base)
        run_interactions(runner, interaction_scenarios(server.job_ids), rundir)
    merged = rundir.consolidate()
    rundir.write_summary(action_index=action_index, findings=merged)
    return {"run_id": rundir.run_id, "run_dir": str(rundir.base),
            "routes": len(action_index),
            "actions": sum(len(v) for v in action_index.values()),
            "findings": len(merged),
            "high": sum(1 for f in merged if f["severity"] == "high")}
