# Architecture — how the whole repo fits together

> **Read this first.** It is the map of the territory: the two halves of the
> system, how data flows from "a company has a job" to "you applied to it," what
> every directory is for, and where state lives. Deep dives live in
> [`pipeline.md`](pipeline.md) and [`webapp.md`](webapp.md); concrete journeys
> in [`user-flows.md`](user-flows.md); the honest caveats in
> [`limitations.md`](limitations.md). The existing `design-*.md` / `analysis-*.md`
> docs explain *why* specific decisions were made — see [the index](README.md).

## What this project is, in one paragraph

`jobsearch` is a **personal, local-first job hunt automation tool**. Point it at
your résumé and it (1) pulls live postings straight from ~68 companies' own
applicant-tracking systems (ATS) — no aggregators, (2) figures out which roles
your résumé is actually for and filters to them, (3) ranks every posting by how
well it matches your résumé using TF-IDF + K-means, weighting recent postings
higher, (4) writes a daily Markdown/CSV/JSON report, and (5) gives you a local
web app to triage that report, auto-fill application forms from your profile,
study company-specific interview questions, find referrals, and sync
confirmation emails. Everything personal stays on your machine.

## The two halves

The repo is two cooperating programs that share files on disk. They are coupled
**only** through a handful of artifacts under `reports/` and `data/` — neither
imports deeply into the other's runtime (the one bridge is `python -m jobsearch
ingest`, which the webapp calls).

```
┌──────────────────────────────────────────────────────────────────────────┐
│  HALF 1 — THE PIPELINE  (jobsearch/ package, a CLI)                        │
│  `python -m jobsearch run` — batch, runs daily (locally or via GitHub CI)  │
│                                                                            │
│   settings.yaml ─┐                                                         │
│   companies.yaml ├─► load registry ─► fetch boards ─► filter ─► score ─►   │
│   occupations.yaml┘     (API + browser)   (role-aware)  (TF-IDF/KMeans)    │
│   résumé ─────────► role profile ─────────────────────────────────────►   │
│                                                                            │
│                                    writes ▼                                │
│   reports/latest.{md,csv,json}, reports/clustering.json, run-log.{json,md},│
│   reports/validation-request.md, data/seen_jobs.tsv, data/corpus/*.jsonl.gz│
└──────────────────────────────────────────────────────────────────────────┘
                                    │  reports/latest.json  +  clustering.json
                                    ▼  (read by `ingest` and the Fit-map views)
┌──────────────────────────────────────────────────────────────────────────┐
│  HALF 2 — THE WEB APP  (webapp/ package, FastAPI + uvicorn)               │
│  `python -m jobsearch ui` → http://127.0.0.1:8484 — interactive, long-lived│
│                                                                            │
│   ingest latest.json ─► SQLite (data/jobsearch.db)                         │
│        dashboard · job detail · résumé · profile · settings · emails       │
│        Fit map · companies/LeetCode · prep curriculum · referrals          │
│        integrated Chromium: open posting → auto-fill form (never submits)  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why two programs and not one?** The pipeline is a stateless batch job that is
happy to run head­less in CI and commit its output back to the repo. The web app
is a stateful, long-lived server holding your PII and driving a real browser.
Keeping them separate means a daily scheduled run needs none of the web app, and
the web app can be restarted without re-fetching. The web app even runs the
pipeline as a **subprocess** (`webapp/runner.py`) rather than importing it, so a
crash or Playwright hang in a fetch never takes down the server.

## The pipeline at a glance (`jobsearch/pipeline.py::run`)

One function, `run(root)`, is the spine. Each numbered stage is detailed in
[`pipeline.md`](pipeline.md); here is the whole arc so you can hold it in your head:

| # | Stage | Code | In → Out |
|---|-------|------|----------|
| 1 | Load config + registry | `config.load_settings`, `config.load_registry` | yaml → `settings`, `[Company]` (curated `companies.yaml` **merged with** generated `data/companies.discovered.yaml`) |
| 2 | Load résumé | `resume.load_resume_text` | `data/resume.txt` (or bundled sample) → text + `is_sample` flag |
| 3 | Role targeting | `role_profile.resolve_profile` / `apply_profile` | résumé → nearest occupation in `occupations.yaml`; **overrides** `search.query`/`title_include`/`title_exclude` so a non-SWE résumé stops getting SWE jobs |
| 4 | Fetch all boards | `pipeline.fetch_all` | `[Company]` → `[JobPosting]`; parallel **API pass** (threads) then sequential **browser pass** (one shared headless Chromium); a broken board becomes a `FetchError`, never crashes the run |
| 5 | Dedupe + snapshot | `pipeline.dedupe`, `corpus.write_snapshot` | dedupe by `job.key`; persist the full corpus to `data/corpus/<date>.jsonl.gz` for offline replay |
| 6 | Filter | `filters.JobFilter.classify`, `build_funnel` | each posting → `MATCH` / `NEAR_TITLE` / `NEAR_LOCATION` / `OUT`, plus an age cutoff and a per-company funnel |
| 7 | Score by fit | `scoring.score_jobs` | TF-IDF over the **whole fetched corpus** + K-means; `fit = 0.85·cosine(résumé) + 0.15·cluster_affinity`, scaled so the day's best = 100 |
| 8 | Recency weight + rank | `scoring.apply_recency`, `rank_companies` | `rank_score = fit · 0.5^(age_days/half_life)`; company fit = mean of its top-3 |
| 9 | Seen-state | `state.load_seen` / `mark_new` / `update_seen` | flag 🆕 jobs vs `data/seen_jobs.tsv` |
| 10 | Merge validation | `validation.apply_verdicts` | fold yesterday's Claude verdicts (`data/validation.json`) into a confidence column |
| 11 | Write reports | `report.write_reports` / `write_clustering` / `write_run_log`, `validation.write_validation_request` | all the `reports/*` artifacts |

`python -m jobsearch verify` runs only stage 4 and prints which boards are
reachable. `discover` / `discover-companies` are separate registry-building
commands (see [`pipeline.md`](pipeline.md#discovery-commands)).

## The web app at a glance (`webapp/app.py::create_app`)

A single FastAPI factory builds the whole app; every route is a closure over the
shared SQLite connection, the apply-browser registry, and the pipeline runner.
On startup it seeds the prep curriculum and curated company questions into the
DB (idempotent, content-hash guarded). The surface area, grouped:

- **Triage** — `/` dashboard (to-apply / in-progress / applied stacks), `/jobs/{id}` detail with a copy-paste profile panel and the company's top interview questions.
- **Apply** — per-job "⚡ Auto-fill apply" opens the posting in its own tab of one shared, **headed** Chromium window and fills the form from your profile; it **never clicks submit**. Submission is detected by watching for a confirmation page.
- **Inputs you edit** — `/resume` (upload + run pipeline), `/profile` (the PII used for autofill), `/settings` (read-only view of the search config).
- **Insight** — `/clusters` Fit map (visualizes the TF-IDF/K-means space and breaks down any single score), `/emails` (Gmail read-only sync that auto-advances applied→confirmed).
- **Prep** — `/prep` (offline interview curriculum: 3 tracks distilled from CtCI/DDIA/System Design Interview), `/companies` (what each company asks on LeetCode), `/jobs/{id}/referrals` (LinkedIn people search, ranked by fit).

Full route table and DB schema: [`webapp.md`](webapp.md).

## Directory map

```
config/
  settings.yaml          ★ every tuning knob (filters, ranking, fetch, discovery, prep, referrals)
  companies.yaml         ★ curated registry: ~68 companies → their ATS; + manual_check list
  occupations.yaml         O*NET-shaped occupation taxonomy (résumé → target roles/skills)

jobsearch/                 HALF 1 — the pipeline (a Python package, run via `python -m jobsearch`)
  __main__.py              CLI entry: run | verify | discover | discover-companies | ingest | ui
  pipeline.py              orchestration (the run() spine above)
  config.py  models.py  utils.py   config loading; dataclasses (Company, JobPosting, …); shared helpers
  resume.py  role_profile.py        résumé intake; résumé → occupation matching (TF-IDF / optional MiniLM)
  http.py  browser.py                requests Session factory; headless-Chromium XHR-harvesting runtime
  fetchers/                          one adapter per ATS / company API  (FETCHERS + BROWSER_FETCHERS)
  sources/                           company-lead mining for discovery (The Muse, HN "who is hiring", Adzuna)
  discover.py  company_discovery.py  single-company ATS slug detection; résumé-tailored registry generation
  filters.py  scoring.py             title/location/remote filtering; TF-IDF+K-means fit + recency + Fit-map data
  state.py  corpus.py  validation.py seen-job TSV; corpus snapshots; the Claude validation loop
  report.py                          renders reports/latest.{md,csv,json}, run-log, clustering.json
  prep/                              the interview-prep curriculum (authored content + seeders)
  company_questions/                 curated company→LeetCode sets + the GitHub-CSV refresh loader
  referrals/                         LinkedIn people-search discovery + fit ranking + storage

webapp/                    HALF 2 — the web app (FastAPI + Jinja2 + uvicorn)
  app.py                   the create_app factory; all routes
  db.py                    the SQLite data model + every query (the only persistence layer)
  ingest.py  runner.py     pull reports/latest.json into the DB; run the pipeline as a subprocess
  profile.py               the editable PII store (also seeds from your résumé)
  ats.py  apply_browser.py autofill.py   apply-leg: canonicalize URLs, drive the shared browser, fill forms
  gmail.py  emailmod.py    raw-OAuth Gmail read-only sync; classify/link job emails
  clusters.py  textfmt.py  load clustering.json for the Fit map; description/markdown → HTML
  prep_render.py prep_sources.py company_questions.py   webapp glue for prep + company questions
  templates/  static/      Jinja2 pages; the "Aurora" CSS theme + vanilla-JS progressive enhancements

tools/build_occupations.py   offline: distill a full O*NET release into config/occupations.yaml
tests/                       ~257 fully-offline tests (no network, no live browser)
docs/                        design rationale, analyses, and THIS reference set
.github/workflows/           the daily scheduled pipeline run (commits the report back)
setup.sh                     one-command install + launch
```

## Where state lives (everything personal is gitignored)

The repo ships **only** code, config, and `data/sample_resume.txt`. Everything
else under `data/` and `reports/` is created at runtime and ignored by git
(`.gitignore` lines 52–68). Knowing what each artifact is makes the whole system
legible:

| Path | Written by | Read by | What it is |
|------|-----------|---------|------------|
| `data/resume.txt` | `/resume/upload` (or you) | pipeline, profile seeding | the résumé that drives targeting + scoring |
| `data/resume.pdf` (+ `.name`) | `/resume/upload` | apply browser (file upload) | original PDF re-attached to forms under its real filename |
| `data/sample_resume.txt` | *shipped* | pipeline fallback | so a fresh clone works before you upload anything |
| `data/role_profile.json` | pipeline stage 3 | webapp `/resume` | what the last run targeted (occupations, skills) |
| `data/companies.discovered.yaml` | `discover-companies` | `config.load_registry` | generated résumé-tailored registry, merged *under* the curated one |
| `data/seen_jobs.tsv` | pipeline stage 9 | pipeline | `key<TAB>date` per posting ever seen → drives 🆕 (TSV so git merges cleanly) |
| `data/corpus/<date>.jsonl.gz` | pipeline stage 5 | `ingest` (descriptions), offline experiments | full fetched corpus snapshot, 14-day retention |
| `data/validation.json` | the `/validate-jobs` skill | pipeline stage 10 | Claude's per-posting verdicts (live/senior/NYC) |
| `data/validation-history/<date>.json` | pipeline stage 10 | you (precision over time) | archived verdicts |
| `data/jobsearch.db` | webapp (`webapp/db.py`) | webapp | **the web app's entire world**: jobs, applications + history, profile PII, emails, prep progress, company questions, referrals |
| `data/credentials.json` / `data/token.json` | you / Gmail OAuth | `webapp/gmail.py` | Google OAuth desktop client + access/refresh token (chmod 600) |
| `data/browser_profile/` | apply browser, LinkedIn discoverer | same | persistent Chromium profiles (cookies, ATS + LinkedIn logins) |
| `reports/latest.{md,csv,json}` | pipeline stage 11 | you, `ingest` | the daily report (json is the machine-readable one) |
| `reports/<date>.md` | pipeline stage 11 | you | dated copy committed by CI |
| `reports/clustering.json` | pipeline stage 11 | webapp `/clusters` | the Fit-map model snapshot (2-D projection + per-job score breakdown) |
| `reports/run-log.{json,md}` | pipeline stage 11 | you (debugging) | what the run targeted, board results, the fetch→match funnel |
| `reports/validation-request.md` | pipeline stage 11 | the `/validate-jobs` skill | the postings to fact-check today |

## How the three config files relate

This trips people up, so it is worth stating plainly (the relationships
otherwise live only in scattered comments):

- **`settings.yaml`** is the keystone. It holds the knobs and *points at* the
  other files (`role.occupations_file`, `discovery.output_file`). Its
  `search.title_include/exclude/query` are the **manual** targeting — used as-is
  only when `search.role_targeting: manual`.
- **`occupations.yaml`** is the taxonomy résumés are matched against. Under the
  default `role_targeting: auto`, the matched occupation's query + title patterns
  **replace** the manual ones in `settings.yaml` at runtime. Expand it from the
  full O*NET database with `tools/build_occupations.py`.
- **`companies.yaml`** is *which boards to pull*, independent of *what role*. The
  `ats:` field selects a fetcher; extra keys (`board`, `org`, `tenant`…) are
  passed to it as params. There is **no `enabled` flag** — every listed company
  is always fetched and then ranked; to "disable" one, move it to the
  `manual_check:` list (which the report surfaces as "check by hand").
- **`data/companies.discovered.yaml`** (generated, gitignored) is merged *under*
  `companies.yaml` at load time — curated entries always win, and
  `discovery.exclude_companies` can never be re-added by a stale generated file.

## The data contract between the two halves

The web app does not parse Markdown or re-derive scores. The bridge is
**`reports/latest.json`** (jobs + near-miss + funnel, descriptions intentionally
omitted to keep it light) plus the matching **`data/corpus/<date>.jsonl.gz`**
(which carries the descriptions). `webapp/ingest.py::ingest_latest` joins them by
`job.key`, upserts each posting into the `jobs` table (recording an append-only
diff in `job_events` and creating an `applications` row), and inserts a `runs`
row. Dedup is by `key`, so re-ingesting the same report is a no-op. The Fit-map
views read **`reports/clustering.json`** directly. That is the entire coupling.

> **One important consequence:** the dashboard *accumulates*. Ingest adds the
> latest run's jobs but never deletes earlier ones, so postings from a previous
> (possibly differently targeted) run stay in your to-apply stack. The dashboard
> defaults to `run_scope=latest` and shows a "N unapplied jobs from earlier runs"
> note to make leftovers obvious. See [`limitations.md`](limitations.md).

## Mental models that make the code click

- **"A broken board never sinks the run."** Every fetch is wrapped; failures
  become `FetchError`s that land in the report's "needs attention" section. The
  same philosophy governs the optional bits: no Chromium → browser boards are
  skipped with a note; no Adzuna key → that source is skipped; refresh dataset
  unreachable → the bundled questions stay. The pipeline always produces a report.
- **Fit scores are *relative ranks*, not absolute percentages.** They are scaled
  so the best posting of the day is 100. A quiet day still has a 100. Trust the
  ordering, not the magnitude (`scoring.py`, and the report says so up top).
- **The whole corpus is the scoring context, not the survivors.** TF-IDF and
  K-means are fit on every fetched posting, then matched/near-miss jobs are scored
  *inside* that space. This is deliberate — see `analysis-scoring-skew.md`.
- **Human-in-the-loop everywhere it touches the outside world.** The apply
  browser fills forms but you click submit. Gmail is read-only. LinkedIn is
  headed and you log in yourself. Validation uses your Claude subscription
  interactively, not an API key.
- **Seed-then-track.** Prep content and company questions are *derived data*:
  rebuilt from code on every startup (idempotent, hash-gated), while your
  progress lives in separate `*_progress` tables keyed by stable row id, so
  reseeding never wipes what you've done.
