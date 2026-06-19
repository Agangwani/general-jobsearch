# Container image for the jobsearch web UI, sized for an AWS App Runner MVP.
#
# Notes:
# - Binds 0.0.0.0:8080 (App Runner's default port) with --allow-remote, since
#   the app otherwise refuses any non-loopback bind.
# - A password gate is enforced at runtime via JOBSEARCH_BASIC_AUTH_PASSWORD
#   (set in the App Runner service config) so the public URL isn't wide open.
# - The Playwright *package* is installed (it's an import-time dependency) but
#   the Chromium *binary* is intentionally not downloaded: the dashboard UI and
#   API-based boards work without it, and browser-scraped boards / auto-fill
#   degrade gracefully. This keeps the image small and the build fast.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Runtime dirs (the SQLite DB and uploaded resume live here; ephemeral on
# App Runner — re-upload after a redeploy/restart).
RUN mkdir -p data reports

EXPOSE 8080

CMD ["python", "-m", "jobsearch", "ui", "--host", "0.0.0.0", "--port", "8080", "--allow-remote"]
