# Deploying the web app the cheapest credible way (CLI-only)

A copy-pasteable, CLI-driven guide to host this app's Docker container for as
close to **$0/month** as is honestly possible in 2026. Companion to
[`deploy.md`](deploy.md) (the broader free-host walkthrough) and
[`design-hosting-progress.md`](design-hosting-progress.md) (the staged plan).
Read those for the auth/data context; this doc is the lean, exact playbook.

> **Recommendation up front:** **Google Cloud Run**, source-deployed via
> `gcloud`. It **scales to zero**, so an idle personal app costs **$0/mo** and
> stays inside the always-free tier even with daily use. The only real cost is a
> 3–5 s cold start on the first request after idle. If you would rather pay a
> flat **~€3.79–4.49/mo ($4–5)** to *never* see a cold start, use the
> **Hetzner VPS + Caddy** runner-up at the bottom. Both keep the database on
> Supabase's free Postgres — that is what makes either option cheap.

## Why this is cheap at all: the database is already external

This app's data lives in **Supabase managed Postgres** (free tier), reached at
runtime through `JOBSEARCH_DATABASE_URL`. We are only hosting a **stateless**
FastAPI/uvicorn container — no database to provision, no disk to pay for. So the
"hosting bill" is just compute for a low-traffic personal web server, which on a
scale-to-zero platform rounds to nothing.

The image (`Dockerfile` at the repo root) runs:

```
python -m jobsearch ui --host 0.0.0.0 --port $PORT --allow-remote
```

a single long-running server on the platform-injected `$PORT`. It is built on
`python:3.12-slim` and bundles numpy / scikit-learn / playwright, so it is
**moderately large** (hundreds of MB). That matters only for cold-start and
push time — see [Gotchas](#gotchas). Note the image **intentionally ships no
Chromium**: the browser-driven features (auto-fill, LinkedIn referral
discovery) are **local-only and never run server-side**, so they cost nothing
to host and need no extra setup.

## The options, compared (verified June 2026)

| Option | Rough real cost/mo | Idles to $0? | Cold start | HTTPS |
|---|---|---|---|---|
| **Google Cloud Run** ⭐ | **$0** (within always-free tier) | **Yes** — true scale-to-zero | ~3–5 s on first request after idle (Python + DB connect) | **Automatic** on the `*.run.app` URL |
| **Render** free web service | $0 | Yes, but by **sleeping** | ~30–60 s to wake from sleep | Automatic on `*.onrender.com` |
| **Fly.io** | **~$2/mo minimum**, realistically $5+ | No (always-on Machine) | None when warm | Automatic |
| **Hetzner VPS + Caddy** | **~€3.79–4.49 (~$4–5)** flat | No (always-on) | **None** — always warm | Automatic via Caddy + Let's Encrypt |

Notes that drive the choice:

- **Cloud Run** always-free tier: **180,000 vCPU-seconds**, **360,000
  GiB-seconds**, and **2,000,000 requests** per month, renewing monthly and
  never expiring. A personal app that's idle most of the day stays comfortably
  inside it → **$0**. You are billed for idle time **only if** you set
  `--min-instances ≥ 1`, which we deliberately do **not**.
  ([Cloud Run pricing](https://cloud.google.com/run/pricing))
- **Render** free tier is genuinely $0 and the simplest, but it **sleeps after
  ~15 min idle** and takes ~30–60 s to wake — a worse first-request experience
  than Cloud Run's few seconds, for the same $0. Good fallback, not the pick.
- **Fly.io is no longer free for new accounts** — the permanent free tier was
  removed in late 2024; new accounts get only a short trial / small credit and
  then pay per-second. A minimal always-on Machine is ~$1.94–2/mo, realistically
  $5+ with egress. Not cheaper than Cloud Run's $0, so it's not recommended
  here. ([Fly pricing](https://fly.io/pricing/),
  [free-tier-died analysis](https://expresstech.io/7-fly-io-alternatives-in-2026-real-pricing-after-the-free-tier-died/))
- **Hetzner** is the cheapest *flat* always-on box: **CAX11 (ARM) €3.79/mo** or
  **CX22 (x86) €4.49/mo**, each with 20 TB traffic and an IPv4. No cold starts,
  but it never drops to $0 and you own patching/uptime. Best when you'll hit it
  often enough that cold starts annoy you.
  ([Hetzner cost-optimized](https://www.hetzner.com/cloud/cost-optimized))

## The pick: Google Cloud Run (and why)

For a **low-traffic, personal-scale** app whose data already lives elsewhere,
**truly $0 at idle beats a flat ~$4/mo** — you only pay when you're actually
using it, and at this scale that's inside the free tier. Cloud Run also gives
**automatic HTTPS** on its managed `*.run.app` domain (the app sets `Secure`
cookies via `JOBSEARCH_HTTPS_ONLY=1`, which needs HTTPS), deploys **straight
from this repo's `Dockerfile` with one command** (no registry juggling), and
manages secrets with the platform's Secret Manager so no secret ever touches
the repo or your shell history.

The one tradeoff is a **3–5 s cold start** on the first hit after the app has
been idle (Python import chain + Postgres connect). For a personal tool that's
fine, and `--cpu-boost` softens it. If that's unacceptable, jump to the
[Hetzner runner-up](#runner-up-hetzner-vps--caddy-flat--4mo-no-cold-starts)
— a flat ~$4/mo box that's always warm.

---

## Cloud Run — exact end-to-end CLI

Everything below is CLI. The **only** unavoidable one-time browser step is
creating/selecting a Google Cloud **billing account** (Google requires it even
though the free tier means you won't be charged at this scale); the CLI
alternative for *linking* an existing billing account is given inline.

### 0. Prerequisites (one-time)

```bash
# Install the gcloud CLI (Debian/Ubuntu shown; see cloud.google.com/sdk/docs/install for macOS/other).
curl -sSL https://sdk.cloud.google.com | bash
exec -l $SHELL                      # reload shell so `gcloud` is on PATH
gcloud components update

# Authenticate.
gcloud auth login

# Create (or pick) a project. IDs are globally unique; change the suffix.
gcloud projects create jobsearch-app-2026 --name="jobsearch"
gcloud config set project jobsearch-app-2026

# Link a billing account (required even for the free tier).
# List billing accounts you can already see:
gcloud billing accounts list
# Link one to the project (replace XXXXXX-XXXXXX-XXXXXX with an ID from above):
gcloud billing projects link jobsearch-app-2026 \
  --billing-account=XXXXXX-XXXXXX-XXXXXX
# ^ If you have NO billing account yet, that is the single web step:
#   create one at https://console.cloud.google.com/billing , then run the link command above.

# Enable the APIs this deploy uses (Cloud Run, Cloud Build, Artifact Registry, Secret Manager).
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

# Pick a region once and reuse it everywhere below.
gcloud config set run/region us-east1
```

### 1. Create the secrets (never in the repo)

Store each secret in **Secret Manager**; Cloud Run reads them at runtime so they
never appear in `gcloud` flags, the image, or your shell history file. Pipe the
value from stdin with `--data-file=-`:

```bash
# Supabase Postgres pooler URI (Session pooler — see deploy.md for where to copy it).
printf '%s' 'postgresql://postgres.YOURPROJECTREF:YOUR-DB-PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres' \
  | gcloud secrets create JOBSEARCH_DATABASE_URL --data-file=-

# Supabase project URL.
printf '%s' 'https://YOURPROJECTREF.supabase.co' \
  | gcloud secrets create SUPABASE_URL --data-file=-

# Supabase anon / publishable key (turns on the login wall).
printf '%s' 'YOUR-SUPABASE-ANON-KEY' \
  | gcloud secrets create SUPABASE_ANON_KEY --data-file=-

# Session signing secret — generate a long random one.
printf '%s' "$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  | gcloud secrets create JOBSEARCH_SESSION_SECRET --data-file=-
```

Grant Cloud Run's **runtime service account** read access to each secret. By
default that account is `PROJECT_NUMBER-compute@developer.gserviceaccount.com`:

```bash
PROJECT_ID="$(gcloud config get-value project)"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for S in JOBSEARCH_DATABASE_URL SUPABASE_URL SUPABASE_ANON_KEY JOBSEARCH_SESSION_SECRET; do
  gcloud secrets add-iam-policy-binding "$S" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor"
done
```

### 2. Build, push, and deploy — one command, straight from the Dockerfile

`--source .` makes Cloud Build build this repo's `Dockerfile`, push the image to
Artifact Registry, and deploy it. We map the secrets to env vars with
`--set-secrets ENV=SECRET:VERSION`, set the plain (non-secret)
`JOBSEARCH_HTTPS_ONLY=1`, and let Cloud Run inject `$PORT` automatically (do
**not** set `PORT` yourself).

```bash
gcloud run deploy jobsearch \
  --source . \
  --allow-unauthenticated \
  --cpu-boost \
  --memory 1Gi \
  --timeout 60 \
  --set-env-vars "JOBSEARCH_HTTPS_ONLY=1" \
  --set-secrets "JOBSEARCH_DATABASE_URL=JOBSEARCH_DATABASE_URL:latest,SUPABASE_URL=SUPABASE_URL:latest,SUPABASE_ANON_KEY=SUPABASE_ANON_KEY:latest,JOBSEARCH_SESSION_SECRET=JOBSEARCH_SESSION_SECRET:latest"
```

Why these flags:
- `--allow-unauthenticated` — let the public reach it; the app's **own
  Supabase login wall** is the gate (signups are owner-gated — see
  `deploy.md`). Without this flag Cloud Run's IAM would block all browsers.
- `--cpu-boost` — temporarily doubles CPU during startup to shrink the cold
  start; **no steady-state cost**.
- `--memory 1Gi` — headroom for the numpy/sklearn import chain on first request.
- `--timeout 60` — request timeout; the default 300 s is also fine.
- **Scale-to-zero is the default** (`--min-instances 0`), which is exactly what
  keeps idle cost at $0 — don't override it.

On success the CLI prints the **Service URL** (`https://jobsearch-...run.app`)
— HTTPS is already terminated for you. Open it and log in.

### 3. HTTPS

Nothing to do — the `*.run.app` URL is HTTPS by default, so the app's `Secure`
cookies (`JOBSEARCH_HTTPS_ONLY=1`) work immediately. (A custom domain is
optional and not needed to be cheap; map one later with
`gcloud beta run domain-mappings create --service jobsearch --domain app.example.com`.)

### 4. Redeploy after a code change

Re-run the same deploy command — it rebuilds from source and rolls out a new
revision with zero downtime. Env/secret mappings persist across deploys, so the
short form is enough:

```bash
gcloud run deploy jobsearch --source . --allow-unauthenticated
```

To rotate a secret value, add a new version and redeploy (Cloud Run pins env
secrets per revision, so a redeploy is required to pick it up):

```bash
printf '%s' 'NEW-VALUE' | gcloud secrets versions add JOBSEARCH_SESSION_SECRET --data-file=-
gcloud run deploy jobsearch --source . --allow-unauthenticated
```

### 5. Logs

```bash
# Tail live logs:
gcloud beta run services logs tail jobsearch

# Or read the most recent entries:
gcloud run services logs read jobsearch --limit 100
```

### 6. Tear down (stop all charges)

```bash
# Delete the service:
gcloud run services delete jobsearch --quiet

# Delete the secrets:
for S in JOBSEARCH_DATABASE_URL SUPABASE_URL SUPABASE_ANON_KEY JOBSEARCH_SESSION_SECRET; do
  gcloud secrets delete "$S" --quiet
done

# Nuke everything (project, built images, all of it) — the cleanest teardown:
gcloud projects delete jobsearch-app-2026
```

> Note: your **Supabase data is untouched** by any of the above — it lives in
> your separate Supabase project.

---

## Runner-up: Hetzner VPS + Caddy (flat ~$4/mo, no cold starts)

Pick this when you want a box that's **always warm** (zero cold start) for a
predictable **~€3.79/mo (CAX11, ARM)** or **€4.49/mo (CX22, x86)**, and you're
OK owning OS patching. Caddy gives **automatic Let's Encrypt HTTPS** from a
one-line config. **You need a domain name** pointed at the server's IP (Caddy
provisions the certificate for that hostname; Let's Encrypt won't issue for a
bare IP).

```bash
# 1. Install the Hetzner CLI and authenticate (create an API token once in the
#    Hetzner Cloud console → Security → API tokens; the rest is CLI).
#    macOS: brew install hcloud   |   others: see github.com/hetznercloud/cli releases
hcloud context create jobsearch          # paste the API token when prompted

# 2. Upload your SSH key and create the cheapest server (Ubuntu 24.04, ARM CAX11).
hcloud ssh-key create --name mykey --public-key-from-file ~/.ssh/id_ed25519.pub
hcloud server create \
  --name jobsearch \
  --type cax11 \
  --image ubuntu-24.04 \
  --ssh-key mykey

# 3. Get the IP, then point an A record for app.example.com at it (at your DNS host).
hcloud server ip jobsearch

# 4. SSH in and install Docker + the compose plugin.
ssh root@$(hcloud server ip jobsearch) '
  apt-get update && apt-get install -y docker.io docker-compose-v2 git &&
  systemctl enable --now docker
'
```

On the server, put the repo somewhere (`git clone` your fork) and add these two
files next to the repo's `Dockerfile`:

`Caddyfile` — auto-HTTPS + reverse proxy to the app container (replace the
domain and email):

```
app.example.com {
    reverse_proxy jobsearch:8484
    tls you@example.com
}
```

`compose.yaml` — build the app image, run Caddy in front; secrets come from an
untracked `.env` file (never commit it):

```yaml
services:
  jobsearch:
    build: .
    environment:
      PORT: "8484"
      JOBSEARCH_HTTPS_ONLY: "1"
      JOBSEARCH_DATABASE_URL: ${JOBSEARCH_DATABASE_URL}
      SUPABASE_URL: ${SUPABASE_URL}
      SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}
      JOBSEARCH_SESSION_SECRET: ${JOBSEARCH_SESSION_SECRET}
    restart: unless-stopped

  caddy:
    image: caddy:2
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data        # persists certs across restarts — do NOT skip
      - caddy_config:/config
    restart: unless-stopped

volumes:
  caddy_data:
  caddy_config:
```

Then, on the server:

```bash
# Write secrets to an untracked .env (chmod 600); compose reads ${VARS} from it.
cat > .env <<'EOF'
JOBSEARCH_DATABASE_URL=postgresql://postgres.YOURPROJECTREF:PW@aws-0-us-east-1.pooler.supabase.com:5432/postgres
SUPABASE_URL=https://YOURPROJECTREF.supabase.co
SUPABASE_ANON_KEY=YOUR-SUPABASE-ANON-KEY
JOBSEARCH_SESSION_SECRET=replace-with-a-long-random-string
EOF
chmod 600 .env

docker compose up -d --build          # build + start; Caddy auto-fetches HTTPS cert

# Redeploy on change:
git pull && docker compose up -d --build

# Logs:
docker compose logs -f jobsearch

# Tear down (deletes the server and stops all billing):
exit
hcloud server delete jobsearch
```

Caddy obtains and auto-renews the TLS certificate for `app.example.com` on first
boot — the persisted `caddy_data` volume keeps it across restarts so you don't
re-request a cert (and risk Let's Encrypt rate limits) on every reboot.

---

## Cost estimate (verified) and gotchas

### Cost estimate

| Component | Cloud Run pick | Hetzner runner-up |
|---|---|---|
| App compute | **$0** (within always-free tier at personal scale) | **€3.79–4.49 (~$4–5)** flat |
| Database (Supabase Postgres) | **$0** (free tier) | **$0** (free tier) |
| Daily worker (GitHub Actions) | **$0** (free minutes) | **$0** |
| HTTPS | **$0** (managed) | **$0** (Let's Encrypt via Caddy) |
| Domain (optional) | $0 on `*.run.app` | ~$10/yr if you buy one (required here) |
| **Total** | **≈ $0/mo** | **≈ $4–5/mo** |

Sources (verified June 2026):
[Cloud Run pricing](https://cloud.google.com/run/pricing) ·
[Fly pricing](https://fly.io/pricing/) ·
[Fly free-tier-died analysis](https://expresstech.io/7-fly-io-alternatives-in-2026-real-pricing-after-the-free-tier-died/) ·
[Hetzner cost-optimized](https://www.hetzner.com/cloud/cost-optimized) ·
[Cloud Run startup CPU Boost](https://cloud.google.com/blog/products/serverless/announcing-startup-cpu-boost-for-cloud-run--cloud-functions)

### Gotchas

- **Cold start (Cloud Run):** a Python service that connects to a DB on startup
  typically cold-starts in **~3–5 s** after idle; `--cpu-boost` (set above)
  trims it. To eliminate it you'd set `--min-instances 1`, but that bills memory
  ~24/7 and breaks the $0 story — don't, unless you decide the snappiness is
  worth a few dollars a month. (At that point the Hetzner box is the better deal
  anyway, since it's always warm.)
- **Image size:** the image bundles numpy / scikit-learn / playwright, so it's
  hundreds of MB. That lengthens the **build/push** and the cold-start pull, not
  the steady-state cost. A later optimization (see
  [`deploy.md`](deploy.md) §Leanness and `design-deployment.md`) splits a lean
  web image — no Chromium, sklearn off the request path — for faster cold
  starts. Correct and runnable first; optimize when latency actually bites.
- **Playwright/browser features are local-only:** the image ships **no
  Chromium** (`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` in the `Dockerfile`), and the
  auto-fill / referral-discovery features don't run server-side. So you do
  **not** need extra memory, system libraries, or a bigger instance for them —
  another reason the cheap tiers are enough.
- **Supabase free-tier pausing:** Supabase **pauses a free project after ~7
  days with no requests** (data is preserved; you click restore). Whichever host
  you pick, keep the DB warm — the simplest fix is the existing daily
  GitHub-Actions worker writing to Postgres, or a tiny scheduled `SELECT 1`. See
  [`deploy.md`](deploy.md) §"Keep the Supabase database from pausing".
- **Use the Supabase *pooler* (Session pooler) URI**, not the direct connection
  string, in `JOBSEARCH_DATABASE_URL` — it handles the many short-lived
  connections a web tier opens. (Details in `deploy.md`.)
- **HTTPS is mandatory:** the app sets `Secure` session cookies via
  `JOBSEARCH_HTTPS_ONLY=1`, so login only works over HTTPS. Cloud Run's
  `*.run.app` is HTTPS by default; on the VPS, Caddy provides it — just don't
  set `JOBSEARCH_HTTPS_ONLY=1` while testing over plain `http://`.
- **Don't set `PORT` yourself on Cloud Run** — the platform injects it and the
  container already honors `$PORT`. Setting it manually can conflict with the
  platform's contract.
- **Billing account is unavoidable on GCP** — Google requires one even though
  the free tier means $0 at this scale. It's the one web step; everything else
  is CLI.
