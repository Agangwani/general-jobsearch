# Hosting design — multi-user jobsearch online

Goal: anyone can sign up, upload a resume, and get matched jobs; one shared
hosted database of users with the repo owner as admin; small budget; built
with security as a first-class requirement.

## What the app is today

Since this doc was first written the project grew from a CLI pipeline into a
full local web product. `python -m jobsearch ui` serves a FastAPI app
(`webapp/`) on `127.0.0.1:8484`, backed by SQLite at `data/jobsearch.db`.
It is deliberately single-user-local: no auth, profile PII and OAuth tokens
on disk under `data/`, and an integrated Chromium that drives *your* logged-in
browser sessions. The current feature surface:

- **Job dashboard** — to-apply / applied stacks, filtering and sorting over
  the pipeline's scored postings; per-job detail + event history.
- **Resume upload & rescoring** (`/resume`) — upload a PDF, rescore the whole
  corpus against it on demand.
- **Profile** (`/profile`) — the structured PII (name, contact, work
  authorization, salary, links…) that feeds auto-fill.
- **Integrated apply browser + auto-fill** (`webapp/apply_browser.py`,
  `autofill.py`) — opens a posting in a Chromium with your own cookies and
  pre-fills the application form; never clicks submit.
- **Gmail sync** (`webapp/gmail.py`, `/emails`) — now *built*: OAuth
  (`gmail.readonly`) with the token in `data/token.json`, server-scoped search
  to mail from companies you're applying to, auto-advances `applied →
  confirmed`.
- **LinkedIn referral discovery** (`jobsearch/referrals/`) — Playwright drives
  your logged-in LinkedIn session to find potential referrers per job.
- **Interview prep** (`jobsearch/prep/`, `/prep`) — a seeded curriculum
  (tracks/modules/lessons/CTCI problems) with per-user progress tracking.

## What changes between "local app" and "hosted product"

Most data tables translate directly to multi-tenant; the three browser-session
features do not, because they run with *your* credentials on *your* machine:

| Local feature | Hosted equivalent |
|---|---|
| SQLite `data/jobsearch.db` | Managed Postgres; per-user tables gain a `user_id` (postings stay global — see below) |
| Profile PII (`profile_fields`) + resume PDF | Per-user rows / object-storage upload, scoped by `user_id` |
| Daily pipeline run (GitHub Action, already exists) | Same Action, repointed to write Postgres instead of committing reports (see below) |
| Auto-fill apply browser | **Stays local-only.** Drives a Chromium with the user's own cookies/sessions; server-side would mean holding users' credentials. Hosted UI links out to postings; power users keep running the local app. |
| LinkedIn referral discovery | **Stays local-only**, same reason: it relies on the user's logged-in LinkedIn session in a local Playwright Chromium. |
| Gmail sync | Defer from hosted v1. The code exists and works locally, but holding Google OAuth tokens for *other* people raises the bar (encryption at rest, Google verification review, gmail.readonly app audit) far above the rest of the app. |
| Interview prep | Curriculum content is global (seeded, idempotent); only the `*_progress` tables are per-user. Trivially multi-tenant. |

**The key architectural win:** job postings are global, not per-user, so
fetch cost scales with **distinct search profiles, not users**:

- Most boards (Greenhouse/Lever/Ashby/SmartRecruiters) return the *full*
  board in one call — every role, HR included; filtering is local. One
  daily fetch serves every user regardless of what they're looking for.
- Search-parameterized sources (Google, Amazon, Workday tenants, the
  browser-scraped boards) bake keyword+location into the request. These run
  once per distinct (board, role keywords, location) profile, deduped
  across users — 1,000 SWE-in-NYC users still cost one pass; an HR-in-Austin
  user adds one more pass over only these boards. Rare niche profiles can
  be batched on-signup/on-demand instead of daily.
- The company registry becomes global: users subscribe to companies, the
  worker fetches the union, each company once regardless of follower count.

Per-user work is just scoring — TF-IDF projection of one resume against the
day's corpus takes seconds. Cost is therefore sublinear in users.

**The fetch worker already exists.** `.github/workflows/daily-job-search.yml`
runs the pipeline daily (`23 11 * * *`), installs Playwright/Chromium for the
browser-scraped boards, runs the tests, then **commits** `reports/` and
`data/seen_jobs.tsv` back to the repo. The hosted change is small and isolated:
keep the same Action and Playwright setup, but the final step writes postings
to Postgres via a `DATABASE_URL` secret and triggers per-user rescoring,
instead of `git commit`/`git push`. No new infrastructure for the heaviest
component.

## Recommended stack (cheapest credible path)

- **App**: the existing FastAPI app, containerized, on **Fly.io or Railway**
  (~$5/mo for a shared-CPU 512MB instance; free tiers exist but sleep).
  TLS and a `*.fly.dev` domain are free; a custom domain is ~$12/yr.
- **Database**: **Neon or Supabase managed Postgres** — free tier (0.5–1 GB)
  comfortably holds tens of thousands of postings + thousands of users;
  $19/mo when outgrown. Daily backups included. You hold the admin
  credentials; an `is_admin` flag on your user row gates the admin pages.
- **Fetch worker**: a **scheduled GitHub Action** (free) running the existing
  pipeline with Playwright and writing to Postgres via `DATABASE_URL` secret.
  Zero hosting cost for the heaviest component, and it's the same code path
  the repo already runs daily.
- **Auth**: email+password with **argon2id** hashing, or lean on Supabase
  Auth / "Sign in with Google" to outsource credential handling entirely
  (recommended — fewer ways to get it wrong).

**Cost: $0–5/mo to start, ~$25–45/mo at the point where free tiers are
outgrown** (bigger Postgres + a second app instance). The first real money
is the Postgres upgrade, not compute.

## Effort estimate (staged, each stage shippable)

1. **Multi-tenancy + auth (the bulk: ~1–2 weeks of focused sessions).**
   `users` table; add a `user_id` column + index to the per-user tables —
   `applications`, `application_events`, `profile_fields`, `runs`, and the
   `prep_*_progress` tables — while `jobs`/`job_events` and the prep
   *content* tables (`prep_tracks/modules/lessons/problems`) stay global.
   Signup/login/logout with secure session cookies; every query scoped by the
   session's user id — enforced in one `current_user` dependency, not
   per-route discipline. Admin page (user list, disable user, usage counts)
   behind `is_admin`.
2. **Shared fetch worker + per-user scoring (~2–3 days).** Repoint the
   existing Action to write postings to Postgres; a post-fetch step rescores
   every active user's resume against the new corpus and stores per-user fit
   rows.
3. **Hardening pass (~1 week initial, then ongoing).** See checklist.
4. **Later**: per-user company lists, email digests, and hosted Gmail sync
   (the local module already works — hosting it adds token encryption at rest
   + Google verification review). Auto-fill and referral discovery remain
   local-only by design.

## Security checklist (what "no security flaws" means in practice)

No software has *no* flaws — the honest target is: no OWASP-Top-10 class
bugs, a small attack surface, and fast recovery. Concretely:

- **AuthN/AuthZ**: argon2id password hashes (or delegated OAuth); session
  cookies `HttpOnly + Secure + SameSite=Lax`; CSRF tokens on every
  state-changing form (the app is form-POST based); all queries filtered by
  `user_id` from the session — never from the URL.
- **Uploads**: resume uploads capped (1 MB), extension+MIME checked, parsed
  with pypdf only, stored under a server-generated name, never executed or
  served back raw.
- **Injection**: keep using parameterized SQL everywhere (already the
  codebase convention); Jinja2 autoescaping stays on (already on).
- **Secrets**: `DATABASE_URL`, session signing key, OAuth secrets live in
  platform env vars / GitHub Actions secrets — the repo stays clean of
  credentials (already the project rule).
- **Transport**: HTTPS only (platform-terminated), HSTS header,
  `X-Content-Type-Options: nosniff`, a restrictive Content-Security-Policy.
- **Abuse**: rate-limit auth + upload endpoints (slowapi or platform proxy);
  signup email verification to stop bot accounts.
- **Ops**: Postgres automated backups (included in Neon/Supabase); error
  monitoring (Sentry free tier); `pip-audit`/Dependabot in CI; account
  deletion endpoint that hard-deletes the user's rows (privacy promise, and
  it keeps the data model honest).
- **Privacy**: resumes are the crown jewels — encrypt at rest (Postgres
  column-level via pgcrypto or platform disk encryption), and never log
  their contents.

## Decision summary

| Question | Answer |
|---|---|
| Cheap way to host? | Yes: Fly.io/Railway app + Neon/Supabase Postgres + GitHub Actions fetcher |
| Cost | $0–5/mo start; ~$25–45/mo grown |
| Effort | ~2–3 weeks of sessions to multi-user v1; auth is the bulk |
| Shared admin DB | Postgres with `users.is_admin`; you own the credentials |
| Biggest cuts for v1 | Auto-fill browser and LinkedIn referral discovery stay local (user's own sessions); Gmail sync deferred despite working locally |
| Fetch worker | Already built as a GitHub Action; hosting just repoints its output from git to Postgres |
