"""Read the per-run K-means clustering explanation (reports/clustering.json,
written by the pipeline) for the cluster-visualization views.

The file is a snapshot of the *latest* run's fit scoring: a 2-D map of the
TF-IDF space, one entry per cluster (topic terms + the resume's affinity), and
a per-job breakdown of the cosine + cluster math that produced each fit score.
It's local-only (gitignored under reports/), exactly like latest.json.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_clustering(root: Path, track: str = "main") -> dict | None:
    """The latest run's fit-map snapshot for a track. The main pipeline writes
    reports/clustering.json; the startup pipeline writes
    reports/startups/clustering.json."""
    path = (root / "reports" / "startups" / "clustering.json" if track == "startups"
            else root / "reports" / "clustering.json")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return None


def job_breakdown(clustering: dict | None, key: str) -> dict | None:
    """The per-job score breakdown for a posting, looked up by its pipeline
    key (source:company:job_id). None if this job wasn't in the latest run."""
    if not clustering:
        return None
    return next((j for j in clustering.get("jobs", []) if j.get("key") == key), None)


def cluster_by_id(clustering: dict | None, cluster_id) -> dict | None:
    if not clustering or cluster_id is None:
        return None
    return next((c for c in clustering.get("clusters", []) if c.get("id") == cluster_id), None)


def map_points(clustering: dict | None, ids_by_key: dict[str, int] | None = None) -> list[dict]:
    """Slim per-job points for the scatter map — omits the per-job match_terms
    bulk, and attaches the DB job id (when known) so a point links to its
    breakdown page."""
    if not clustering:
        return []
    ids_by_key = ids_by_key or {}
    points = []
    for j in clustering.get("jobs", []):
        if j.get("x") is None or j.get("y") is None:
            continue
        points.append({
            "key": j["key"],
            "id": ids_by_key.get(j["key"]),
            "company": j["company"],
            "title": j["title"],
            "cluster": j["cluster"],
            "fit": j["fit"],
            "near_miss": j.get("near_miss", False),
            "x": j["x"],
            "y": j["y"],
        })
    return points
