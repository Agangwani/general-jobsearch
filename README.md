# jobsearch — daily NYC senior-SWE job finder

Every morning this pipeline pulls postings **directly from company job
boards** (no aggregators), keeps the ones that look like senior software
engineer roles in NYC, ranks everything against `data/resume.txt`, and writes
a report that prioritizes **recently posted** jobs.

## How it works

1. **Company registry** — `config/companies.yaml` holds ~60 companies:
   FAANG (tagged `faang`) and the top NYC software employers (tagged
   `top50`) are always included. Each entry points at the company's own ATS:
   Greenhouse, Lever, Ashby, Workday, Eightfold, or a company-specific API
   (Amazon, Google, Apple, Meta, Microsoft, Bloomberg, Uber, Spotify).
2. **Fetch** — every enabled board is queried in parallel for senior
   software engineer roles. A broken board never sinks the run; it lands in
   the report's "needs attention" section instead.
   Boards with **no public API** (Goldman Sachs, JPMorgan, Millennium,
   TikTok, Jane Street, D. E. Shaw) are scraped with **headless Chromium
   (Playwright)** after the API pass: the browser loads the company's own
   career page and captures the JSON its frontend fetches (XHR capture),
   which is far more durable than CSS selectors. Apply links always point at
   the company's own site — direct applications only, never a third-party
   board. Meta and Apple also get a browser fallback for when their
   undocumented APIs break.
3. **Filter** — title regexes (senior/staff SWE, excluding intern, manager,
   principal, mobile, ...) and NYC location matching, both editable in
   `config/settings.yaml`.
4. **Rank by fit** — all postings are embedded in a shared TF-IDF token
   space and clustered with **K-means**; the resume is projected into the
   same space. A posting's fit = 0.7 × cosine similarity to the resume +
   0.3 × the resume's affinity to the posting's cluster, scaled so the best
   match of the day is 100. Company fit = mean of its top-3 postings, which
   is how the company list in the report is sorted.
5. **Prioritize recency** — job order uses
   `rank_score = fit × 0.5^(age_days / 7)`: a posting loses half its weight
   every week, so fresh postings rise to the top. Jobs the pipeline has
   never seen before (tracked in `data/seen_jobs.json`) are flagged 🆕.
6. **Report** — `reports/latest.md` (plus a dated copy, CSV, and JSON) with:
   companies ranked by fit, top jobs by recency-weighted fit, new-since-last-run,
   broken boards, and a "check manually" list (currently just LinkedIn, whose
   careers site sits behind bot protection that scraping would violate).

## Daily schedule

`.github/workflows/daily-job-search.yml` runs the pipeline every day at
7:23am ET (11:23 UTC) and commits the refreshed report back to the repo.
You can also trigger it on demand from the Actions tab (workflow_dispatch).

To run locally instead, `crontab -e`:

```
23 7 * * * cd /path/to/jobsearch && python -m jobsearch run
```

## Usage

```bash
pip install -r requirements.txt
playwright install chromium   # one-time, for browser-scraped boards + apply browser

python -m jobsearch run      # full daily run → reports/latest.md
python -m jobsearch verify   # check every configured board is reachable

python -m jobsearch ingest   # pull the latest run into the application database
python -m jobsearch ui       # application-tracking UI → http://127.0.0.1:8484
```

The UI (docs/design-frontend.md) tracks your to-apply / applied stacks in a
local SQLite database (`data/jobsearch.db`, gitignored), shows formatted job
descriptions with a copy-paste profile panel and your resume, and — via the
"⚡ Auto-fill apply" button on every job row — opens each posting in its own
tab of an integrated Chromium window, **auto-fills the application form from
your profile** (docs/design-autofill.md), and detects submissions
automatically. It never clicks submit: you review every field and submit
yourself.

If Chromium isn't installed the run still works — browser-scraped boards are
skipped with an actionable note in the report instead of failing the run.

> **Note:** ATS board slugs in `companies.yaml` are best-effort and companies
> migrate ATS vendors over time. Run `python -m jobsearch verify` (or just
> read the "needs attention" section of the daily report) and fix or remove
> any slug that 404s. The sandbox this project was authored in could not
> reach the job-board domains, so expect to prune a few on the first real run.

## Customizing

- **Add/remove companies** — edit `config/companies.yaml`. For Greenhouse
  use the slug from `boards.greenhouse.io/<slug>`, for Lever
  `jobs.lever.co/<slug>`, for Ashby `jobs.ashbyhq.com/<slug>`.
- **Change role/location targeting** — `search.title_include`,
  `search.title_exclude`, and `search.locations` in `config/settings.yaml`.
  Set `include_remote: true` to also accept US-remote roles.
- **Tune recency vs. fit** — `ranking.half_life_days` (smaller = recency
  matters more) and `ranking.max_age_days` (hard cutoff).
- **Update the resume** — replace `data/resume.txt`; the ranking adapts
  automatically on the next run.

Capital One is deliberately not in the registry (current employer).

## Layout

```
config/companies.yaml    company registry (FAANG + NYC top 50, ATS pointers)
config/settings.yaml     filters, ranking knobs, fetch limits
data/resume.txt          resume text used for fit scoring
data/seen_jobs.json      state: job IDs seen on previous runs
jobsearch/fetchers/      one adapter per ATS / company API
jobsearch/scoring.py     TF-IDF + K-means fit scoring, recency weighting
jobsearch/pipeline.py    orchestration
reports/                 daily output (markdown, CSV, JSON)
tests/                   offline tests (no network needed)
```
