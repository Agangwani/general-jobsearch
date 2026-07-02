# User flows — what actually happens, end to end

> Concrete journeys through the system, tracing each step to the code and the
> files it touches. For the mechanics behind any step, see
> [`pipeline.md`](pipeline.md) and [`webapp.md`](webapp.md).

## Flow 0 — First-time setup (5 minutes)

```
./setup.sh                          # venv, pip install, playwright install chromium, launch UI
→ http://127.0.0.1:8484 opens
```

1. `setup.sh` creates `.venv`, installs `requirements.txt`, downloads Chromium
   (degrades gracefully if blocked), makes `data/`+`reports/`, and execs
   `python -m jobsearch ui`.
2. The UI comes up running against the **bundled sample résumé** so it is not
   empty. The dashboard is empty until the first ingest.
3. Go to **`/resume`** → upload your `.pdf`/`.txt`. This writes `data/resume.txt`
   (+ `data/resume.pdf` + a `.name` sidecar), extracts keywords, seeds your
   **profile** from the résumé, and shows the **detected target roles** (the role
   profile) with a **▶ Run pipeline** button.
4. Go to **`/profile`** and fill in the gaps (phone, location, work
   authorization, etc.). These are the values the autofill engine will type into
   forms. EEO fields left blank are never guessed.

**State created:** `data/resume.*`, profile rows in `data/jobsearch.db`.

## Flow 1 — The daily loop (the core use case)

```
Run the pipeline → ingest → triage the dashboard → auto-fill applications → submit yourself
```

1. **Run.** Click ▶ on `/resume` (or the run control on the dashboard, or
   `./setup.sh run`, or let GitHub Actions do it at 7:23am ET). The pipeline
   fetches every board, targets your role, scores everything, and writes
   `reports/latest.{md,csv,json}` + `clustering.json` + `run-log.*`. The UI streams
   the run's stderr live.
2. **Ingest.** The web app auto-ingests `reports/latest.json` into SQLite on the
   first log-poll after a clean finish (or you can `POST /ingest`). Each posting
   becomes a `jobs` row + an `applications` row (status `not_applied`).
3. **Triage `/`.** The dashboard shows the to-apply stack, sorted by
   recency-weighted fit, scoped to this run by default. Filter by company, minimum
   fit, or near-miss. 🆕 marks postings never seen before. Click a job for the
   **detail page**: a cleaned description, a copy-paste **profile panel**, the
   company's top interview questions, a "📊 Why this fit?" link, and a
   "🤝 Find a referral" button.
4. **Apply.** Click **⚡ Auto-fill apply** on any job (or **Prepare top 5** to
   batch the best fits). The shared Chromium window opens the posting in a new tab
   and fills the form from your profile across as many passes as the page needs.
   The button polls and shows "auto-filled N fields (+M left for review)."
5. **Review & submit.** You check the filled fields, complete anything skipped
   (EEO, cover letter, anything it wasn't sure about), and **click submit
   yourself**. The engine watches for the confirmation page and flips the
   application to **applied** automatically.
6. **Mark up.** Use the per-row status dropdown or the bulk bar to move jobs
   through `applied → confirmed → interviewing → offer/rejected`. Everything is
   logged append-only in `application_events`.

**State touched:** `reports/*`, `data/seen_jobs.tsv`, `data/corpus/*`,
`data/jobsearch.db` (jobs, applications, events), `data/browser_profile/`.

## Flow 2 — Retargeting to a non-engineering résumé

The whole point of role targeting. Suppose you upload a **Customer Success** résumé.

1. On the next run, `role_profile.resolve_profile` matches it (TF-IDF or MiniLM)
   to the *Customer Success* occupation in `config/occupations.yaml`.
2. `apply_profile` **replaces** the SWE-by-default `search.query` /
   `title_include` / `title_exclude` with Customer-Success ones — so the boards
   are searched and filtered for CS roles, not engineering roles.
3. `reports/run-log.md` and the report's "What this run targeted" section confirm
   the matched occupation, the query, and the relevant skills.
4. If your résumé straddles two fields (CS + Project Management), a runner-up
   occupation scoring ≥ 85% of the top is blended in.

**To override:** set `search.role_targeting: manual` in `settings.yaml` and edit
the `title_include`/`title_exclude` regexes by hand. **To widen the taxonomy:**
`python tools/build_occupations.py <onet_dir> > config/occupations.yaml`.

## Flow 3 — Discovering companies for your résumé

The curated registry is ~68 companies. To go beyond it:

```
python -m jobsearch discover-companies --dry-run     # preview
python -m jobsearch discover-companies               # write the registry
```

1. It mines **The Muse**, the **HN "Who is hiring?"** thread, and (with a free
   key) **Adzuna** for companies hiring people like you in your location.
2. It ranks the leads by résumé fit (TF-IDF), resolves each to its ATS board
   (trusting URLs companies posted themselves, else probing slug guesses), and
   writes `data/companies.discovered.yaml`.
3. That file is merged **under** `companies.yaml` on every subsequent run —
   curated entries always win, and your current employer
   (`discovery.exclude_companies`) is never added.

To pin a discovered company permanently, move its stanza into `companies.yaml`.
To find one specific company's board: `python -m jobsearch discover "Warby Parker"`
and paste the printed stanza.

## Flow 4 — The validation loop (confidence without an API key)

Once a day, fact-check the report against the live postings using your Claude
subscription:

1. Every `run` writes **`reports/validation-request.md`** (the top jobs +
   near-misses with their claims).
2. In Claude Code, invoke the **`/validate-jobs`** skill. Claude reads the request
   + your résumé, web-verifies each posting (still live? senior? in NYC?), and
   writes **`data/validation.json`** with a verdict + confidence per posting.
3. The **next** `run` folds the verdicts into the report as a **Conf** column
   (✓ verified / ⚠ mismatch / ✗ stale) and archives them to
   `data/validation-history/` so labeled precision becomes a time series.

This is the only path to *labeled precision* — the metric that says whether the
fit scores themselves are any good. See `design-validation-loop.md`.

## Flow 5 — Interview prep

1. **`/prep`** — pick a track (Coding/CtCI, System Design, or Distributed
   Systems/DDIA). The landing page shows overall progress and "resume where you
   left off."
2. Open a **module** → read its **lessons** (rendered Markdown with key takeaways;
   opening one marks it in-progress), drill its **LeetCode** problems, and work its
   **CtCI book problems** (prompt → progressive hints → worked solution; opening
   one marks it attempted). If you've placed the source books locally, "📖 Open
   source chapter" shows the distilled chapter and deep-links the PDF.
3. Mark lessons/problems solved/attempted and jot notes — all persisted by stable
   row id in `data/jobsearch.db`, surviving content reseeds.

## Flow 6 — Company-specific interview questions

1. **`/companies`** — every employer with its question + solved counts. Each job
   detail page also shows the top-6 questions for that posting's company, right
   next to the application.
2. Open a company → its LeetCode questions ranked by how often it asks them, with
   difficulty filters and frequency bars. Mark problems solved/attempted (persists
   across runs).
3. **⟳ Refresh questions** pulls a larger, frequency-measured list from a
   community GitHub CSV dataset. Network-optional: if it can't be reached, the
   bundled list stays and the UI shows why. Point it at a different dataset/window
   under `company_questions:` in `settings.yaml`.

## Flow 7 — Finding a referral (highest-risk feature)

1. On a job detail page, click **🤝 Find a referral** → `/jobs/{id}/referrals`,
   then **Discover**.
2. A **headed** Chromium window opens LinkedIn People Search. **The first time,
   you log in yourself** — the tool never authenticates programmatically (that
   gets accounts banned), and headed mode lets you solve any verification
   challenge. Your login persists in `data/browser_profile/linkedin/`.
3. It de-levels the job title (so it finds subject-matter experts, not headline
   keyword matches), scrapes the result cards, and ranks candidates by **job fit +
   your-background fit** in one shared TF-IDF space.
4. Candidates are stored and shown with Job-fit / Your-fit / Combined columns and
   "Open profile ↗" links. Reload the page to see results (it does not auto-poll).

> **Caveat, stated plainly:** this automates LinkedIn against its ToS. Repeated
> rapid searches can trigger verification challenges or temporary restrictions.
> Consider a secondary LinkedIn login. Pacing is randomized (3–7s) to reduce risk.

## Flow 8 — Syncing confirmation emails

1. Create a Google Cloud OAuth **Desktop app** client, download its JSON to
   `data/credentials.json`.
2. **`/emails`** → **Connect** → consent in the browser. A read-only
   (`gmail.readonly`) token is stored at `data/token.json`.
3. **⟳ Sync now** pulls recent mail **from your applied companies and known ATS
   senders only**, classifies each (confirmation/interview/rejection/offer), links
   it to the right application, and **auto-advances applied→confirmed** on a
   confirmation. Synced mail appears on `/emails` and on the relevant job detail
   page.

## How the flows compose

The dashboard is the hub. A typical week: let CI run the pipeline daily; each
morning open `/`, triage the new 🆕 jobs, **Prepare top 5** to auto-fill them,
review and submit, mark them applied; once a day run `/validate-jobs` to keep the
confidence column honest; between applications, work `/prep` and the company
questions for your upcoming interviews; for the most promising roles, find a
referral; and let Gmail sync quietly advance applications as confirmations and
interview invites arrive.
