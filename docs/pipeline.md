# The pipeline — deep dive

> Half 1 of the system: the `jobsearch/` package, run as a CLI. This document
> walks `python -m jobsearch run` stage by stage with the actual code paths, then
> covers the fetch layer, the scoring math, the filter logic, the discovery
> commands, and the report artifacts. High-level context is in
> [`architecture.md`](architecture.md).

## Entry point and commands

`jobsearch/__main__.py` is a thin `argparse` dispatcher. All real work is in the
submodules it lazily imports.

| Command | Does | Code |
|---------|------|------|
| `run` | the full daily pipeline → `reports/*` | `pipeline.run(root)` |
| `verify` | fetch every board once, print reachable vs failed | `pipeline.verify(root)` |
| `discover "<company>" [--url]` | auto-detect one company's ATS board slug, print a paste-ready `companies.yaml` stanza | `discover.discover(...)` |
| `discover-companies [--limit N] [--dry-run]` | mine generalized boards for companies matching your résumé, write `data/companies.discovered.yaml` | `company_discovery.discover_companies(...)` |
| `ingest` | pull `reports/latest.json` into `data/jobsearch.db` | `webapp.ingest.ingest_latest(...)` |
| `ui [--host --port --allow-remote]` | start the web app (refuses non-loopback host without `--allow-remote`) | `webapp.app.create_app` + `uvicorn` |

`--root` defaults to the repo root and locates `config/`, `data/`, `reports/`.

## The `run` spine, stage by stage

Everything below is `jobsearch/pipeline.py::run`. The stages are sequential; the
only concurrency is inside stage 4.

### 1. Config + registry (`config.py`)

`load_settings` reads `config/settings.yaml` and fills in section defaults.
`load_registry` reads `config/companies.yaml` into `[Company]` and, if
`data/companies.discovered.yaml` exists, merges it **under** the curated file:
deduped by `utils.normalize_company_name`, curated entries win, and any name in
`discovery.exclude_companies` is dropped even if a stale generated file lists it.
`manual_check` entries (boards with no scrapable API) are carried separately and
only surface in the report.

`Company` (`models.py`): `name, ats, tags, careers_url, enabled, params`. The
`ats` string is the key into the fetcher registries; everything in `params`
(e.g. `board`, `org`, `tenant`, `fallback`) is fetcher-specific.

### 2. Résumé (`resume.py`)

`load_resume_text` returns `(text, is_sample)`: the configured `data/resume.txt`
if present, else the bundled `data/sample_resume.txt` with `is_sample=True` (and
a stderr nudge to upload your own). `resume.py` also provides `pdf_to_text`
(via `pypdf`, raises if it extracts < 100 chars — likely a scanned image) and
`extract_keywords` (used on the `/resume` page to sanity-check extraction).

### 3. Role targeting (`role_profile.py`)

This is what makes the tool work for non-engineering résumés. `resolve_profile`:

- Returns `None` (→ keep the manual `settings.yaml` filters) when
  `role_targeting: manual`, when `occupations.yaml` is missing/empty, **or when
  the best match scores below `search.role_match_min_score`** (default 0.02 — a
  guard against garbled résumés).
- Otherwise matches the résumé against every `Occupation.document()` (its name +
  doubled titles + doubled skills) by cosine similarity. Backend is `auto`: it
  uses the **MiniLM** sentence-transformer if installed, else **TF-IDF**
  (`_load_minilm` returns `None` on any import/model error, so CI and offline
  installs silently fall back).
- Builds a `RoleProfile` (`occupations, query, title_include, title_exclude,
  skills, categories, seniority, matched_via, scores`). A runner-up occupation
  scoring ≥ 85% of the top is blended in (e.g. a résumé straddling Customer
  Success + Project Management). `infer_seniority` scans for year-counts and
  level words to decide whether generated exclude filters drop *junior* titles
  (senior résumé) or *management* titles (junior résumé, unless the occupation
  is flagged `manage: true`).

`apply_profile` returns a copy of `settings["search"]` with `query`,
`title_include`, `title_exclude` **replaced** by the profile's. Location and
remote-pay knobs are deliberately left alone — *the profile decides the role,
settings decide the place*. The profile is written to `data/role_profile.json`
for the UI/report, and a `targeting` dict flows into the run log.

`occupations.yaml` schema (per entry): `name`, `soc` (O*NET code, reference
only), `manage` (bool), `titles` (→ generated includes, levels stripped), `query`
(server-side search term), `skills` (the bulk of the match signal), `categories`
(Muse categories for discovery).

### 4. Fetch all boards (`pipeline.fetch_all`, `fetchers/`, `http.py`, `browser.py`)

Two passes:

**API pass (concurrent).** Companies whose `ats` is in `FETCHERS` are fetched in
a `ThreadPoolExecutor` (`fetch.max_workers`, default 8). Each task builds its own
`requests.Session` via `http.make_session` (retries on 429/5xx with backoff, a
desktop User-Agent, `Accept: application/json`). A fetcher that raises is caught:
if its `params["fallback"]` names a browser fetcher, the company is queued for
the browser pass carrying the primary error; otherwise it becomes a `FetchError`.

**Browser pass (sequential).** Companies whose `ats` is in `BROWSER_FETCHERS`
(plus any API fallbacks) are scraped inside **one shared** `BrowserRuntime`
(headless Chromium). If Chromium is unavailable, every queued company gets an
actionable `FetchError` and the run continues.

#### The fetcher contract

```python
# API fetcher — registered in fetchers.FETCHERS  (ats key e.g. "greenhouse")
def fetch(company: Company, session: requests.Session, settings: dict) -> list[JobPosting]

# Browser fetcher — registered in fetchers.BROWSER_FETCHERS  (ats key e.g. "browser_goldman")
def fetch(company: Company, runtime: BrowserRuntime, settings: dict) -> list[JobPosting]
```

Both return a `list[JobPosting]` and **raise on failure** (an empty result is a
`RuntimeError` with a diagnostic). One module can register both (e.g. `meta.fetch`
→ `FETCHERS["meta"]` and `meta.fetch_browser` → `BROWSER_FETCHERS["browser_meta"]`).

#### Fetcher families

- **Public JSON board dumps** — `greenhouse`, `lever`, `ashby`,
  `smartrecruiters`. One GET returns *all* postings; filtering is entirely local;
  capped at `fetch.max_per_company` (1500). SmartRecruiters additionally fetches
  per-posting detail (capped by `fetch.max_detail_requests`, 40), and only for
  jobs that already pass the title/location filter.
- **Paginated query APIs** — `workday`, `eightfold`. Pass the search query
  server-side and page through results. Workday has no location facet by default,
  so it appends a location term to `searchText` (popular tenants otherwise
  exhaust the page budget on non-NYC rows); its dates are relative strings parsed
  by `utils.parse_workday_posted_on`.
- **Company-specific APIs** — `amazon`, `google`, `apple`, `meta`, `microsoft`,
  `bloomberg`, `uber`, `spotify`, `tiktok`. Each wraps one undocumented endpoint.
  Several need special handling: Apple does a CSRF priming GET; Meta posts a
  GraphQL query with a hard-coded `doc_id` and strips Facebook's `for(;;);` XSSI
  prefix; Google's `api/v3` is already dead and only the browser path works.
  `apple`, `google`, `meta`, `microsoft`, `bloomberg`, `eightfold` carry browser
  fallbacks.
- **Browser-only finance boards** — `goldman`, `jpmorgan`, `millennium`,
  `janestreet`, `deshaw`. No usable API; scraped via the harvesting runtime.

#### The browser runtime (`browser.py`) — the durable-scraping core

`BrowserRuntime` owns one headless Chromium for the whole run (with light
bot-evasion: a real User-Agent, `navigator.webdriver` spoofed away). Its key
method is **`harvest(url, url_pattern)`**, which is far more durable than CSS
selectors because it captures the *data the page's own frontend fetches*:

1. Navigate, registering a listener that buffers every network response.
2. Dismiss cookie-consent walls (OneTrust/TrustArc selectors) — banks block the
   jobs XHR until you do — and scroll a few times to trigger lazy loading.
3. Wait for network idle (tolerantly — busy pages never settle).
4. Bucket responses into `matched` (URL matches the pattern) vs `extra` (any
   other JSON).
5. Extract JSON embedded in the final DOM: SPA state globals (`__NEXT_DATA__`
   etc.), **Phenom's `window.phApp.ddo`** (how careers.jpmorgan.com and mlp.com
   embed page-1 results without an XHR), and schema.org **JobPosting JSON-LD**.

It retries with a longer settle window if nothing job-shaped came back. The
generic extractor `fetchers/_generic.py::fallback_jobs` then walks all harvested
JSON (`utils.walk_collect`) for JobPosting-shaped records — JSON-LD first, then
duck-typed records — so a site fetcher's precise key-map can fall back to "find
anything that looks like a job." Every "no records" error embeds a
`debug_summary` (final URL, response counts, sample URLs) so the report carries
enough signal to fix the board.

`JobPosting` (`models.py`) is the canonical record. Fetchers populate
`company, title, location, url, job_id, description, posted_at, source`; the rest
(`fit_score, rank_score, cluster, is_new, filter_reason, validation`) are filled
downstream. Identity is `key = "{source}:{company}:{job_id}"`.

### 5. Dedupe + corpus snapshot

`dedupe` drops repeats by `key`. `corpus.write_snapshot` writes the full fetched
corpus (post-dedupe, **pre-filter**) to `data/corpus/<date>.jsonl.gz`
(gzip JSON-Lines, 14-day retention) so scoring changes can be replayed offline
against real data, and so `ingest` can recover descriptions that `latest.json`
omits.

### 6. Filter (`filters.py`)

`JobFilter.classify(job)` returns `(status, reason)`:

- **`MATCH`** — title passes *and* location passes (or a remote carve-out fires).
- **`NEAR_TITLE`** — a location-acceptable engineering role that failed the title
  filter (reason codes: `EXCLUDED_TRACK:<word>`, `UNLEVELED_TITLE`, `MID_LEVEL`,
  `OTHER_ENG_TRACK`, …).
- **`NEAR_LOCATION`** — title passed but the role is US-remote (reason codes:
  `REMOTE_PAY_BELOW_MIN`, `REMOTE_NO_PAY_RANGE`, `REMOTE_ONLY`).
- **`OUT`** — not shown.

Title matching is case-insensitive regex: a title must hit one `title_include`
and no `title_exclude`. Location matching is substring against `search.locations`.
Two policy carve-outs (decided 2026-06-12, see `improvement-plan.md`):

- **Remote pay floor** — a US-remote role enters the main table only if its
  posted pay range tops out ≥ `search.remote_min_pay` (default $200k);
  `filters.extract_max_pay` parses `$NNN,NNN` / `$NNN.NK` forms in a sane band.
- **Unleveled-title promotion** — a software title with no level (Stripe, OpenAI,
  Jane Street post these) is promoted to `MATCH` when the description requires 5+
  years and the title looks software-ish (`promote_unleveled: true`).

`build_funnel` produces the per-company `fetched / title✓ / loc✓ / matched /
near_miss / aged_out` counters shown in the report. It is **age-aware**: postings
older than `ranking.max_age_days` (default 45) land in `aged_out` rather than
inflating matched, so the funnel agrees with what the report can actually show.
After classification the pipeline also hard-drops matched/near-miss jobs older
than `max_age_days`.

### 7. Score by fit (`scoring.py`)

The heart of the ranking. `score_jobs(resume_text, jobs+near_miss, clusters,
corpus=all_jobs, cluster_weight, return_topics=True, return_explanation=True)`:

1. **Vectorize.** A `TfidfVectorizer` (unigrams+bigrams, sublinear TF, English +
   an `EXTRA_STOP_WORDS` stoplist of compensation/EEO boilerplate, corpus-size-
   aware `min_df`) is fit on the **whole fetched corpus**, not the survivors.
   Company-authored boilerplate is stripped first (`strip_company_boilerplate`
   removes sentences shared across ≥60% of a company's postings) and each
   company's own name is masked out of its postings, so a company can't cluster
   on its marketing copy. Vectors are L2-normalized so a dot product *is* cosine.
2. **Cluster.** K-means with `pick_cluster_count` (`"auto"` → ~1 cluster per 150
   corpus postings, clamped to 2–20; 1 cluster below 6 docs). The résumé is
   projected into the same space; **cluster affinity** is the cosine of the
   résumé to each centroid.
3. **Score.** For each job:
   `raw = 0.85·cosine(résumé) + 0.15·cluster_affinity[its cluster]`, then scaled
   so the day's max raw → `fit_score = 100`. (The 0.85 is `1 − cluster_weight`.)
4. **Explain.** With `return_explanation`, it emits the exact same vectors as a
   `clustering` object: a 2-D TruncatedSVD projection of every scored posting +
   the résumé + centroids, per-cluster topic terms and résumé affinity, and a
   per-job breakdown (cosine vs cluster contributions, the overlapping keywords
   that *literally summed to* the cosine). This is what `reports/clustering.json`
   and the `/clusters` Fit-map render — so the picture always matches the score.

### 8. Recency weight + company rank

`apply_recency`: `rank_score = round(fit · 0.5^(age_days/half_life_days), 2)`
(`half_life_days` default 7 → a posting loses half its weight per week; unknown
ages assumed 14 days). Jobs sort by `(-rank_score, -fit, company, title)`.
`rank_companies`: company fit = mean of its top-`company_top_n` (default 3)
postings — which is how the report's company table is ordered.

### 9. Seen-state (`state.py`)

`load_seen` reads `data/seen_jobs.tsv` (`key<TAB>date` per line; salvages valid
lines even from a merge-conflicted file, and falls back to the legacy `.json`).
`mark_new` sets `is_new` for keys not seen before; `update_seen` writes today's
date for new keys back as sorted TSV. TSV replaced JSON specifically because a
bad git merge of the old JSON could flag *every* job 🆕.

### 10. Merge validation (`validation.py`)

If `data/validation.json` exists and is ≤ 3 days old, `apply_verdicts` annotates
each posting's `validation` (`verified`/`mismatch`/`stale`) and note, returning a
tally; `archive_validation` copies it to `data/validation-history/<date>.json`.
This is the read side of the once-daily, subscription-funded Claude loop: each
run also *writes* `reports/validation-request.md` (stage 11), you run the
`/validate-jobs` skill to fact-check the postings against their live pages, it
writes `data/validation.json`, and the next run folds the verdicts into a **Conf**
column. See `design-validation-loop.md`.

### 11. Write reports (`report.py`)

`write_reports` emits `reports/<today>.md` + `latest.md` (same Markdown),
`latest.csv`, and `latest.json` (the machine-readable feed the web app ingests —
jobs, near-miss, funnel; descriptions omitted). The Markdown has, in order: a
"What this run targeted" section, companies ranked by résumé fit, a skew warning
if one company dominates the top 10, the top-N jobs by recency-weighted fit
(with 🆕 and a Conf column when verdicts exist), near-miss roles with reasons,
the fetch→filter funnel, cluster topics, new-since-last-run, boards that errored,
and the manual-check list. `write_clustering` writes `clustering.json`;
`write_run_log` writes `run-log.{json,md}` (targeting, board results, funnel
totals, top matched titles) — the first place to look when results seem wrong.

## Discovery commands

These build the *registry*, separately from a normal run.

### `discover "<company>"` — one company's ATS slug (`discover.py`)

Companies migrate ATS vendors, so slugs rot. This finds the current one without
guessing: (1) if a careers URL is known, try to classify it directly; (2) probe
name-derived slug candidates (`"Warby Parker"` → `warbyparker`, `warby-parker`,
`warby`) against the four public ATS APIs (Greenhouse/Lever/Ashby/SmartRecruiters)
— a 200 with ≥1 posting confirms it, no browser needed; (3) failing that, a
headless-Chromium survey of the careers page classifies **every URL the frontend
touches** (XHRs, redirects, iframes, anchors) against URL-pattern rules,
following job-listing-ish links one or two hops deep. It prints a paste-ready
`companies.yaml` stanza and writes nothing — you review, paste, and `verify`.

### `discover-companies` — a résumé-tailored registry (`company_discovery.py`)

Builds a per-résumé employer set so you are not limited to the curated ~68:

1. **Target** — `resolve_profile` supplies the aggregator query + Muse categories
   (else fall back to `settings.search.query` and inferred categories).
2. **Mine** — run the enabled `sources/` (The Muse and HN "who is hiring" are
   keyless; Adzuna needs a free `ADZUNA_APP_ID`/`KEY` or it skips cleanly). Each
   returns `CompanyLead`s (name + evidence: titles, snippets, any ATS URLs seen).
3. **Rank** — TF-IDF cosine of each lead's evidence (its own name masked) against
   the résumé, with a small multi-mention bonus, scaled so the top lead = 100.
4. **Resolve** — for the top N, reuse `discover.py`: trust a URL the company
   itself posted (HN links), else probe slugs.
5. **Write** — `data/companies.discovered.yaml` (companies.yaml-shaped, tagged
   `discovered`, with a `discovered_via` audit field); unresolved leads go to
   `manual_check`. `--dry-run` prints instead. Merged under the curated file on
   every run.

## How to debug a run

1. Read `reports/run-log.md` — it states the matched occupation(s), the search
   query, which boards returned/erred/came back empty, and the funnel totals.
2. "Why am I seeing SWE jobs for a non-SWE résumé?" → check the targeting section
   engaged and what query it used. A low-confidence match falls back to manual.
3. "Why zero from company X?" → its funnel row shows whether it was a fetch error,
   a title-filter wipeout, a location wipeout, or genuinely aged out.
4. "Why did job Y score what it did?" → the `/clusters/job/{id}` Fit-map page, or
   the per-job block in `reports/clustering.json`.
5. `python -m jobsearch verify` after editing `companies.yaml` to catch bad slugs.
