# Deploying the web app (free hosts)

How to run the jobsearch web app on a managed host so it's reachable from any
device. The repo ships a host-agnostic [`Dockerfile`](../Dockerfile); pick a
host below. Companion to [`design-hosting-progress.md`](design-hosting-progress.md)
(the staged plan) and [`design-deployment.md`](design-deployment.md) (cost
analysis).

> ## ⚠️ Read this first — do not deploy publicly yet
> The UI has **no login today**. Anything you host is readable by anyone who
> finds the URL: your résumé, profile PII, and application history. Add
> authentication (Stage 2 in `design-hosting-progress.md`) — or at least a
> single shared password — **before** exposing it. These files let you build
> the image and test it privately; treat public deploy as gated on auth.

## What you need

1. **The Postgres connection string** (this is `JOBSEARCH_DATABASE_URL`). From
   the Supabase dashboard: **Project → Settings → Database → Connection string →
   "Connection pooling" (Session pooler)**. Use the *pooler* URI (not the direct
   one) for hosted apps — it handles many short-lived connections. It looks like:

   ```
   postgresql://postgres.wbbkehjknmjvzshmsfby:YOUR-DB-PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres
   ```

   (Your project ref `wbbkehjknmjvzshmsfby` is already filled in; paste your real
   DB password.) The app reads this env var and connects to Postgres; the schema
   is already applied (migration `supabase/migrations/0001_initial_schema.sql`).

2. **A host account** (Render or Google Cloud Run below). Both are free at this
   scale. This is the one-time step nobody can do for you.

## Test the image locally first

```bash
docker build -t jobsearch .
docker run --rm -p 8484:8484 \
  -e JOBSEARCH_DATABASE_URL='postgresql://postgres.wbbkehjknmjvzshmsfby:PW@aws-0-us-east-1.pooler.supabase.com:5432/postgres' \
  jobsearch
# open http://127.0.0.1:8484
```

## Option A — Render (simplest, free)

Free web service: 750 instance-hours/month, no credit card; it **sleeps after
15 min idle** and takes ~30–60s to wake on the next request (fine for personal
use). Native "deploy on every push" GitHub integration.

1. Push this repo to GitHub (done).
2. Go to **render.com → New → Web Service**, connect your GitHub, pick this repo.
3. Render auto-detects the `Dockerfile`. Set:
   - **Instance type:** Free
   - **Environment variable** `JOBSEARCH_DATABASE_URL` = your pooler string (mark
     it secret). Render injects `PORT` automatically.
4. Create. Every `git push` to the branch now redeploys automatically.

(You can also commit a `render.yaml` blueprint so step 3 is automatic — ask and
I'll add one once a deploy branch/host is chosen.)

## Option B — Google Cloud Run (more generous free, scales to $0)

Always-free: 2M requests + 180k vCPU-seconds/month, **scales to zero** when idle
(no monthly floor). More setup: needs a GCP project with billing enabled (the
free tier covers the cost). Deploy by hand or via GitHub Actions.

One-time, by hand (`gcloud` CLI):

```bash
gcloud run deploy jobsearch \
  --source . \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars "JOBSEARCH_DATABASE_URL=postgresql://postgres.wbbkehjknmjvzshmsfby:PW@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
```

To automate it on every push, I can add a `.github/workflows/deploy.yml` that
builds and deploys to Cloud Run — you'd add a service-account key (or Workload
Identity) as a GitHub secret once.

## Keep the Supabase database from pausing

Supabase **pauses free-tier projects after ~7 days with no requests** (data is
preserved; you click "restore" to wake it). The existing daily job-search
GitHub Action will keep it warm once it writes to Postgres (Stage 4). Until
then, a tiny scheduled Action that runs `SELECT 1` every few days prevents the
pause — ask and I'll add it.

## Leanness (later optimization)

This image installs the full `requirements.txt`, including `playwright`,
`numpy`, and `scikit-learn`. The web request path doesn't need Chromium, and
scoring (sklearn/numpy) belongs in the daily worker, not the web tier. A
follow-up can split a lean web image from the worker image for faster cold
starts (see `design-deployment.md` §"Web tier"). Correct and runnable first;
optimize when cold-start latency actually matters.
