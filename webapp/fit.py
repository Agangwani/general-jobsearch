"""Per-user résumé-fit scoring (Stage 2b parts 4a/4b).

Scores a user's résumé against their active jobs in the database and writes the
result onto their own job rows (jobs are per-user — see Stage 2a — so
fit_score/rank_score/cluster on a row already belong to exactly one account).
Invoked three ways:

- on résumé **upload** (immediate feedback for the person who just uploaded),
- on the manual **"refresh matches"** action,
- by the **daily worker** for every active user, after the ingest of fresh jobs
  (``python -m jobsearch rescore-users``).

The corpus is the user's active jobs in the DB. That's a subset of the
pipeline's full fetched corpus (which the owner's ingest still scores at higher
fidelity into the ``local`` rows — rescore skips 'local' for exactly that
reason), but it grows as jobs accumulate and needs no re-fetch, so it's the
right trade-off for on-demand and per-user re-scoring.
"""

from __future__ import annotations

from datetime import datetime

from jobsearch.models import JobPosting
from jobsearch.scoring import apply_recency, score_jobs

from . import db


def _parse_dt(value):
    """Parse jobs.posted_at (ISO datetime or bare date, possibly None) for
    recency weighting. Unparseable/absent → None (treated as unknown-age)."""
    if not value:
        return None
    for text in (value, value[:10]):
        try:
            return datetime.fromisoformat(text)
        except (ValueError, TypeError):
            continue
    return None


def _load_corpus(conn, user_id: str) -> list[tuple[int, JobPosting]]:
    """This user's active jobs as (db_id, JobPosting) pairs for scoring. The
    synthetic key (source:company:db_id) is unique per row, which is all
    score_jobs needs."""
    rows = conn.execute(
        "SELECT id, source, company, title, location, description, posted_at "
        "FROM jobs WHERE user_id = ? AND is_active = 1", (user_id,)).fetchall()
    out = []
    for r in rows:
        out.append((r["id"], JobPosting(
            company=r["company"], title=r["title"], location=r["location"] or "",
            url="", job_id=str(r["id"]), description=r["description"] or "",
            posted_at=_parse_dt(r["posted_at"]), source=r["source"] or "db")))
    return out


def rescore_user(conn, user_id: str, resume_text: str) -> int:
    """Score ``resume_text`` against the user's active jobs and write the
    result back onto their job rows. Returns the number of jobs scored. A
    blank résumé or an empty corpus is a no-op (returns 0)."""
    resume_text = (resume_text or "").strip()
    if not resume_text:
        return 0
    corpus = _load_corpus(conn, user_id)
    if not corpus:
        return 0
    jobs = [jp for _, jp in corpus]
    # score_jobs mutates fit_score + cluster in place; apply_recency sets
    # rank_score in place (it also sorts `jobs`, but the corpus pairs still hold
    # the same mutated objects, so we read each job's fit back by identity).
    score_jobs(resume_text, jobs, corpus=jobs)
    apply_recency(jobs)
    for db_id, jp in corpus:
        conn.execute(
            "UPDATE jobs SET fit_score = ?, rank_score = ?, cluster = ? "
            "WHERE id = ?",
            (jp.fit_score, jp.rank_score, jp.cluster, db_id))
    conn.commit()
    return len(corpus)


def rescore_all_active_users(conn) -> dict[str, int]:
    """Re-score every user who has a stored résumé — the daily worker's job,
    run after ingesting fresh postings. Skips 'local' (see users_with_resume).
    Returns {user_id: jobs_scored}."""
    out: dict[str, int] = {}
    for uid in db.users_with_resume(conn):
        out[uid] = rescore_user(conn, uid, db.get_resume(conn, uid) or "")
    return out
