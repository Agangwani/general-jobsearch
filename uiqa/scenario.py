"""Run a scenario — an ordered list of user actions — and report what broke.

A scenario is the unit of exploration *and* the unit of reproduction: an
explorer agent writes one to express a journey ("upload a tiny resume, then open
the fit map"), the runner executes it capturing per-step browser + server
errors, and Stage 2 validation replays the exact same file. Plain JSON, so
agents author and diff them trivially.

Step vocabulary (each step is {"action": ..., ...params}):
  goto    {path}                     navigate (path is app-relative or full URL)
  click   {selector|text}            click an element
  fill    {selector, value}          type into an input (value "$persona" → auto)
  select  {selector, value}          choose an <option> (value "$first" → first real)
  check / uncheck {selector}         toggle a checkbox
  upload  {selector, file}           set a file input (file "$resume"|"$tiny"|path)
  back    {}                         browser back
  wait    {ms} | {selector}          pause / wait for an element
  index   {}                         attach the page's action index to the result
  snapshot{name}                     full-page screenshot
  expect_status {code}               assert the last navigation's HTTP status
  expect_text   {text, present?}     assert body text contains / lacks `text`
  expect_no_error {}                 assert no high/medium severity event in step
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .actions import index_actions
from .appserver import AppServer
from .browser import BrowserSession
from .persona import Persona

# Severities that, when captured during a step, mark the step as having found a
# problem even without an explicit expect.
_PROBLEM_SEVERITIES = {"high", "medium"}


class ScenarioRunner:
    def __init__(self, server: AppServer, browser: BrowserSession,
                 persona: Persona, out_dir: Path):
        self.server = server
        self.browser = browser
        self.persona = persona
        self.out_dir = out_dir
        self._uploads: dict[str, str] = {}
        self._last_status: int | None = None

    # ------------------------------------------------------------------- public
    def run(self, scenario: dict[str, Any]) -> dict[str, Any]:
        name = scenario.get("name", "scenario")
        steps = scenario.get("steps", [])
        self.server.server_errors_since()  # reset cursor to "now"
        self.browser.drain()               # clear any pre-existing events
        results: list[dict[str, Any]] = []
        for i, step in enumerate(steps):
            results.append(self._run_step(i, step, name))
        problems = [r for r in results if r["problems"]]
        return {
            "name": name,
            "persona": self.persona.name,
            "steps": results,
            "ok": not problems,
            "problem_count": len(problems),
            "final_url": self.browser.current_url(),
        }

    # --------------------------------------------------------------- per-step
    def _run_step(self, i: int, step: dict[str, Any], scn: str) -> dict[str, Any]:
        action = step.get("action", "")
        res: dict[str, Any] = {"i": i, "action": action, "params": _params(step),
                               "ok": True, "error": "", "problems": []}
        http_status = None
        try:
            http_status = self._dispatch(action, step, res)
        except Exception as exc:  # noqa: BLE001 — a failed action is a result, not a crash
            res["ok"] = False
            res["error"] = f"{type(exc).__name__}: {exc}"[:500]

        # Attribute everything that happened during the step.
        events = [e.to_dict() for e in self.browser.drain()]
        server_errs, _ = self.server.server_errors_since()
        res["events"] = events
        res["server_errors"] = server_errs
        res["url"] = self.browser.current_url()
        if http_status is not None:
            res["http_status"] = http_status

        problems = [e for e in events if e["severity"] in _PROBLEM_SEVERITIES]
        if server_errs:
            problems.append({"kind": "server_error", "severity": "high",
                             "text": server_errs[0]})
        if not res["ok"] and action.startswith("expect"):
            problems.append({"kind": "assertion", "severity": "high",
                             "text": res["error"]})
        res["problems"] = problems
        # A screenshot is cheap insurance for anything that looked wrong.
        if problems or not res["ok"] or action == "snapshot":
            shot = self.out_dir / "screenshots" / f"{_slug(scn)}-{i}-{action}.png"
            res["screenshot"] = self.browser.screenshot(shot)
        return res

    def _dispatch(self, action: str, step: dict[str, Any], res: dict[str, Any]):
        if action == "goto":
            self._last_status = self.browser.goto(step["path"])
            return self._last_status
        if action == "click":
            self.browser.click(selector=step.get("selector", ""),
                               text=step.get("text", ""))
        elif action == "fill":
            self.browser.fill(step["selector"], self._value(step))
        elif action == "select":
            self.browser.select_option(step["selector"], self._option(step))
        elif action == "check":
            self.browser.set_checked(step["selector"], True)
        elif action == "uncheck":
            self.browser.set_checked(step["selector"], False)
        elif action == "upload":
            self.browser.upload(step["selector"], self._upload(step.get("file", "$resume")))
        elif action == "back":
            self.browser.go_back()
        elif action == "wait":
            if "selector" in step:
                self.browser.page.wait_for_selector(step["selector"], timeout=step.get("timeout", 8000))
            else:
                self.browser.page.wait_for_timeout(int(step.get("ms", 500)))
        elif action == "index":
            res["index"] = index_actions(self.browser.page)
        elif action == "snapshot":
            pass  # screenshot taken in _run_step
        elif action == "expect_status":
            self._expect_status(step)
        elif action == "expect_text":
            self._expect_text(step)
        elif action == "expect_no_error":
            pass  # evaluated from captured events in _run_step
        else:
            raise ValueError(f"unknown action: {action!r}")
        return None

    # ------------------------------------------------------------- assertions
    def _expect_status(self, step: dict[str, Any]) -> None:
        # Asserts against the status of the most recent goto.
        want = int(step["code"])
        if self._last_status is None:
            raise AssertionError("expect_status must follow a goto that navigates")
        if self._last_status != want:
            raise AssertionError(f"expected HTTP {want}, got {self._last_status}")

    def _expect_text(self, step: dict[str, Any]) -> None:
        present = step.get("present", True)
        needle = step["text"]
        body = self.browser.text()
        found = needle.lower() in body.lower()
        if present and not found:
            raise AssertionError(f"expected text {needle!r} not found on page")
        if not present and found:
            raise AssertionError(f"text {needle!r} should be absent but was present")

    # -------------------------------------------------------------- value help
    def _value(self, step: dict[str, Any]) -> str:
        v = step.get("value", "$persona")
        if v != "$persona":
            return str(v)
        sel = step["selector"]
        meta = self.browser.page.evaluate(
            "(sel)=>{const e=document.querySelector(sel);"
            "return e?{name:e.name||'',type:e.type||'',ph:e.placeholder||''}:null;}", sel) or {}
        return self.persona.value_for(name=meta.get("name", ""),
                                      input_type=meta.get("type", "text"),
                                      placeholder=meta.get("ph", ""))

    def _option(self, step: dict[str, Any]) -> str:
        v = step.get("value", "$first")
        if v != "$first":
            return str(v)
        opts = self.browser.page.evaluate(
            "(sel)=>{const e=document.querySelector(sel);"
            "return e?[...e.options].map(o=>o.value).filter(x=>x!==''):[];}",
            step["selector"]) or []
        if not opts:
            raise AssertionError("select has no selectable options")
        return opts[0]

    def _upload(self, token: str) -> str:
        if token in self._uploads:
            return self._uploads[token]
        if not token.startswith("$"):
            return token
        d = Path(tempfile.mkdtemp(prefix="uiqa-upload-"))
        if token == "$tiny":
            p = d / "tiny.txt"
            p.write_text("too short")  # trips the <100-char validation path
        elif token == "$resume_pdf":
            p = d / "resume.pdf"
            p.write_bytes(b"not a real pdf")  # trips the %PDF magic-byte check
        else:  # $resume — a valid text resume
            p = d / "resume.txt"
            p.write_text(self.persona.resume_text)
        self._uploads[token] = str(p)
        return str(p)


# --------------------------------------------------------------------- helpers
def _params(step: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in step.items() if k != "action"}


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower())[:40].strip("-") or "scn"


def run_scenario_file(repo_root: Path, scenario_path: Path, out_dir: Path, *,
                      persona_name: str = "sample", headless: bool = True) -> dict[str, Any]:
    """Boot an isolated app + browser, run one scenario file, return its result.
    Used by `python -m uiqa run-scenario` and Stage-2 replay."""
    scenario = json.loads(Path(scenario_path).read_text())
    persona = Persona.load(repo_root, scenario.get("persona", persona_name))
    out_dir.mkdir(parents=True, exist_ok=True)
    with AppServer(repo_root, persona) as server, \
            BrowserSession(headless=headless, base_url=server.base_url) as browser:
        runner = ScenarioRunner(server, browser, persona, out_dir)
        result = runner.run(scenario)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result
