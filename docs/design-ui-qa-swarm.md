# UI-QA Swarm: agents that explore the UI, validate breakage, and fix it

> **Status (2026-06-22): shipped (v1).** The `uiqa` harness drives the live app
> with a real headless Chromium; `python -m uiqa explore` does a deterministic
> crawl (40 routes, ~1.9k actions indexed on the seeded app) and a curated
> combination battery; three Claude sub-agent types (`ui-explorer`,
> `ui-validator`, `ui-fixer`) layer human-like exploration, triage, and fixes on
> top; `/ui-qa` orchestrates the whole swarm. The first run found a real
> dashboard 500 (`/?min_fit=abc`) end-to-end and Stage 3 opened a fix PR for it.

## The question this answers

*"Can a Claude agent navigate the UI like a user with a given resume — opening
sub-pages and sub-windows, indexing every action, trying combinations, logging
errors — then have another agent validate the errors, and a final agent open PRs
that fix them? With sub-agents and multiple agents spawned throughout."*

Yes. The design mirrors the proven `validate-jobs` loop (docs/design-validation-loop.md):
a cheap deterministic tier does what a script can, and Claude is spent only on
the judgment a script can't make — here, *human-like* exploration and
*is-this-actually-a-bug* triage. Everything is filesystem-mediated (JSON
artifacts), so sub-agents that share no memory can hand work down the pipeline.

## Why a harness + agents, not just one or the other

- **A pure script** can crawl and assert, but can't explore *intuitively* —
  "upload a tiny resume, then open the fit map before the run finishes," "type
  letters into the min-fit box," "open a job, change status, hit back." That
  open-ended, resume-in-hand behavior is what catches the interesting bugs.
- **A pure agent driving a browser** explores intuitively but is
  non-reproducible, can't *guarantee* it indexed every action, and produces no
  durable repro for the next stage.

So `uiqa` is the deterministic **floor** (coverage + reproducibility) and the
agents are the **ceiling** (intuition + judgment). A *scenario* — an ordered
list of UI actions in JSON — is the shared unit: an explorer authors one, the
runner executes it capturing per-step errors, and Stage 2 replay re-runs the
exact same file. The scenario *is* the repro.

## Architecture

```
                ┌────────────────────────── uiqa harness (python -m uiqa) ──────────────────────────┐
                │  AppServer            BrowserSession         actions.index_actions    scenario.run  │
                │  (isolated, seeded    (real Chromium;        (every clickable          (journey      │
                │   app on a temp port; console/JS/network     element → stable          runner +      │
                │   captures server      capture incl.         selector + label +        per-step      │
                │   tracebacks)          pop-up windows)       side-effect flags)         error attrib) │
                └───────────────────────────────────────────────────────────────────────────────────┘
   Stage 1 EXPLORE                         Stage 2 VALIDATE                 Stage 3 FIX
   ─────────────                           ────────────────                 ───────────
   python -m uiqa explore   ──►            ui-validator × N   ──►            ui-fixer × N
   (deterministic floor:                   replay each finding,             one confirmed bug each,
    crawl + battery)                        read code, rule it              on its own branch:
   + ui-explorer × (areas)                  confirmed / WAI /               fix + regression test,
   intuitive journeys, edge                 flaky / needs-info              prove repro gone + suite
   cases, sub-pages          findings.json  ──► validation.json  confirmed   green, open draft PR
   ──► incoming/*.json                                            ──►
```

Multiple agents are spawned in **every** stage: an explorer per app area, a
validator per finding-batch, a fixer per confirmed bug — all run in parallel.

### The harness (`uiqa/`)

| Module | Role |
|--------|------|
| `appserver.py` | Boots `python -m jobsearch ui` on an ephemeral port against a **throwaway** project root: copied `config/`, a persona-seeded `data/`, a fresh DB pre-loaded with fixture jobs, and a matching `reports/clustering.json`. Tees stdout+stderr to a log so **server-side tracebacks** are catchable. Never touches the user's real `data/`/`reports/`. |
| `browser.py` | A real headless Chromium with capture wired on the whole **context** — so apply-browser pop-ups / `target=_blank` sub-windows are watched too. Records console errors/warnings, uncaught JS exceptions, failed requests, and 4xx/5xx responses. Off-origin resource failures (blocked fonts/CDNs) are down-ranked to `low` — they're the environment, not the app. |
| `actions.py` | `index_actions(page)` enumerates every interactive element with a stable selector, a human label, and flags (`side_effecting`, `external`, `navigates`). This is the "index all actions" guarantee. |
| `persona.py` | The simulated user: a resume (default = bundled sample) + realistic profile values, and `value_for()` so form fills look like a real applicant. |
| `fixtures.py` | Deterministic seed jobs + a complete `clustering.json` so `/jobs/{id}`, `/clusters/job/{id}`, `/companies/{key}`, referrals, etc. are reachable and render their populated (not empty) state. |
| `scenario.py` | The step vocabulary + runner. Executes a journey, draining browser **and** server errors after each step to attribute them to the step that caused them. `run_scenario_file()` is also Stage-2 replay. |
| `explore.py` | Stage-1 deterministic pass: BFS crawl (indexing every route, discovering sub-pages via in-area links) + a curated combination battery (filter×sort, edge inputs, valid/invalid upload, profile save, in-place status change). |
| `findings.py` | The shared finding/verdict vocabulary + stable-signature dedup so the crawler and several explorers reporting the same break collapse to one id. |
| `report.py` | The run directory and `summary.md`. |

### The agents (`.claude/agents/`)

- **`ui-explorer`** — given an `AREA` and `RUN_DIR`, indexes its routes, opens
  sub-pages, and runs intuitive/edge scenarios; files findings as
  `incoming/*.json`. Spawn one per area, in parallel.
- **`ui-validator`** — replays findings, reads the code, and rules each
  `confirmed | works_as_intended | flaky | needs_info` with a root cause; writes
  `validation.json`.
- **`ui-fixer`** — one confirmed bug per agent, on its own branch: minimal fix +
  regression test, proves repro gone and suite green, opens a draft PR.

### The orchestrator (`.claude/skills/ui-qa/SKILL.md`)

`/ui-qa` runs the deterministic floor, spawns the three swarms in sequence
(parallel within each stage), and shuttles artifacts between them.

## Step vocabulary (scenarios)

`goto · click · fill · select · check/uncheck · upload · back · wait · index ·
snapshot · expect_status · expect_text · expect_no_error`. `value:"$persona"`
auto-fills a field as the persona; `file:"$resume"|"$tiny"|"$resume_pdf"` covers
valid + invalid uploads. Full reference: the `uiqa/scenario.py` docstring.

## Artifacts (under `reports/uiqa/<run-id>/`, gitignored)

| File | Written by | Consumed by |
|------|-----------|-------------|
| `action-index.json` | crawl | explorers (what to try), humans |
| `session-log.jsonl` | crawl + battery | debugging, audit |
| `findings.jsonl` / `incoming/*.json` | crawl / explorers | `consolidate` |
| `findings.json` | `consolidate` (dedup+merge) | validators, fixers |
| `validation.json` | validators | fixers, `summary.md` |
| `scenarios/*.json` | battery + explorers | replay (repro) |
| `screenshots/*.png` | runner (on problems) | evidence |
| `summary.md` | `consolidate` | humans |

**Finding** = `{area, route, kind, severity, title, detail, repro(scenario),
evidence[], discovered_by, status, id}`.
**Verdict** = `{finding_id, verdict, reproduced, root_cause, suggested_fix,
severity, validated_by}`.

## What's deliberately *not* auto-fired

Actions with real-world side effects — launching the integrated apply browser
(`⚡ Auto-fill`), running the pipeline (`▶ Run`), `Prepare top 5`, Gmail
connect/sync, LinkedIn referral discovery — are **indexed but never triggered**
automatically (flagged `side_effecting`). They hit the network, spawn a second
real browser, or mutate external state; exploring them is opt-in and
human-supervised. This is the same "don't make Claude/automation do something
irreversible without a human" stance as the apply flow that never clicks submit.

## How completeness is achieved (mapping to the ask)

| Requirement | Mechanism |
|-------------|-----------|
| simulate a user with a given resume | `Persona` seeds role targeting + profile; default = bundled resume; `--persona` for others |
| navigate pages intuitively | `ui-explorer` agents author human-like journeys |
| open & interact with sub-pages / sub-windows | BFS follows in-area links; capture is on the whole browser context (pop-ups included) |
| index all actions | `actions.index_actions` per route → `action-index.json` |
| explore combinations | curated battery + open-ended agent journeys |
| log errors | console/JS/network + **server tracebacks**, per step |
| analyze + produce output | `findings.json` + `summary.md` |
| another agent validates | `ui-validator` swarm → `validation.json` |
| final agent opens PRs | `ui-fixer` swarm → draft PRs |
| sub-agents + multiple agents | parallel fan-out in all three stages |

## First-run evidence (2026-06-22)

The deterministic floor alone indexed ~1,942 actions across 40 routes and — once
off-origin CDN noise was down-ranked — surfaced exactly one real defect, as three
facets of the same crash: `/?min_fit=abc` returns **HTTP 500** because the
dashboard handler does `float(min_fit)` on raw query input without a guard
(`webapp/app.py`), unlike its sibling handlers which parse user input
defensively. Validation confirmed it; Stage 3 shipped a guard + a `TestClient`
regression test and opened a draft PR.

## Future work

- **Per-page learned action maps** — cache which selectors/journeys mattered so
  later runs prioritize them (cf. the autofill design's learned field maps).
- **CI integration** — a nightly GitHub Action runs Stage 1 + 2 and files an
  issue (or auto-PR) when a new high-severity finding appears, gating merges.
- **Playwright MCP as an alternative driver** — if a session prefers Claude to
  drive the browser natively, the same scenario/finding schemas apply; the
  Python harness stays the reproducible floor and CI engine.
- **Tier-1 static checks** — template/route lints (every `url_for`-style link
  resolves; every form's action route exists) before spending browser time.
- **Visual diffing** — screenshot baselines per route to catch layout
  regressions the DOM-level capture misses.
```
