"""uiqa — an agent-driven UI exploration & QA harness for the jobsearch web app.

This package is the deterministic "hands and eyes" that Claude sub-agents drive
to test the FastAPI UI like a human would. It boots the app on an ephemeral port
against an isolated, persona-seeded database, drives a real headless Chromium via
Playwright, and captures everything that could signal a bug: browser console
errors, uncaught JS exceptions, failed/4xx/5xx network responses, *server-side
tracebacks*, navigation status, and screenshots.

Three layers sit on top of it (see docs/design-ui-qa-swarm.md):

  Stage 1  Explore   — a deterministic crawler indexes every actionable element
                       on every route, and `ui-explorer` sub-agents drive the
                       harness through intuitive, human-like journeys.
  Stage 2  Validate  — `ui-validator` sub-agents replay each candidate finding
                       and classify it (confirmed / works-as-intended / flaky).
  Stage 3  Fix       — `ui-fixer` sub-agents fix confirmed bugs and open PRs.

The harness is deliberately scriptable (`python -m uiqa ...`, JSON in/out) so the
agents act on structured results and every exploration is reproducible: a
scenario file *is* the repro, and Stage 2 replay just re-runs it.
"""

from __future__ import annotations

__version__ = "0.1.0"
