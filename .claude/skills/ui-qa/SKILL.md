---
name: ui-qa
description: Run the multi-agent UI-QA swarm against the jobsearch web app — explore the UI like a human with a resume (indexing all actions and trying combinations across pages and sub-windows), validate the problems found, and open PRs that fix the confirmed ones. Use when the user wants to dynamically test the website's functionality, hunt for UI/route bugs, or "have agents click around the app and fix what breaks."
---

# UI-QA swarm

Drive the jobsearch UI the way a real user would, find what breaks, and fix it —
in three stages, each fanning out into multiple sub-agents. Design and artifact
schemas: `docs/design-ui-qa-swarm.md`. Harness: the `uiqa` package
(`python -m uiqa ...`). You are the **orchestrator**: you run the deterministic
floor, spawn the sub-agents, and move artifacts between stages.

## Setup (once)

```
pip install -r requirements.txt          # fastapi, uvicorn, playwright, httpx…
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers   # use the pre-installed browser
```
If `python -m uiqa explore --max-pages 2` errors on a missing browser, tell the
user Chromium isn't available and stop — the swarm needs a real browser.

## Stage 1 — Explore (deterministic floor + explorer swarm)

1. Run the deterministic crawl to guarantee coverage and seed the run dir:
   ```
   python -m uiqa explore
   ```
   Note the printed `run_dir` (`reports/uiqa/<run-id>`). It now holds
   `action-index.json` (every route → every action), `session-log.jsonl`, and
   baseline `findings.jsonl`.

2. **Spawn `ui-explorer` sub-agents — one per app area, all in a single message
   so they run concurrently.** Areas: `dashboard`, `jobs`, `prep`, `companies`,
   `clusters`, `resume`, `profile`, `settings`, `emails`. Give each agent its
   `AREA` and the `RUN_DIR`. They explore intuitively, open sub-pages, try edge
   cases/combinations, and drop findings as `RUN_DIR/incoming/*.json`.

3. Merge everything:
   ```
   python -m uiqa consolidate --run-dir reports/uiqa/<run-id>
   ```

## Stage 2 — Validate (validator swarm)

Spawn one or more `ui-validator` sub-agents (split `findings.json` ids across
them if there are many; run them in parallel). Each replays its findings with
`python -m uiqa replay`, reads the code to judge real-vs-expected, and writes
verdicts into `RUN_DIR/validation.json`. Then re-consolidate so `summary.md`
reflects verdicts:
```
python -m uiqa consolidate --run-dir reports/uiqa/<run-id>
```
The `confirmed_ids` it prints are the only ones that proceed.

## Stage 3 — Fix (fixer swarm)

For each confirmed bug (or each group sharing one root cause), **spawn a
`ui-fixer` sub-agent** — multiple fixers in parallel, each on its own branch.
Give each its `FINDING_ID(s)`, the validator's `root_cause`/`suggested_fix`, and
the `RUN_DIR`. Each writes the fix + a regression test, proves the bug no longer
reproduces and the suite is green, and opens a **draft PR**.

## Reporting

Finish with a digest: routes explored, actions indexed, findings by severity,
confirmed vs. dismissed, and the PR(s) opened. Point the user at
`reports/uiqa/<run-id>/summary.md`.

## Knobs & modes

- **Scope:** ask the user, or default to the full sweep. For a quick check, run
  only Stage 1 deterministic (`python -m uiqa explore`) and report findings.
- **Demo / low-noise fix:** if the user wants just one proof-of-concept PR, run
  Stages 1–2 fully, then spawn a single `ui-fixer` for the highest-severity
  confirmed bug.
- **Persona:** `--persona <name>` (default `sample` = the bundled resume). Drop
  a `data/personas/<name>.json` (`{"resume_text": ..., "profile": {...}}`) to
  simulate a different applicant.
- **Side effects:** the harness indexes but never auto-fires actions that launch
  the integrated apply browser, run the pipeline, or touch Gmail. Only exercise
  those with explicit user say-so.
- Artifacts live under `reports/uiqa/` (gitignored). Nothing here touches the
  user's real `data/` or `reports/` — every run uses an isolated temp app.
