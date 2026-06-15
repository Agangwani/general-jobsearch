"""Orchestrator: per-job referral discovery.

Flow:
  1. Load the job's company + description and the user's resume.
  2. Build a role_query from the job title (de-leveled, capped to 5 keywords
     so LinkedIn's search doesn't get over-constrained).
  3. Call the LinkedIn discoverer for `company, role_query` → CandidateHits.
  4. TF-IDF score each hit against the job description and resume.
  5. Persist candidates + per-job match scores.

The actual Playwright work and the SQLite mutations both block, so callers
typically wrap this in a thread (the FastAPI route launches discovery as a
background task and polls referral_runs for completion).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .rank import rank_candidates
from .sources.linkedin import LinkedinDiscoverer, LoginRequired
from .store import (
    fail_run, finish_run, save_matches, start_run,
)

# Level words borrowed from role_profile._LEVEL_WORDS — same intent: strip
# "Senior" / "Staff" / "III" from a job title before passing to LinkedIn,
# otherwise LinkedIn ranks people who literally have "Senior" in their
# headline above the actual subject-matter experts.
_LEVEL_WORDS = frozenset({
    "senior", "sr", "jr", "junior", "lead", "staff", "principal", "distinguished",
    "associate", "entry", "mid", "level", "i", "ii", "iii", "iv", "v",
    "1", "2", "3", "4", "engineer", "developer",
})
_MAX_QUERY_WORDS = 5


def role_query_from_title(title: str) -> str:
    """A short LinkedIn keyword query distilled from the job title:
    de-leveled, lowercased, capped to the most-informative tokens. We drop
    the words 'engineer' / 'developer' from the query because almost every
    candidate already has them in their headline — they're noise."""
    tokens = re.findall(r"[a-z0-9&/+]+", title.lower())
    cleaned = [t for t in tokens if t not in _LEVEL_WORDS and len(t) > 1]
    return " ".join(cleaned[:_MAX_QUERY_WORDS])


def discover_for_job(
    conn: sqlite3.Connection,
    root: Path,
    job_id: int,
    discoverer: LinkedinDiscoverer,
) -> dict:
    """Find + rank + persist referral candidates for one job. Returns a
    summary dict suitable for logging or surfacing in the UI."""
    run_id = start_run(conn, job_id)
    try:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            fail_run(conn, run_id, f"job {job_id} not found")
            return {"job_id": job_id, "state": "error", "detail": "job not found"}

        resume_text = _load_resume(root)
        role_query = role_query_from_title(job["title"] or "")
        hits = discoverer.search(job["company"], role_query)
        scored = rank_candidates(hits, job["description"] or "", resume_text)
        saved = save_matches(conn, job_id, job["company"], scored)
        detail = (
            f"{saved} candidates ranked for {job['company']} "
            f"('{role_query}')"
        )
        finish_run(conn, run_id, detail)
        return {
            "job_id": job_id, "state": "done", "saved": saved,
            "company": job["company"], "role_query": role_query,
        }
    except LoginRequired as exc:
        fail_run(conn, run_id, str(exc))
        return {"job_id": job_id, "state": "error", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 — surface to the UI run log
        fail_run(conn, run_id, f"{type(exc).__name__}: {exc}")
        return {"job_id": job_id, "state": "error", "detail": str(exc)[:300]}


def _load_resume(root: Path) -> str:
    """Same fallback chain as the resume route — real resume preferred,
    sample as a last resort so discovery still produces *some* ranking on a
    fresh checkout."""
    for name in ("resume.txt", "sample_resume.txt"):
        path = root / "data" / name
        if path.exists():
            return path.read_text()
    return ""
