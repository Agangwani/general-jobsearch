# jobsearch — resume-driven job finder + application tracker

Point it at **your resume** and it pulls postings **directly from company job
boards** (no aggregators), filters to the roles you target, ranks everything
against your resume with TF-IDF + K-means, and gives you a local web UI to
track applications, auto-fill forms, and sync confirmation emails.

## Quickstart (one command)

```bash
git clone https://github.com/Agangwani/general-jobsearch
cd general-jobsearch
./setup.sh            # installs everything, opens the UI at http://127.0.0.1:8484
```

Then open **http://127.0.0.1:8484/resume** and upload your resume (`.pdf` or
`.txt`). That's it — the next pipeline run (`./setup.sh run`, or the ⟳ button
in the UI) fetches boards, scores every posting against *your* resume, and
fills the dashboard. Until you upload one, everything runs against the
bundled `data/sample_resume.txt` so you can explore the app immediately.

Everything personal stays on your machine: `data/` (resume, profile, OAuth
tokens, SQLite DB) and `reports/` are gitignored. The repo only ships code,
config, and the sample resume.

The default search targets senior software engineering roles in NYC — edit
`config/settings.yaml` (title/location filters, remote-pay policy) and
`config/companies.yaml` (which boards to pull) to retarget it.

## Understanding the codebase

This README is the quick tour. For a thorough, current-state map of the repo,
read **[`docs/`](docs/README.md)** — start with
**[`docs/architecture.md`](docs/architecture.md)** (the whole system on one
page) and branch into the pipeline deep dive, the web app deep dive, end-to-end
user flows, known limitations, and refactoring notes. The summary below is the
condensed version of that.

## How it works

1. **Company registry** — `config/companies.yaml` holds ~60 curated
   companies: FAANG (tagged `faang`) and the top NYC software employers
   (tagged `top50`) are always included. Each entry points at the company's
   own ATS: Greenhouse, Lever, Ashby, Workday, Eightfold, or a
   company-specific API (Amazon, Google, Apple, Meta, Microsoft, Bloomberg,
   Uber, Spotify). On top of that, `python -m jobsearch discover-companies`
   builds a **resume-tailored registry dynamically**: it mines generalized
   boards (The Muse, the HN "Who is hiring?" thread, optionally Adzuna) for
   companies hiring people like you in your target location, ranks them by
   resume fit, auto-resolves each to its own ATS board, and writes
   `data/companies.discovered.yaml`, which every run merges under the
   curated file (docs/design-company-discovery.md).
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
3. **Filter** — title regexes and NYC location matching. By default the title
   targeting is **derived from your resume**: the resume is matched to its
   nearest occupation in `config/occupations.yaml` (O*NET-shaped: Customer
   Success, Project Manager, Data Scientist, …) and that occupation's query +
   title patterns replace the SWE defaults, so a non-engineering resume stops
   coming back full of engineering jobs (docs/design-role-targeting.md). Set
   `search.role_targeting: manual` in `config/settings.yaml` to use hand-tuned
   regexes instead. Location matching stays in `config/settings.yaml`.
4. **Rank by fit** — all postings are embedded in a shared TF-IDF token
   space and clustered with **K-means**; the resume is projected into the
   same space. A posting's fit = 0.85 × cosine similarity to the resume +
   0.15 × the resume's affinity to the posting's cluster, scaled so the best
   match of the day is 100. Company fit = mean of its top-3 postings, which
   is how the company list in the report is sorted. The **Fit map** tab in the
   UI visualizes this whole space and breaks down any single score (see below).
5. **Prioritize recency** — job order uses
   `rank_score = fit × 0.5^(age_days / 7)`: a posting loses half its weight
   every week, so fresh postings rise to the top. Jobs the pipeline has
   never seen before (tracked in `data/seen_jobs.json`) are flagged 🆕.
6. **Report** — `reports/latest.md` (plus a dated copy, CSV, and JSON) with:
   companies ranked by fit, top jobs by recency-weighted fit, new-since-last-run,
   broken boards, and a "check manually" list (currently just LinkedIn, whose
   careers site sits behind bot protection that scraping would violate).

## Debugging a run

Every `run` writes **`reports/run-log.json`** (and a readable
`reports/run-log.md`) recording what it actually did: the role profile it
matched (occupations, query, seniority, skills), which boards returned
postings vs. errored vs. came back empty, the fetch→match→near-miss funnel,
and this run's top matched titles. The main report (`reports/latest.md`) now
also leads with a **"What this run targeted"** section. If results look wrong
("why am I seeing software-engineer jobs for a customer-success resume?"),
that log shows whether targeting engaged and what it searched for.

Note the **tracker dashboard accumulates** across runs: ingest adds each run's
jobs but never deletes earlier ones, so jobs from a previous (differently
targeted) run stay in your to-apply stack. Ingest now logs how many unapplied
jobs are *not* in the latest report so leftovers are obvious.

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
python -m jobsearch discover "Warby Parker"   # auto-detect a company's ATS board slug
python -m jobsearch discover-companies        # mine generalized boards for companies
                                              # matching YOUR resume; --dry-run to preview

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

### Interview prep curriculum

The **Prep** tab is a resumable, cited curriculum that now spans disciplines, not
just software. A universal **Behavioral Interviews** track (STAR / Nugget-First,
a 50+ question bank by competency, Amazon's Leadership Principles, "tell me about
yourself"/weakness/salary) sits alongside the original software tracks (coding,
system design, distributed systems) and new discipline tracks: **Case Interviews**
(consulting/strategy/ops), **Finance & Investment Banking**, **Product
Management**, **Data & Analytics**, **Sales/CS/Account Management**, **Marketing**,
**Design**, and **Industry-Specific** (healthcare, legal, education, HR). Content
is authored in `jobsearch/prep/` and each lesson cites its source.

Prep is the one part of the flow that is *not specific to your resume's role* —
every track is available to everyone — but the `/prep` page now **recommends**
the tracks relevant to your resume: Behavioral for every resume, plus the
discipline track(s) for your matched occupation (a consultant sees Case
Interviews first; a nurse sees Industry-Specific). The occupation→discipline
mapping lives in `jobsearch/prep/disciplines.py`.

### Company interview questions (LeetCode)

The **Companies** tab tracks *what each company actually asks* on LeetCode.
Online, every big employer is known for a recognisable set of problems
(Amazon → LRU Cache / Number of Islands, Meta → Min Remove to Make Valid
Parentheses, …). The app ships a curated, **offline** set per company and
shows them ranked by how often that company asks them, with mark-solved /
attempted tracking that persists across runs (`/companies` → pick a company).
Every **job detail page** also surfaces the top questions for that posting's
company, so the prep is right next to the application.

Hit **⟳ Refresh questions** on a company to pull a larger, frequency-measured
list from a community "company-wise LeetCode" dataset (one CSV per company).
It's network-optional — exactly like a broken board never sinks a run: if the
dataset can't be reached the bundled list stays and the reason shows in the
UI. Point it at a different dataset or time window under `company_questions:`
in `config/settings.yaml`. Bundled content lives in
`jobsearch/company_questions/` (curated set + the refresh loader).

### Fit map — why a job scored what it did

Fit scores are easy to distrust when they're just a number. The **Fit map**
tab (`/clusters`) opens up the TF-IDF + K-means model:

- A **high-level view**: every scored posting plotted as a 2-D scatter (LSA
  projection of the TF-IDF space), coloured by the K-means cluster it landed
  in, with **your resume** drawn in the same space — closer means more similar
  wording. Each cluster is labelled with its topic terms and how strongly your
  resume matches it (the "home" cluster is the one feeding the cluster-fit term
  of every score). Hover a cluster to highlight its postings; click any point
  to drill in.
- A **per-job view** (`/clusters/job/{id}`, also the "📊 Why this fit?" button
  on every job page): the exact arithmetic behind one posting's score — the
  `0.85 × cosine + 0.15 × cluster-affinity` split shown as a stacked bar, the
  overlapping keywords that earned the cosine (each literally a term in the
  similarity sum), and where the posting sits relative to your resume on the
  map.

Each run writes the model snapshot to `reports/clustering.json` (local-only,
like the other reports), and the scorer emits it straight from the vectors it
already computed, so the numbers shown always match the assigned `fit_score`.

> **Note:** ATS board slugs in `companies.yaml` are best-effort and companies
> migrate ATS vendors over time. Run `python -m jobsearch verify` (or just
> read the "needs attention" section of the daily report) and fix or remove
> any slug that 404s. The sandbox this project was authored in could not
> reach the job-board domains, so expect to prune a few on the first real run.

## Customizing

- **Add/remove companies** — edit `config/companies.yaml`. For Greenhouse
  use the slug from `boards.greenhouse.io/<slug>`, for Lever
  `jobs.lever.co/<slug>`, for Ashby `jobs.ashbyhq.com/<slug>`.
- **Discover companies for your resume** — `python -m jobsearch
  discover-companies` regenerates `data/companies.discovered.yaml` from
  generalized job boards. Tune it under `discovery:` in
  `config/settings.yaml`: `location` (what aggregator APIs are asked for),
  `max_companies`, `categories` (Muse categories, default inferred from your
  resume), `exclude_companies` (never auto-add — put your current employer
  here), and `sources`. Adzuna is included when `ADZUNA_APP_ID` /
  `ADZUNA_APP_KEY` are set (free key at developer.adzuna.com). Curated
  entries in `companies.yaml` always win conflicts; delete the generated
  file to fall back to the curated registry alone.
- **Retarget to your roles (automatic)** — by default (`search.role_targeting:
  auto`) the pipeline matches your resume to an occupation in
  `config/occupations.yaml` and searches for *that* role. Upload your resume on
  the `/resume` page and it shows the detected target roles + relevant skills,
  with a **▶ Run pipeline** button. To widen coverage beyond the shipped seed,
  distil the full O*NET database into `config/occupations.yaml` with
  `python tools/build_occupations.py <onet_dir>`. Matching uses TF-IDF by
  default; `pip install sentence-transformers` enables the more robust MiniLM
  backend automatically (`search.role_match_backend`).
- **Change role/location targeting (manual)** — set `search.role_targeting:
  manual` and edit `search.title_include`, `search.title_exclude`, and
  `search.locations` in `config/settings.yaml`.
  Set `include_remote: true` to accept all US-remote roles, or leave it off
  and use `remote_min_pay` (default $200k) to admit only remote roles whose
  posted pay range clears the floor. `promote_unleveled: true` lets
  unleveled software titles (Stripe-style) match when the description
  requires 5+ years.
- **Tune recency vs. fit** — `ranking.half_life_days` (smaller = recency
  matters more) and `ranking.max_age_days` (hard cutoff).
- **Update the resume** — replace `data/resume.txt`; the ranking adapts
  automatically on the next run.

Capital One is deliberately not in the registry (current employer) and sits
in `discovery.exclude_companies` so dynamic discovery can never add it back.

## Layout

```
config/companies.yaml    curated company registry (FAANG + NYC top 50, ATS pointers)
config/occupations.yaml  occupation taxonomy: resume → target roles/skills
config/settings.yaml     filters, ranking knobs, fetch limits, discovery knobs
data/resume.txt          resume text used for role targeting + fit scoring
data/role_profile.json   what the last run targeted (occupations, skills), gitignored
data/companies.discovered.yaml  generated registry (discover-companies), gitignored
data/seen_jobs.json      state: job IDs seen on previous runs
jobsearch/fetchers/      one adapter per ATS / company API
jobsearch/sources/       company-lead sources: generalized boards (Muse, HN, Adzuna)
jobsearch/company_questions/  curated company→LeetCode sets + the refresh loader
jobsearch/role_profile.py       resume → occupation matching (TF-IDF / MiniLM)
jobsearch/company_discovery.py  resume-tailored registry generation
tools/build_occupations.py      expand config/occupations.yaml from O*NET
jobsearch/scoring.py     TF-IDF + K-means fit scoring, recency weighting, the /clusters explanation
jobsearch/pipeline.py    orchestration
webapp/clusters.py       loads reports/clustering.json for the Fit map views
reports/                 daily output (markdown, CSV, JSON, run-log)
reports/run-log.json     per-run diagnostics: what was targeted, board results, funnel
reports/clustering.json  per-run fit map: 2-D projection + per-job score breakdown
jobsearch/prep/          multi-discipline interview-prep curriculum (behavioral, case, finance, …)
tests/                   offline tests (no network needed)
tests/fixtures/resumes/  20 industry resumes (one per top NYC industry) for the suite
tests/industry_fixtures.py  manifest behind tests/test_industry_resumes.py
```
