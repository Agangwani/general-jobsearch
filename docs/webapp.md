# The web app — deep dive

> Half 2 of the system: the `webapp/` package, a FastAPI + Jinja2 app served by
> uvicorn (`python -m jobsearch ui` → http://127.0.0.1:8484). It is the
> human-facing layer over the pipeline: triage, apply-automation, email sync, the
> Fit map, interview prep, company questions, and referrals. High-level context is
> in [`architecture.md`](architecture.md); the data it reads comes from
> [`pipeline.md`](pipeline.md).

## Bootstrap (`webapp/app.py::create_app`)

One factory `create_app(root, db_path=None) -> FastAPI` builds everything; there
is no router-module split — every route is a closure inside the factory, capturing
the shared connection and helpers. Startup, in order:

1. `conn = db.connect(data/jobsearch.db)` — **one** shared `sqlite3.Connection`
   (`check_same_thread=False`, WAL, `foreign_keys=ON`, `row_factory=Row`). The
   schema is created with `CREATE TABLE IF NOT EXISTS` — there is no migration
   system (see [`limitations.md`](limitations.md)).
2. `profile.ensure_seeded` + `ensure_fields` — seed PII fields, top up new ones.
3. `seed_into_db(conn)` — load the interview-prep curriculum (idempotent,
   content-hash guarded).
4. `company_questions.seed_bundled(conn)` — load curated company→LeetCode sets.
5. `sessions = SessionRegistry(...)` — the integrated apply-browser registry.
6. `runner = PipelineRunner(root)` — runs the pipeline as a subprocess.
7. `discoverer = LinkedinDiscoverer(...)` — **lazy**; Playwright does not launch
   until the first referral search.

Jinja filters registered: `qp` (URL-quote), `description_html`, `prep_markdown`.
Static files mounted at `/static`; a `css_v` cache-buster is the stylesheet mtime.
A `render()` helper injects nav-badge counts (stack counts, prep progress, company
question counts) into every page.

`--allow-remote` is required to bind a non-loopback host, because the app is
**unauthenticated** and exposes profile PII, your résumé, Gmail, and browser
control. It is designed for `127.0.0.1` only.

## Route inventory

Grouped by area. `→ tmpl` = renders that template; `→ JSON`/`→ 303` otherwise.

### Dashboard & job detail
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | main job table; filters `q, company, stack, near_miss, sort_by, sort_dir, min_fit, status_filter, run_scope` (default `run_scope=latest` scopes to-apply to the latest run) → `dashboard.html` |
| GET | `/jobs/{job_id}` | detail: job + application + merged event timeline + linked emails + copy-paste profile panel + the company's top-6 LeetCode questions → `job_detail.html` |
| GET | `/api/jobs` | search jobs as JSON |
| GET | `/api/jobs/{job_id}/history` | `job_events` rows as JSON |

### Apply / autofill (drives the integrated browser)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/jobs/{job_id}/apply` | open the posting in a new tab + auto-fill (`sessions.launch`) |
| POST | `/jobs/{job_id}/refill` | re-run autofill on the open tab (e.g. after a profile edit) |
| GET | `/api/apply-status/{application_id}` | per-tab fill summary + current status (UI polls this) |
| POST | `/api/prepare-top` | launch+fill a tab for each of the top-N best-fit applyable jobs |
| POST | `/api/apply-all` | fill every job tab the user already opened (`sessions.apply_all`) |
| GET | `/api/apply-all-status` | all session statuses |
| POST | `/jobs/{job_id}/status` | set this user's status for a job (+ note); materializes the per-user application lazily → 303 |
| POST | `/applications/bulk-status` | batch set status for checked rows (checkbox values are `job_id`) → 303 |

### Pipeline run / ingest
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/run` | start a pipeline **subprocess** (`runner.start`); 409 if already running |
| GET | `/run/log?since=N` | poll run output; **side effect**: on the first poll after a clean finish, auto-runs ingest and appends a summary |
| POST | `/ingest` | manually ingest `reports/latest.json` → 303 |
| POST | `/resume/run` | run the pipeline **in-process** in a thread (the `/resume` page's ▶ button) |

### Résumé / profile / settings
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/resume` | résumé text in copy blocks + extracted keywords + the derived role profile → `resume.html` |
| POST | `/resume/upload` | upload `.pdf/.txt/.md` (10 MB cap, `%PDF` magic check); writes `data/resume.txt` (+ `resume.pdf` + `.name`); reseeds profile |
| GET | `/resume.pdf` | serve the newest PDF in `data/` |
| GET/POST | `/profile` | view / save the PII fields used for autofill |
| POST | `/profile/from-resume` | fill only the *empty* fields from the résumé |
| GET | `/settings` | read-only view of `settings.yaml` + `companies.yaml` → `settings.html` |

### Emails (Gmail, read-only)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/emails` | stored job emails + connection state → `emails.html` |
| POST | `/emails/connect` | begin Gmail OAuth (mint CSRF `state`, redirect to consent) |
| GET | `/emails/oauth/callback` | OAuth return: validate state, exchange code, store token |
| POST | `/emails/sync` | pull recent job-relevant mail, link to applications, auto-advance applied→confirmed |

### Fit map
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/clusters` | 2-D scatter of all scored postings + your résumé, colored by cluster → `clusters.html` |
| GET | `/clusters/job/{job_id}` | per-job score breakdown (the `0.85·cosine + 0.15·cluster` split, overlapping keywords) → `cluster_job.html` |

### Companies / interview questions
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/companies` | company index with question + solved counts → `companies.html` |
| GET | `/companies/{company_key}` | one company's questions (difficulty filter, frequency bars, solve tracking) → `company.html` |
| POST | `/companies/{company_key}/refresh` | background pull of a larger frequency-ranked list from the GitHub CSV dataset |
| GET | `/api/companies/{company_key}/refresh-status` | poll refresh state (JS polls this) |
| POST | `/company-problems/{problem_id}/state` | mark a problem solved/attempted → 303 |

### Prep (interview curriculum)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/prep` | landing: track overview, "resume where you left off", company widget → `prep.html` |
| GET | `/prep/track/{slug}` | modules in a track → `prep_track.html` |
| GET | `/prep/module/{slug}` | lessons + LeetCode drills + CtCI problems → `prep_module.html` |
| GET | `/prep/module/{slug}/source` | the distilled book chapter for the module → `prep_source.html` |
| GET | `/prep/book/{book_key}` | serve a book PDF inline (if present locally) |
| GET | `/prep/module/{slug}/lesson/{lesson_slug}` | a lesson (auto-marks `not_started`→`in_progress`) → `prep_lesson.html` |
| GET | `/prep/module/{slug}/ctci/{problem_slug}` | a CtCI problem (auto-marks →`attempted`) → `prep_problem.html` |
| POST | `/prep/lessons/{id}/state`, `/prep/problems/{id}/state`, `/prep/ctci-problems/{id}/state` | save progress + notes → 303 |

### Referrals
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/jobs/{job_id}/referrals` | LinkedIn candidates for the job, ranked by fit → `referrals.html` |
| POST | `/jobs/{job_id}/referrals/discover` | background LinkedIn people-search (headed Chromium) |

## The data model (`webapp/db.py`)

SQLite at `data/jobsearch.db` is the web app's **entire** persistent world. Key
tables (every state column noted):

**Job tracking**
- `jobs` — one row per posting, keyed by `key` (UNIQUE). Mirrors the pipeline's
  `JobPosting` plus `first_seen_at` (exact insertion time), `last_seen_at`,
  `is_active`.
- `job_events` — append-only audit (`inserted/updated/...` + a JSON field diff).
- `applications` — one per job (`job_id` UNIQUE), `status` default `not_applied`.
- `application_events` — append-only status history.
- `runs` — one row per ingest (counts + report date).

**Your data**
- `profile_fields` — the PII store (`field` UNIQUE → value).
- `email_accounts`, `email_messages` — Gmail connection + stored job-relevant mail
  (append-only; bodies stored in plaintext locally).

**Prep** — `prep_tracks/modules/lessons/problems/ctci_problems` (content, rebuilt
from code) + separate `prep_*_progress` tables (your state, keyed by row id) +
`prep_meta` (content hash). **Company questions** — `company_problems` +
`company_problem_progress` + `company_refresh_runs`. **Referrals** —
`referral_candidates` (global per LinkedIn URL) + `referral_matches`
(per candidate×job score) + `referral_runs`.

**The application lifecycle.** `APP_STATUSES = not_applied, in_progress, applied,
confirmed, interviewing, offer, rejected, withdrawn`. Transitions are **not
enforced** — the human is in charge. The dashboard's three "stacks" are views over
`status`: *to-apply* (not engaged), *in-progress* (autofill underway), *applied*
(anything from applied onward). Status changes come from the per-row dropdown, the
bulk bar, the job-detail form, the apply browser's confirmation detection, or a
Gmail confirmation email. **History is append-only** — nothing is silently
overwritten.

`upsert_job` (called by ingest) inserts or patches only changed fields, records a
diff, creates the `applications` row, and never erases a stored non-empty value
with an empty one. Re-ingesting the same report is a no-op.

## Ingest (`webapp/ingest.py`) and the "leftovers" behavior

`ingest_latest` reads `reports/latest.json`, joins descriptions from the newest
`data/corpus/*.jsonl.gz`, and upserts every job + near-miss by `key`. It then
counts **stale** to-apply jobs — `not_applied` rows absent from the current report,
i.e. carried over from earlier runs — and logs a "N unapplied jobs from earlier
runs" note. This is the mechanism behind the dashboard's accumulation: jobs are
never deleted on re-ingest, so a differently-targeted earlier run leaves residue.
`run_scope=latest` (the default) hides that residue from the to-apply stack
without losing anything you've engaged with.

## The apply browser (`webapp/apply_browser.py`, `autofill.py`, `ats.py`)

The single most intricate part of the web app. Goal: open a posting and fill its
form from your profile, in a real browser you can watch and take over — and
**never click submit**.

**Runtime model.** `SessionRegistry` (held by the app) owns one `BrowserHost`
daemon thread, which owns the *only* Playwright instance. It launches **one
persistent, headed Chromium** (`launch_persistent_context`, `headless=False`, a
`data/browser_profile/` user-data-dir so ATS logins survive). Every "apply" opens
a **new tab in that same window** (`ApplySession` per tab). The host runs a 0.5s
poll loop: drain newly-requested tabs, tick each live tab, GC the context when the
last tab closes. Web requests enqueue work; only the host thread touches pages.

**The fill cycle (`_on_settle`).** When a tab's page settles, the host: detects a
Cloudflare challenge (and asks you to solve it in the tab); checks for a
confirmation page (→ submission detected, below); waits for hydration; then runs
`autofill.run_fill`. If almost nothing was fillable, it tries to hoist a
cross-origin ATS iframe to top-level or click an "Apply" button to reach the form,
then re-ticks. It re-fills the same URL across multiple passes until the fillable
count is stable (React SPAs and multi-step ATS flows hydrate progressively).

**Submission detection — "never submits, but knows when you did."** The engine
infers success conservatively by watching the page you land on:
`looks_like_confirmation` matches confirmation-ish URLs (`thank-you`,
`application-submitted`, …) or body text ("we've received your application"). On a
hit it sets the application to `applied`. A false positive is considered worse than
asking you to confirm, so the bar is deliberately high.

**The autofill engine (`autofill.py`).** Cleanly split: `plan()` is pure logic
over field-descriptor dicts (heavily unit-tested offline), `run_fill()` is the thin
Playwright layer. A JS pass collects every visible control across **all frames**
(Greenhouse embeds its form in an iframe), including ARIA comboboxes (custom
dropdowns), tagging each with a handle and discovering its label/question/etc.
`plan()` then matches all controls at once against your profile:

- Formats values (name split, `(NNN) NNN-NNNN` phone, US state expansion, `$`
  salary, `https://` URLs).
- Answers yes/no screeners it is confident about (work authorization, sponsorship,
  age ≥ 18); leaves unknown ones for you.
- **Deliberately skips and reports**: EEO/demographic self-ID, cover letters, GPA,
  and anything without a confident answer — so your review pass knows exactly
  what's left. It never guesses a self-identification answer; if you've set a
  decline value it selects the decline option.
- Resume upload re-attaches `data/resume.pdf` under your original filename.

`ats.py` adds platform-specific knowledge used only on the apply leg (distinct
from `jobsearch/fetchers`, which is the *discovery* leg): canonicalizing a posting
URL to the page that actually renders the form (Greenhouse `/embed/job_app`, Ashby
`/application`, Lever `/apply`), detecting Cloudflare, hoisting ATS iframes, and
fetching Greenhouse's `?questions=true` schema for exact dropdown answers.

**The "never clicks submit" guarantee** holds because the executor only
fills/selects/checks/uploads, and the one button-clicking helper
(`click_apply_button`) excludes anything `type="submit"` and only ever runs to
*reach* a form, never when one is present.

## Gmail (`webapp/gmail.py`, `emailmod.py`)

Read-only (`gmail.readonly` scope), with **zero new dependencies** — the OAuth
exchange and Gmail REST calls are plain `requests`. You drop a Google OAuth
desktop-client `data/credentials.json`, click Connect, and the loopback OAuth flow
(redirect URI = the running UI's `/emails/oauth/callback`, CSRF-protected by a
single-use `state`) stores a token at `data/token.json` (chmod 600, refresh token
preserved). Sync builds a server-side query **from your own applications** (`from:`
your applied companies + known ATS sender domains, `newer_than:Nd`) — nothing
outside that filter is ever fetched. Each message is classified
(`confirmation/interview/rejection/offer`), linked to an application by company-
token matching, and stored. A confirmation email auto-advances the application
`applied`/`in_progress` → `confirmed` (`emailmod.store_message`).

## Prep, company questions, referrals (webapp glue)

All three follow one house pattern: **authored/curated data → idempotent
hash-gated seed into SQLite on startup → progress tracked by stable row id →
optional live refresh that degrades gracefully offline.**

- **Prep** — `jobsearch/prep/` holds ~6,700 lines of authored curriculum across 3
  tracks (Coding/CtCI, System Design, Distributed Systems/DDIA) assembled at
  import time into `ALL_TRACKS`; `prep/seed.py::seed_into_db` upserts it by natural
  key (so progress survives reseeds) and prunes vanished rows. Lesson bodies render
  through `textfmt.prep_markdown` (a dependency-free Markdown subset); the
  "open source chapter" feature (`prep_render.py`/`prep_sources.py`) cleans raw
  book-text dumps into Markdown — only when you've placed the (gitignored) books.
- **Company questions** — `company_questions/seed_data.py` is a hand-ranked
  offline set for 13 big employers (frequency synthesized from rank); the
  "⟳ Refresh" button (`refresh.py`) pulls a larger frequency-measured list from a
  community GitHub CSV dataset, tolerant of column layouts, and falls back to the
  bundled set on any network failure. Surfaced both on `/companies` and inline on
  every job-detail page.
- **Referrals** — `referrals/discover.py` runs a headed-Chromium LinkedIn People
  Search (de-leveling the job title so it ranks subject-matter experts),
  `rank.py` scores candidates by job-fit + your-background-fit in one shared
  TF-IDF space, `store.py` persists. The browser profile persists your LinkedIn
  login so you sign in once. **This is the highest-risk feature** — see
  [`limitations.md`](limitations.md).

## Frontend (`webapp/static/`)

`app.js` is vanilla JS, all progressive enhancement: copy-to-clipboard, the
apply/refill/apply-all/prepare-top buttons (which POST then poll the `/api/apply*`
status endpoints every ~1.5s), bulk-select, per-row status changes, the run-log
streamer (polls `/run/log`), a light/dark theme toggle, and the hand-built SVG
Fit-map scatter (`#cluster-map-data` → circles per cluster, the résumé as a ★,
click-through to per-job breakdowns). `app.css` is "Aurora," a dependency-free
Apple-HIG-inspired theme with full light/dark via CSS custom properties.

## Two run mechanisms (a wart worth knowing)

The pipeline can be triggered two different ways from the UI: `/run` uses the
**subprocess** `PipelineRunner` (isolated, streamed, single-flight) and `/resume/run`
runs `pipeline.run` **in-process** in a thread. They have independent "already
running" guards and don't know about each other. See
[`refactoring.md`](refactoring.md).
