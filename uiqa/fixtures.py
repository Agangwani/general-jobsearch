"""Deterministic seed data so every interesting route is reachable in a run.

A fresh DB leaves /jobs/{id}, /clusters/job/{id}, and /jobs/{id}/referrals with
nothing to open, so the explorer can't reach them. This module seeds a handful
of jobs (with the application rows the UI needs) and a matching
reports/clustering.json — built to the exact shape webapp/clusters.py and the
cluster_job template expect, so the fit-map pages render their *real* populated
state instead of an empty-state we'd misread as a bug.

Everything here is fake-but-valid and self-contained; no network, no real
companies' data.
"""

from __future__ import annotations

import json
from pathlib import Path

from webapp import db

# A small, varied set: different companies, fits, a near-miss, and one with no
# URL (exercises the "no apply button" branch). Companies match canonical keys
# that have bundled LeetCode questions so the company pages show content.
SEED_JOBS: list[dict] = [
    {
        "key": "greenhouse:Amazon:1001", "source": "greenhouse", "company": "Amazon",
        "title": "Senior Software Engineer, Payments",
        "location": "New York, NY", "url": "https://example.com/amazon/1001",
        "description": ("Build high-throughput payment services in a distributed "
                        "environment. Python, Go, Kubernetes, AWS. 8+ years."),
        "posted_at": "2026-06-18", "fit_score": 92.0, "rank_score": 70.0,
        "cluster": 0, "filter_reason": "", "validation": "verified",
        "validation_note": "live + senior + NYC", "new": 1,
    },
    {
        "key": "lever:Meta:1002", "source": "lever", "company": "Meta",
        "title": "Software Engineer, Infrastructure",
        "location": "New York, NY", "url": "https://example.com/meta/1002",
        "description": ("Own backend infrastructure for a large-scale platform. "
                        "Distributed systems, reliability, performance."),
        "posted_at": "2026-06-15", "fit_score": 81.0, "rank_score": 55.0,
        "cluster": 0, "filter_reason": "", "validation": "", "new": 0,
    },
    {
        "key": "ashby:Stripe:1003", "source": "ashby", "company": "Stripe",
        "title": "Engineer, Payments Platform",
        "location": "Remote - US", "url": "https://example.com/stripe/1003",
        "description": "Unleveled posting. Payments platform, API design, 5+ years.",
        "posted_at": "2026-06-12", "fit_score": 88.0, "rank_score": 40.0,
        "cluster": 1, "filter_reason": "UNLEVELED_TITLE",
        "validation": "mismatch", "validation_note": "remote pool, level unclear",
        "new": 1,
    },
    {
        "key": "greenhouse:Datadog:1004", "source": "greenhouse", "company": "Datadog",
        "title": "Senior Software Engineer, Observability",
        "location": "New York, NY", "url": "",  # no URL → apply button suppressed
        "description": "Observability pipelines at scale. Go, metrics, tracing.",
        "posted_at": "2026-06-10", "fit_score": 63.0, "rank_score": 30.0,
        "cluster": 2, "filter_reason": "", "validation": "", "new": 0,
    },
]


def clustering_for(jobs: list[dict]) -> dict:
    """A reports/clustering.json matching the seeded jobs, complete enough for
    both /clusters (map points) and /clusters/job/{id} (full breakdown)."""
    params = {"scored": len(jobs), "cosine_weight": 0.85,
              "cluster_weight": 0.15, "scale": 1.08}
    cluster_defs = [
        {"id": 0, "centroid": {"x": -0.6, "y": 0.4}, "label": "backend/platform",
         "terms": ["backend", "distributed", "payments", "api", "kubernetes"],
         "affinity": 0.71, "size": 2, "is_resume_cluster": True},
        {"id": 1, "centroid": {"x": 0.5, "y": 0.5}, "label": "payments/api",
         "terms": ["payments", "api", "platform", "billing"],
         "affinity": 0.55, "size": 1, "is_resume_cluster": False},
        {"id": 2, "centroid": {"x": 0.2, "y": -0.6}, "label": "observability",
         "terms": ["observability", "metrics", "tracing", "go"],
         "affinity": 0.33, "size": 1, "is_resume_cluster": False},
    ]
    # Spread points deterministically around their cluster centroid.
    xs = {0: (-0.7, 0.45), 1: (0.55, 0.5), 2: (0.2, -0.65)}
    job_entries = []
    for rank, j in enumerate(jobs, start=1):
        cx, cy = xs.get(j["cluster"], (0.0, 0.0))
        cosine = round(0.4 + j["fit_score"] / 250, 3)
        affinity = round(cluster_defs[j["cluster"]]["affinity"], 3)
        raw = round(params["cosine_weight"] * cosine
                    + params["cluster_weight"] * affinity, 3)
        job_entries.append({
            "key": j["key"], "company": j["company"], "title": j["title"],
            "cluster": j["cluster"], "fit": float(j["fit_score"]),
            "near_miss": bool(j["filter_reason"]),
            "x": round(cx + 0.03 * rank, 3), "y": round(cy - 0.02 * rank, 3),
            "rank": rank, "cosine": cosine, "affinity": affinity, "raw": raw,
            "cosine_contribution": round(params["cosine_weight"] * cosine, 3),
            "cluster_contribution": round(params["cluster_weight"] * affinity, 3),
            "match_terms": [["payments", 0.21], ["distributed", 0.14],
                            ["api", 0.11], ["python", 0.08]],
            "top_terms": ["payments", "backend", "platform", "api"],
        })
    return {"params": params, "clusters": cluster_defs, "jobs": job_entries,
            "resume": {"x": -0.65, "y": 0.42}}


def seed(root: Path, db_path: Path, jobs: list[dict] | None = None) -> dict[str, int]:
    """Insert the seed jobs and write the matching clustering.json. Returns the
    map of job key → DB id so callers know which sub-pages exist."""
    jobs = jobs or SEED_JOBS
    conn = db.connect(db_path)
    try:
        for rec in jobs:
            db.upsert_job(conn, rec)
        # Move one job into "applied" so the In-progress/Applied stacks and the
        # status-filtered views are non-empty too.
        applied = conn.execute(
            "SELECT a.id FROM applications a JOIN jobs j ON j.id = a.job_id "
            "WHERE j.key = ?", (jobs[1]["key"],)).fetchone()
        if applied:
            db.set_application_status(conn, applied["id"], "applied",
                                      detail="seeded", via="uiqa")
        ids = {row["key"]: row["id"]
               for row in conn.execute("SELECT key, id FROM jobs").fetchall()}
    finally:
        conn.close()

    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "clustering.json").write_text(json.dumps(clustering_for(jobs)))
    return ids
