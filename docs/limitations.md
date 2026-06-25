# Limitations & known issues

> An honest, consolidated account of what this repo does *not* do well, where it
> is fragile, and what to watch for — gathered from across both subsystems.
> Refactoring proposals that address many of these are in
> [`refactoring.md`](refactoring.md). Several items are also documented in the
> `analysis-*.md` design docs.

## Scope & design constraints (by intent)

- **Single-user, local-first, unauthenticated.** The web app has no login, no
  CSRF protection on form POSTs (only the Gmail OAuth `state`), and no
  authorization. It is meant for `127.0.0.1` only and refuses non-loopback hosts
  without `--allow-remote`. Anyone who can reach the port has full read/write and
  can drive your browser. Multi-user hosting would require the changes in
  `design-hosting.md`.
- **NYC / senior-SWE heritage.** The defaults target senior software roles in
  NYC. Role *targeting* makes the **role** dynamic (any occupation in
  `occupations.yaml`), but the **location** is still NYC-centric: many fetchers
  hard-code "New York" server-side, and some report/validation copy still says
  "NYC senior-SWE." Retargeting location means editing `search.locations` and is
  not as automatic as role retargeting.
- **The repo doubles as a datastore.** GitHub Actions commits the daily report
  and `data/seen_jobs.tsv` back to the branch. History grows unbounded, and a
  rebase conflict on those files would fail the job *after* the search ran.

## Data acquisition (the most fragile layer)

- **Undocumented APIs break without notice.** The company-specific fetchers
  (Meta's GraphQL `doc_id`, Apple's CSRF flow, Google's already-dead `api/v3`,
  Amazon/Uber/Spotify internal endpoints) depend on private contracts that change.
  Browser fallbacks mitigate this but are themselves brittle (they depend on the
  frontend's XHR shape). Expect to prune/fix boards periodically;
  `python -m jobsearch verify` and the report's "needs attention" section are how
  you find them.
- **Inconsistent empty-result handling.** Greenhouse/Lever/Ashby/SmartRecruiters/
  Google/Meta/Apple/Bloomberg raise on zero postings (→ visible in the report);
  but **Amazon, Uber, Spotify, Eightfold, Workday, Microsoft silently return
  `[]`**. For those high-volume boards, "endpoint moved" looks identical to "no
  jobs today," and three of them have no browser fallback.
- **ATS slugs rot.** Companies migrate ATS vendors; `companies.yaml` slugs are
  best-effort. The sandbox the project was authored in couldn't reach job-board
  domains, so the registry has never had a full real-world shakeout — expect to
  prune several on the first real run.
- **Bot-detection exposure.** Evasion is minimal (one shared User-Agent, a
  `navigator.webdriver` spoof, consent-banner dismissal). There is no proxy
  rotation, per-host throttle, jitter, or `Retry-After` honoring. Discovery's
  slug-probing fires many unauthenticated requests at public ATS APIs and could
  draw IP blocks at scale.
- **`make_session`'s timeout is a non-enforced shim.** It is honored only when a
  fetcher routes through `get_json`/`post_json`; the few that call
  `session.get/post` directly (apple/meta/uber) pass their own literal timeout, so
  the configured `fetch.timeout_seconds` is ignored on those paths.

## Scoring & ranking caveats

- **Fit scores are relative, never absolute.** They are scaled so the day's best
  posting is 100 — a uniformly weak day still produces a 100. The ordering is
  meaningful; the magnitude is not. The only guard against a misleading top is the
  report's skew warning when one company dominates.
- **Small corpora degrade gracefully but differently.** Below 6 fetched postings
  there is 1 cluster and no 2-D Fit-map; cluster-affinity even *changes meaning*
  (centroid cosine when >1 cluster, corpus-mean cosine when ==1), so the 0.15 term
  is not strictly comparable across run sizes.
- **Regex filtering is brittle.** Title/seniority/pay decisions are regex over
  free text. The "5+ years" detector misses "5+ yrs" or "half a decade"; pay
  parsing only understands `$`-prefixed USD in a fixed band (misses €/£, "150–180k"
  without `$`, hourly rates). `classify` is a long nested branch whose reason codes
  hinge on description-regex hits and are easy to mis-bucket.

## Web app & data model

- **No DB migrations.** `connect()` is `CREATE TABLE IF NOT EXISTS` only. Adding a
  *column* to an existing table has no upgrade path (only `profile.ensure_fields`
  tops up profile *rows*); an old `data/jobsearch.db` silently lacks new columns
  until rebuilt. The hand-maintained `PATCHABLE`/`SORTABLE` column lists can drift
  from the schema.
- **The dashboard accumulates.** Ingest never deletes jobs absent from a new
  report, so leftovers from earlier (differently-targeted) runs pile up in
  to-apply. This is worked *around* with `run_scope=latest` + a warning banner,
  not fixed — the `is_active`/`deactivated` machinery exists in the schema but
  ingest never sets it.
- **Two parallel pipeline-run mechanisms.** `/run` (subprocess) and `/resume/run`
  (in-process thread) have independent "already running" guards and can both run a
  pipeline at once; the in-process path contradicts the very isolation rationale
  the subprocess runner was built for.
- **One shared SQLite connection across request threads** (`check_same_thread=
  False`, WAL). Background workers correctly open their own connections, but
  concurrent writes rely on SQLite's locking and can contend.
- **Broad exception swallowing.** Many handlers `except Exception: pass`. Robust
  against 500s, but real failures (a bad state write, an OAuth/sync error) can
  silently no-op and just redirect.
- **`GET /run/log` has a side effect** — it triggers ingest on the first clean-
  finish poll. Convenient, but surprising for a "log" endpoint.

## Apply automation & autofill

- **Heuristic field matching is inherently flaky.** Odd or unlabeled fields fall
  through to a (reported) skip; the combobox path depends on the ATS's rendered
  menu and typeahead behavior and silently degrades to "pick it yourself" on
  unfamiliar widgets. Only Greenhouse gets schema-accurate dropdown answers.
- **Location parsing is US-only** (state abbreviations); non-US locations produce
  odd values.
- **Playwright fragility.** The whole apply subsystem leans on broad
  `except Exception`, which swallows real errors — debugging a misfill means
  reading stderr, not exceptions. The multi-pass hydration loop is a timing
  heuristic that a very slow or very dynamic page can exhaust.
- **Captcha/anti-automation.** Cloudflare is handled by pausing and asking you to
  solve it (the right call), but other defenses aren't addressed beyond using a
  real, headed, persistent-profile browser.

## Email (Gmail)

- **Setup friction is the cost of zero dependencies.** You must create a GCP
  project, enable the Gmail API, make a Desktop OAuth client, and place
  `credentials.json` before anything works. Token refresh assumes Google issued a
  refresh token; behind an HTTPS proxy the computed loopback redirect URI must
  exactly match what's registered.
- **Email bodies are stored in plaintext** in the local SQLite DB (filesystem
  permissions are the only protection). Matching emails to applications is a
  company-token heuristic that can both over- and under-link.

## Referrals (highest risk)

- **LinkedIn automation violates LinkedIn's ToS and risks account bans.** The code
  is careful (headed, manual login, randomized pacing, never auto-authenticates),
  but the risk is real and acknowledged in the code's own comments. Use a
  secondary login if that matters to you.
- **Heuristic DOM scraping** anchored on profile links survives class-name churn
  but will silently return empty/garbled results on a major redesign — and
  failures are swallowed, so breakage looks like "no candidates," not an error.
- Profile enrichment (current role/company/summary) is only weakly populated;
  `referral_candidates.summary` is currently always empty.

## Prep content

- **~6,700 lines of hand-authored curriculum** distilled from copyrighted books
  (CtCI, DDIA, System Design Interview), stored as giant Python string literals.
  This is expensive to maintain, hard to review, can't be regenerated without the
  source books, and carries **copyright exposure** from substantial verbatim
  quoting. The CtCI book-problems feature is invisible on any checkout lacking the
  (gitignored) extracted JSON, with no UI hint as to why.
- **Company-question frequencies are synthesized from rank**, not measured, until
  a live refresh overlays real numbers. The refresh hard-codes one community GitHub
  repo; if it moves or goes stale, refresh silently falls back to bundled data with
  no freshness indicator.

## Testing & environment

- **Tests are fully offline — but only by convention.** ~257 tests, no live
  network or browser, yet there is no `conftest.py`/socket guard enforcing it; a
  future test could make a live call. The Playwright *executor* (actual DOM
  typing/clicking) is not exercised in CI — only the pure `plan()` logic is.
- **Dependency drift.** `Pipfile` pins Python 3.14 and **omits `pypdf`**, while CI
  uses 3.11 and `setup.sh` uses system `python3`. `requirements.txt` is the source
  of truth; the `Pipfile` is stale.
- **Doc drift.** `SKILL.md` and `design-validation-loop.md` reference a
  `.claude/commands/validate-jobs.md` that no longer exists (the feature ships as a
  skill now).
