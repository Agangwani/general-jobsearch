# Run the jobsearch web app on any managed container host (Render, Google Cloud
# Run, Fly, Railway, a VPS …). The app reads JOBSEARCH_DATABASE_URL at runtime
# and connects to Postgres (Supabase); with it unset it would fall back to local
# SQLite inside the container, which is ephemeral — so always set it in hosting.
# Full walkthrough: docs/deploy.md.
#
# NOTE: the browser-driven features (auto-fill apply, LinkedIn referral
# discovery) are local-only by design and are NOT part of a hosted deployment —
# this image intentionally ships no Chromium.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Belt-and-suspenders: never let any transitive Playwright step pull browser
    # binaries into this image (they aren't used server-side).
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app

# Dependencies first, so the (slow) pip layer is cached across code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code (everything not excluded by .dockerignore).
COPY . .

# Managed hosts inject the listening port via $PORT; default to 8484 so a plain
# `docker run -p 8484:8484` works locally too.
ENV PORT=8484
EXPOSE 8484

# `--allow-remote` is required to bind a non-loopback address; the app refuses
# otherwise. ⚠️ The UI is UNAUTHENTICATED today — do not expose this publicly
# until the auth stage lands (docs/design-hosting-progress.md, Stage 2).
CMD ["sh", "-c", "python -m jobsearch ui --host 0.0.0.0 --port ${PORT:-8484} --allow-remote"]
