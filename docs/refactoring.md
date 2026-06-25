# Refactoring recommendations

> Prioritized, concrete suggestions to make the codebase easier to understand and
> maintain. These are *proposals*, not applied changes — the repo is healthy
> (good docstrings, ~257 offline tests, sensible module boundaries), so this is
> about paying down specific debt, not a rewrite. Ordered by value-to-effort.
> Each item cites the relevant code so it can be picked up directly.

## Tier 1 — high value, low risk

### 1.1 Collapse the duplicated browser-board fetchers
`goldman.py`, `jpmorgan.py`, `millennium.py`, `tiktok.py`, `janestreet.py` are
near-identical: a module-local set of `TITLE_KEYS`/`ID_KEYS`/`LOCATION_KEYS`/… key
tuples, a one-line `_looks_like_job` predicate, a `parse_payloads` loop over
`walk_collect`, and a fall-through to `_generic.fallback_jobs`. This is ~5 copies
of the same algorithm with a different key map.

**Proposal:** a single parametrized helper —
`browser_board_fetch(company, runtime, *, url_pattern, key_map, link_fmt, source)`
— that does the harvest → precise-parse → generic-fallback → `debug_summary`
dance once. The five modules shrink to a registry of `(url_pattern, key_map,
link_fmt)` per site. Consolidate the key-alias vocabulary with `_generic`'s
`TITLE_KEYS`/`ID_KEYS`/… so more sites can use `_generic` directly (it's why
`goldman` has to re-run over `harvest["extra"]` for `roleTitle`/`division`).

### 1.2 Make empty-result handling uniform across fetchers
Half the fetchers raise on zero postings (good — visible in the report); the other
half (`amazon`, `uber`, `spotify`, `eightfold`, `workday`, `microsoft`) silently
return `[]`, which hides a moved endpoint. **Proposal:** a shared
`require_nonempty(jobs, company, diagnostic)` that every fetcher calls before
returning, so "no jobs" vs "board broke" is always distinguishable in the funnel.

### 1.3 De-duplicate the "idempotent hash-gated seed" pattern
`prep/seed.py::seed_into_db` and `webapp/company_questions.py::seed_bundled` both
implement: hash the content, short-circuit if unchanged, upsert by natural key,
prune vanished rows, stamp `prep_meta`. **Proposal:** one
`seed_with_hash(conn, meta_key, records, upsert_fn, prune_fn)` helper. Same for the
**background-run + polling** machinery, reimplemented for both `referral_runs` and
`company_refresh_runs` — extract a small `RunTracker` (start/finish/fail/latest/
is_running over a `*_runs` table).

### 1.4 Consolidate shared helpers that were copy-pasted
- Two `utcnow`/`_utcnow`: `referrals/store.py` defines its own instead of importing
  `webapp.db.utcnow` (which `prep/seed.py` already reuses).
- Two LeetCode-URL builders: `prep/coding.py::_p` and
  `company_questions/__init__.py::leetcode_url`.
- Two identical asset regexes: `discover.py` and `browser.py`.
- `discover.probe_slugs` builds a bare `requests.Session()`, bypassing
  `make_session`'s retries/UA — route it through `make_session`.

### 1.5 Fix the dependency/doc drift
- Delete or regenerate `Pipfile`/`Pipfile.lock` (pins Python 3.14, omits `pypdf`);
  `requirements.txt` is the source of truth. Pick one Python version across
  `Pipfile`, CI (3.11), and `setup.sh`.
- Update `SKILL.md` and `design-validation-loop.md` to reference the
  `.claude/skills/validate-jobs/` **skill**, not the removed
  `.claude/commands/validate-jobs.md`.

## Tier 2 — clarity & correctness

### 2.1 Unify the two pipeline-run mechanisms
`/run` runs the pipeline as a subprocess (isolated, streamed); `/resume/run` runs
it in-process in a thread. They have separate guards and can run concurrently, and
the in-process path defeats the isolation the subprocess runner exists to provide.
**Proposal:** route `/resume/run` through the same `PipelineRunner`, giving one
run mechanism with one single-flight guard.

### 2.2 Centralize scoring constants and the TF-IDF setup
- `scoring.py` derives `cosine_weight = 1 - cluster_weight` but also keeps a
  separate `COSINE_WEIGHT = 0.85` constant that is effectively vestigial — a future
  edit to it would be a silent no-op. Pick one source of truth.
- The `TfidfVectorizer` is configured in three places with slightly different
  params (`scoring.score_jobs`, `role_profile._vectorize_match_tfidf`,
  `company_discovery.rank_leads`). A shared `make_vectorizer(...)` factory prevents
  drift. The three anti-skew mechanisms (`strip_company_boilerplate`,
  `_company_name_re` masking, the `EXTRA_STOP_WORDS` stoplist) also overlap — at
  least centralize `EXTRA_STOP_WORDS` (already imported across modules) and
  document the division of labor.

### 2.3 Turn `filters.classify` into a rules table
The classify decision tree is a long nested branch with subtle precedence
(HARD_EXCLUDE vs exclude-pattern vs seniority) and reason codes that are easy to
mis-bucket. A small ordered list of `(predicate, status, reason)` rules would be
more readable, more testable, and would make the reason codes self-documenting.
The filter is already well unit-tested, so this can be done safely.

### 2.4 Add a DB migration step
Replace the implicit `CREATE TABLE IF NOT EXISTS`-only schema with a tiny
versioned migration runner (a `schema_version` in `prep_meta` and an ordered list
of `ALTER`/`CREATE` steps). This removes the "old DB silently lacks new columns"
foot-gun and lets `PATCHABLE`/`SORTABLE` be derived from, or checked against, the
live schema.

### 2.5 Make ingest deactivate stale jobs (fix accumulation properly)
The schema already has `is_active` and `deactivated` events, but ingest never sets
them. Marking jobs absent from the newest report `is_active = 0` (rather than
relying on `run_scope=latest` to hide them) would fix the accumulation wart at the
source while preserving history.

## Tier 3 — larger / longer-horizon

### 3.1 Move the prep curriculum out of Python literals
`coding.py`/`system_design.py`/`distributed_systems.py`/`ctci_extra_modules.py`
are ~6,700 lines of authored content as giant string literals — painful to review
and edit. The system-design and distributed tracks' docstrings already imply a
`data/prep_sources/_build.py` JSON pipeline; finish that migration so all tracks
load from data files (JSON/Markdown), shrinking the modules to loaders. This also
isolates the **copyright-exposure** question (substantial verbatim book quoting)
to a clearly-local, gitignored content set.

### 3.2 Thread `search.locations` into the fetchers
Many fetchers hard-code "New York" server-side, so the tool is effectively
NYC-only on the fetch side even though discovery and role-targeting are
location-general. Pass the configured locations down so retargeting a city is as
easy as retargeting a role.

### 3.3 Harden the offline-test guarantee
Add a `conftest.py` with a socket-blocking fixture (or a `network` marker) so the
"fully offline" property is enforced, not just observed. Consider a thin
Playwright smoke test (against a local fixture HTML) so the autofill *executor*,
not just `plan()`, has some coverage.

### 3.4 Reduce blanket `except Exception` in the apply/referral browser code
The broad catches are deliberate (pages and DOMs vanish), but they hide real
failures behind stderr prints. Narrow them where the failure mode is known, and
route the rest through a single "degrade and record" helper that writes a visible
note (to the session detail / run row) instead of only stderr.

## What *not* to change

- The two-program split (pipeline vs web app) and the file-based contract between
  them are a strength — they keep the daily batch job and the long-lived server
  independent. Keep it.
- The "a broken board never sinks the run" philosophy and the human-in-the-loop
  boundaries (never auto-submit, read-only Gmail, manual LinkedIn login) are core
  to the design — refactors should preserve them, not optimize them away.
- Fitting TF-IDF/K-means on the **whole corpus** (not the survivors) is a
  deliberate, documented fix for scoring skew — don't "simplify" it back.
