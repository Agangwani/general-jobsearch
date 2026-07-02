# CLAUDE.md

Daily job-search pipeline (`jobsearch/`) + FastAPI application tracker (`webapp/`),
plus a UI-QA agent swarm (`uiqa/`) and a static portfolio site. Python 3.14 local,
3.11 in CI. Resume-driven: most behavior derives from `data/resume.txt`.

## Commands
- Run pipeline: `python -m jobsearch run` → `reports/latest.md` (+ CSV, `clustering.json`)
- Startups track: `python -m jobsearch run-startups` → `reports/startups/`
- Verify boards reachable: `python -m jobsearch verify [--startups]`
- Load reports into DB: `python -m jobsearch ingest`
- Tracker UI: `python -m jobsearch ui` → http://127.0.0.1:8484 (loopback-only)
- Discover: `python -m jobsearch discover <company>` | `discover-companies` | `discover-startups`
- **Tests: `python -m pytest -q`** — this is exactly what CI runs. No lint/format/type tooling is configured.

Deps: `requirements.txt` + `Pipfile`/`Pipfile.lock` (keep in sync). No `pyproject.toml`.
First-time setup: `./setup.sh`.

## Validate every change — IMPORTANT
1. Run `python -m pytest -q` and report exact pass/fail counts. Keep the full suite green.
2. Any behavior change ships with a **fails-before / passes-after regression test** (verify it
   fails when you revert the fix).
3. **One root cause per change.** Do not touch unrelated failing tests — but DO refresh a
   genuinely stale test whose assertion no longer matches hardened behavior (don't leave it red
   and cite it as "pre-existing").
4. For a runtime-facing change, exercise it for real (`/verify`, drive the route, `python -m
   jobsearch run`), not just tests.
5. When you fix an input/parsing bug, **grep for duplicate or inline copies of the same query
   or logic** — this class of bug recurs because a second copy was missed (e.g. int64 overflow
   fixed in one handler but not `api_history`'s inline query).

## Tools available to you
- **Skills** (`.claude/skills/`): `/ui-qa` (explore→validate→fix web-app bugs), `/validate-jobs`
  (web-verify the day's report → `data/validation.json`). Prefer these over ad-hoc equivalents.
- **UI-QA subagents** (`.claude/agents/ui-*.md`): explorer → validator → fixer swarm; findings
  live under `reports/uiqa/<run-id>/` (gitignored). Reproduce a finding with
  `python -m uiqa replay --id <finding>` (`reproduced: false` proves the fix).
- Use subagents / `Explore` for broad multi-file investigation to protect main context.

## Architecture (data flow)
`config/companies.yaml` (+ gitignored generated registries) → `jobsearch/fetchers/` pull
postings → `filters.py` (title/location funnel: MATCH vs near-miss) → `scoring.py` (resume
TF-IDF cosine + K-means cluster affinity + recency decay) → `report.py` writes dated markdown/
CSV/`clustering.json` → `webapp ingest` → `data/jobsearch.db` → tracker UI.

- **Two independent pipelines** (main + startups) with fully separate report dirs, seen-state,
  and corpus dirs — never let them share state.
- **Tuning lives in `config/settings.yaml`** (all keys have code defaults); role knowledge in
  `config/occupations.yaml`. Prefer config changes over hardcoding.
- Deep design docs in `docs/` (`architecture.md`, `pipeline.md`, `webapp.md`, `design-*.md`).

## Product invariants — do not break
- **Resume-tailored, non-repetitive.** Output is tailored per resume; don't surface the same
  companies/jobs every run. Generated registries and startup metadata are gitignored because
  they derive from the resume — don't commit them.
- **Graceful degradation.** One failing board never sinks a run; browser (Playwright) boards
  are optional and API boards must still work without Chromium. Keep `# noqa: BLE001` broad
  catches around per-board fetches.
- **Security.** The UI is unauthenticated locally and exposes PII / resume / Gmail / browser
  control — the loopback-only bind guard (`--allow-remote` to override) is intentional; keep it.
- Side-effecting UI actions (apply-browser, pipeline, Gmail send) are indexed but **never
  auto-fired** — don't add code paths that trigger them without explicit user action.

## Git
Branch off `main`; commit/push only when asked. Scope each PR to one root cause. After merging
parallel agent branches, confirm the test suite still *collects* (no `<<<<<<<` conflict
markers, no emptied test bodies) — not just that it passes.

Area-specific rules load automatically when you edit `webapp/`, `jobsearch/`, or `tests/`.
