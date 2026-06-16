# Deployment & hosting cost analysis

Concrete, cost-optimized deployment design for taking the local app online as a
multi-user product. Companion to [`design-hosting.md`](design-hosting.md),
which covers *what changes* between the local app and a hosted product; this doc
covers *where to run it and what it costs*.

Target scale: ~20 users/day now, scalable later. Goal: cheapest sustainable
path with simple ops. Prices are point-in-time (researched **2026-06-16**) and
should be re-verified at signup — free-tier terms shift.

## TL;DR

- **Recommended (cheapest sustainable): a managed "indie" split — Neon +
  Fly.io + GitHub Actions + Cloudflare R2 + Cloudflare. ~$0–3/mo** at this
  scale, scales cleanly.
- **All-in on one hyperscaler costs ~$11–17/mo steady-state** — and ~90% of
  that is managed Postgres, because none of the big three autosuspend a DB to
  $0 the way Neon does (Aurora Serverless v2 excepted, with caveats). Year 1
  is ~$0–2 on AWS/Azure (12-month free Postgres); GCP has no free Postgres.
- **The real cost is not the monthly bill — it's the one-time multi-tenancy
  port** (auth + SQLite→Postgres + per-user fit table). See `design-hosting.md`.

## General architecture (cloud-agnostic)

```
                     ┌─────────────┐
    users ──HTTPS──▶ │ Cloudflare  │   free: TLS · CDN · DDoS · cache static
                     └──────┬──────┘
                            │
                    ┌───────▼─────────┐  pooled  ┌──────────────────────┐
                    │  Web tier       │◀───SQL──▶│  Managed Postgres     │
                    │  FastAPI        │          │  autosuspend at idle  │
                    │  stateless      │          └──────────┬───────────┘
                    │  scale 0→N      │                     ▲
                    └───────┬─────────┘     upsert jobs +   │ writes
                            │ PDF bytes      user_job_fit    │
                    ┌───────▼─────┐                ┌─────────┴──────────┐
                    │ Object store│                │  Scheduled worker   │
                    │ (R2/S3)     │                │  daily Playwright   │
                    └─────────────┘                │  scrape + rescore   │
                                                   └─────────────────────┘
   LOCAL-ONLY (user's own machine, never hosted):
   apply-browser autofill · LinkedIn referral discovery · Gmail OAuth token
```

Five tiers, each scale-to-zero or free at idle:

1. **Edge** — TLS, static caching, abuse absorption. Free (Cloudflare).
2. **Web tier** — stateless FastAPI; no local state, so it scales 0→N.
   Sessions are signed HttpOnly+Secure+SameSite cookies (no session store →
   scale-to-zero friendly). Lean image: **no Chromium**, sklearn/numpy
   lazy-loaded off the request path → fast cold start.
3. **Database** — managed Postgres, single source of truth, multi-tenant via
   `user_id` scoping, accessed through a connection pooler.
4. **Scheduled worker** — the Playwright pipeline, fully decoupled. Daily
   scrape → upsert the **global** `jobs` corpus → rescore each active user.
   numpy/sklearn run here, never on the web request path.
5. **Blob store** — resume PDFs + nightly DB dumps. Encrypted at rest.

### Two schema changes that make it multi-tenant

- **Move fit out of `jobs` into `user_job_fit`** `(user_id, job_id,
  fit_score, rank_score, cluster, computed_at)`, PK `(user_id, job_id)`.
  Today `jobs.fit_score/rank_score/cluster` are columns on the *global*
  posting row — a single-user assumption. Dashboard becomes
  `jobs ⋈ user_job_fit WHERE user_id = :me`. `jobs`/`job_events` and `prep_*`
  *content* tables stay global; only progress + fit are per-user.
- **SQLite → Postgres dialect port** in `db.py`: `psycopg`, `?`→`%s`,
  `AUTOINCREMENT`→`GENERATED … AS IDENTITY`, `INSERT OR REPLACE`→
  `INSERT … ON CONFLICT`, TEXT timestamps→`timestamptz`, JSON-in-TEXT→`jsonb`.

## Recommended stack (cheapest sustainable): the managed split

| Layer | Service | Now | Why |
|---|---|---|---|
| **Database** | **Neon Postgres** | **$0** | Autosuspends after 5 min (sub-second resume), 0.5 GB free that *never deletes*, built-in PgBouncer pooler. |
| **Daily worker** | **GitHub Actions** | **$0** | Already runs the Playwright scrape. ~750 min/mo ≪ 2,000 free (private) / unlimited (public). |
| **Web tier** | **Fly.io** (or Koyeb / Cloud Run for literal $0) | **$0–3** | $2–3/mo always-on 256 MB (no cold start), `fly launch` from Dockerfile. Swappable in one step. |
| **Blobs + backups** | **Cloudflare R2** | **$0** | 10 GB free, **zero egress fees**. |
| **Edge** | **Cloudflare** | **$0** | Free TLS, CDN, DDoS, caching. |
| **Ops** | **Sentry + healthchecks.io** | **$0** | Error tracking + cron dead-man's-switch. |

**Key insight:** the web host barely moves the bill ($0–3 whichever you pick)
and is trivially portable (Dockerfile + env vars). The decisions expensive to
change later are Neon (your data) and GitHub Actions (your pipeline) — optimize
those, treat the web host as interchangeable.

**Worker gotcha:** GitHub disables a `schedule:` workflow after 60 days of repo
inactivity. Today it's immune because it commits daily; once it writes to
Postgres instead, add a keepalive (heartbeat commit or API ping every ~45
days). Cron is best-effort (10–30 min jitter) — fine for a daily scrape.

### Cost-optimization levers

1. **One daily fetch shared across all users** — cost is *sublinear in users*
   (postings are global; per-profile searches dedupe).
2. **Worker on free GitHub Actions** — the heaviest component (30 min of
   Chromium) is $0, and it sidesteps serverless-Chromium pain entirely.
3. **Neon autosuspend** — the DB is $0 at idle.
4. **Lean web image** — drop Chromium, keep sklearn off the request path →
   cheap cold start → scale-to-zero (or $2–3 always-on) instead of a warm
   $30/mo instance.
5. **R2 zero-egress** — no surprise bandwidth bills.
6. **Cloudflare free tier** — CDN/TLS/DDoS for $0.
7. **Signed-cookie sessions** — no session store, fewer DB hits.

## All-in on one hyperscaler (GCP / AWS / Azure)

Cheapest credible full-stack config on each. Compute is ~free everywhere at
this scale; managed Postgres is the whole bill.

| Component | **GCP** | **AWS** | **Azure** |
|---|---|---|---|
| Web tier | Cloud Run — **$0** | Lambda container — **$0** (or Lightsail $5 flat) | Container Apps — **$0** |
| **Postgres** | Cloud SQL `f1-micro` **~$10** (no SLA) / **~$32** SLA | RDS `t4g.micro` + 20 GB **~$14** | Flexible Server `B1ms` **~$16–17** |
| Daily worker | Cloud Run Jobs — **$0** | Fargate scheduled **~$1** (Lambda's 15-min cap can't run a 30-min job) | Container Apps Jobs — **$0** |
| Blob | GCS **~$0** | S3 **~$0** | Blob **~$0** |
| Edge / TLS | Domain mapping **$0** (skip the $18/mo LB) | CloudFront **$0** (skip the $16/mo ALB) | CA ingress **$0** (skip Front Door) |
| Secrets / logs | $0 | $0 (SSM Parameter Store, not Secrets Manager) | $0 *if logs <5 GB* |
| **Free first year?** | No ($300 / 90-day credit) | **Yes** (12-mo RDS) | **Yes** (12-mo Postgres) |
| **Year-1 total** | ~$0 then ~$10 | **~$1–2/mo** | **~$0–2/mo** |
| **Steady-state total** | **~$10–11** (no SLA) / ~$32 SLA | **~$15–16** | **~$17–22** |

### Reading it

- **GCP** looks cheapest steady-state (~$10) but that's the legacy no-SLA
  `f1-micro`; SLA-backed Cloud SQL is ~$32, and there's no free year.
- **AWS** is the best single-vendor pick: free year, then ~$15/mo, mature, and
  the only native scale-to-zero escape hatch (Aurora v2 below). Avoid the two
  footguns — **NAT Gateway (~$33/mo)** and **ALB (~$16/mo)** — via public
  subnets + Lambda function URLs + CloudFront.
- **Azure** is competitive but has the most silent line-items: **Log Analytics
  ingestion** ($2.30/GB past 5 GB free) and Postgres **auto-restarts 7 days**
  after you stop it.

### Two ways to dodge the Postgres floor

1. **AWS Aurora Serverless v2 → 0 ACU.** Genuinely scales to zero on idle;
   cost approaches $0 when nobody's on, at the price of a **~15–30 s cold
   resume** + connection-retry logic. Viable for a low-traffic app whose main
   writer is the daily worker.
2. **The hybrid (real cost-optimal move):** hyperscaler *compute* (Cloud Run /
   Container Apps / Lambda — free at this scale) + *database on Neon* (free,
   autosuspends) ≈ **$0/mo with hyperscaler-grade infra**. "All on one
   provider" is precisely the expensive version — you're buying their Postgres.

## Recommendation

- **Lowest cost + simple, don't care about single-vendor →** the managed split
  (Neon + Fly + GitHub Actions + R2 + Cloudflare), ~$0–3/mo.
- **Must be all-in on one major cloud →** AWS: ~$0 year one, ~$15/mo after,
  with Aurora Serverless v2 as a path back toward $0.
- **Want one box you own →** Hetzner + Docker Compose, ~$5/mo (EU) / ~$9/mo
  (US) flat, but you own OS/DB ops.

## Scaling path

- **20 → 1k users:** web tier `min=1`; Neon → paid (~$5–19/mo). Worker still
  one daily run (sublinear). ~$15–25/mo.
- **1k → 100k:** bottleneck is *rescoring* (N resumes × corpus), not fetching.
  Fan it out (GH Actions matrix or Cloud Run Jobs), add a `rescore_queue`
  table + worker pool, Neon read replicas, partition `jobs` by date, cache hot
  dashboards. Fetch stays a single global pass; web tier autoscales (stateless).

The design survives 4 orders of magnitude because postings are global, per-user
work is cheap scoring, and everything is stateless behind managed Postgres.
