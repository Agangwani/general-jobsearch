#!/usr/bin/env bash
# One-command setup + launch. Usage:
#   ./setup.sh          → install everything, start the web UI (http://127.0.0.1:8484)
#   ./setup.sh run      → install everything, run the daily pipeline instead
# Re-running is safe: each step is idempotent and skipped when already done.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "· creating virtualenv (.venv)…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "· installing dependencies…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Headless Chromium for the browser-scraped boards (~150 MB, one-time).
# The pipeline degrades gracefully without it — API boards still work.
if ! python -m playwright install chromium >/dev/null 2>&1; then
  echo "  (playwright browser download failed — browser-scraped boards will be"
  echo "   skipped; rerun ./setup.sh on a network that allows the download)"
fi

mkdir -p data reports   # runtime dirs; SQLite DB auto-creates on first launch

cmd="${1:-ui}"; shift || true
echo "· starting: python -m jobsearch ${cmd}"
exec python -m jobsearch "${cmd}" "$@"
