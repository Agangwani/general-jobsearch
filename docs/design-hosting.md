# Hosting design — multi-user jobsearch online

Goal: anyone can sign up, upload a resume, and get matched jobs; one shared
hosted database of users with the repo owner as admin; small budget; built
with security as a first-class requirement.

## What changes between "local app" and "hosted product"

The current app is deliberately single-user-local: SQLite on disk, no auth,
file paths under `data/`, and an integrated Chromium that drives *your*
browser sessions. Three of those translate directly; one does not:

| Local feature | Hosted equivalent |
|---|---|
| SQLite `data/jobsearch.db` | Managed Postgres, every table gains a `user_id` |
| Resume at `data/resume.txt` | Per-user upload in object storage / DB column |
| Daily pipeline run | One shared fetch worker for ALL users (see below) |
| Auto-fill apply browser | **Stays local-only.** It drives a Chromium with the user's own cookies/sessions on their machine; running it server-side would mean holding users' credentials. Hosted UI links out to postings; power users keep running the local app. |
| Gmail sync | Defer from hosted v1. Holding Google OAuth tokens for other people raises the security bar (encryption at rest, Google verification review) far above the rest of the app. |

**The key architectural win:** job postings are global, not per-user. The
expensive part (fetching ~60 boards, Playwright scraping) runs **once a day
for everyone** and writes to a shared `postings` table. Per-user work is just
scoring — TF-IDF projection of one resume against the day's corpus takes
seconds. Cost therefore barely grows with users.

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
   `users` table; `user_id` column + index on applications/events/profile
   tables (postings stay global); signup/login/logout with secure session
   cookies; every query scoped by the session's user id — enforced in one
   `current_user` dependency, not per-route discipline. Admin page (user
   list, disable user, usage counts) behind `is_admin`.
2. **Shared fetch worker + per-user scoring (~2–3 days).** Pipeline writes
   postings to Postgres instead of reports; a post-fetch step rescores every
   active user's resume against the new corpus and stores per-user fit rows.
3. **Hardening pass (~1 week initial, then ongoing).** See checklist.
4. **Later**: per-user company lists, email digests, Gmail sync (only with
   token encryption + scoped review).

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
| Biggest cuts for v1 | Auto-fill browser stays local; Gmail sync deferred |
