"""Tests for the fit-clustering visualization: the per-run explanation emitted
by score_jobs, the report writer that persists it, and the webapp views that
render it. Everything runs offline against synthetic postings / a temp DB."""

import json

import pytest

from jobsearch.models import JobPosting
from jobsearch.report import write_clustering
from jobsearch.scoring import score_jobs

RESUME = ("Senior backend engineer: Python microservices on AWS Lambda and "
          "DynamoDB, Kafka event streaming, distributed systems, observability, "
          "fraud detection, payments platform.")
BACKEND = ("Build Python backend microservices on AWS Lambda and DynamoDB. "
           "Kafka, distributed systems, observability, payments and fraud.")
FRONTEND = ("Craft React and TypeScript user interfaces. CSS animation, design "
            "systems, accessibility, Figma, component libraries, storybook.")


def make_jobs():
    jobs = []
    for i in range(6):
        jobs.append(JobPosting(company=f"Back{i % 2}", title="Senior Software Engineer, Platform",
                               location="New York", url="", job_id=f"b{i}",
                               description=BACKEND + f" variant {i}"))
    for i in range(6):
        jobs.append(JobPosting(company=f"Front{i % 2}", title="Senior Software Engineer, Web UI",
                               location="New York", url="", job_id=f"f{i}",
                               description=FRONTEND + f" variant {i}"))
    return jobs


# ----------------------------------------------------------------- scoring ---
def test_explanation_breakdown_matches_assigned_scores():
    jobs = make_jobs()
    scored, topics, expl = score_jobs(RESUME, jobs, clusters=2, corpus=jobs,
                                      return_topics=True, return_explanation=True)
    p = expl["params"]
    assert p["n_clusters"] == 2 and p["scored"] == len(jobs)
    assert 0 < p["cosine_weight"] < 1 and p["has_map"] is True

    # Clusters partition the scored jobs; exactly one is the resume's home;
    # every cluster carries human-readable topic terms and a non-negative affinity.
    assert len(expl["clusters"]) == 2
    assert sum(c["size"] for c in expl["clusters"]) == len(jobs)
    assert sum(1 for c in expl["clusters"] if c["is_resume_cluster"]) == 1
    assert all(c["terms"] and c["affinity"] >= 0 for c in expl["clusters"])

    # Each per-job breakdown adds up, scales to the fit the model actually
    # assigned, and is plotted on the map.
    by_key = {j.key: j for j in scored}
    for jr in expl["jobs"]:
        assert abs(jr["cosine_contribution"] + jr["cluster_contribution"] - jr["raw"]) < 1e-6
        assert abs(jr["raw"] * p["scale"] - jr["fit"]) < 0.1
        assert jr["fit"] == by_key[jr["key"]].fit_score
        assert jr["cluster"] == by_key[jr["key"]].cluster
        assert jr["x"] is not None and jr["y"] is not None

    top = min(expl["jobs"], key=lambda j: j["rank"])
    assert top["fit"] == 100.0 and top["rank"] == 1
    # The top match's overlapping keywords are the cosine's biggest contributors.
    assert top["match_terms"] and top["match_terms"][0][1] > 0


def test_explanation_flag_combinations_and_empty():
    jobs = make_jobs()
    # explanation only → 2-tuple
    scored, expl = score_jobs(RESUME, jobs, clusters=2, corpus=jobs, return_explanation=True)
    assert isinstance(expl, dict) and len(expl["jobs"]) == len(jobs)
    # topics only stays backwards-compatible → 2-tuple of (jobs, topics)
    s2, topics = score_jobs(RESUME, jobs, clusters=2, corpus=jobs, return_topics=True)
    assert isinstance(topics, dict) and topics
    # empty job set returns an unpackable empty shape
    s3, t3, e3 = score_jobs(RESUME, [], return_topics=True, return_explanation=True)
    assert s3 == [] and t3 == {} and e3["jobs"] == [] and e3["params"]["scored"] == 0


def test_single_cluster_small_corpus_still_explains():
    jobs = make_jobs()[:4]  # < 6 postings → pick_cluster_count returns 1
    _, expl = score_jobs(RESUME, jobs, corpus=jobs, return_explanation=True)
    assert expl["params"]["n_clusters"] == 1
    assert len(expl["clusters"]) == 1 and expl["clusters"][0]["size"] == 4
    # The lone cluster still gets the resume-home flag and an affinity.
    assert expl["clusters"][0]["is_resume_cluster"] is True


def test_corpus_too_small_to_map_still_breaks_down_scores():
    """A 2-posting corpus can't be projected to 2-D; the map is dropped but the
    per-job math must still be intact (no crash, coords None)."""
    jobs = [JobPosting(company="A", title="Eng", location="NY", url="", job_id="1",
                       description="python aws backend kafka distributed"),
            JobPosting(company="B", title="Eng", location="NY", url="", job_id="2",
                       description="react css frontend design systems")]
    _, expl = score_jobs(RESUME, jobs, corpus=jobs, return_explanation=True)
    assert expl["params"]["has_map"] is False
    assert all(j["x"] is None and j["y"] is None for j in expl["jobs"])
    assert expl["resume"]["x"] is None
    assert all(abs(j["cosine_contribution"] + j["cluster_contribution"] - j["raw"]) < 1e-6
               for j in expl["jobs"])


# ------------------------------------------------------------ report writer ---
def test_write_clustering(tmp_path):
    jobs = make_jobs()
    _, expl = score_jobs(RESUME, jobs, clusters=2, corpus=jobs, return_explanation=True)
    path = write_clustering(tmp_path, expl)
    assert path is not None and path.name == "clustering.json"
    loaded = json.loads(path.read_text())
    assert loaded["params"]["scored"] == len(jobs) and loaded["jobs"]
    # Nothing scored → nothing written.
    assert write_clustering(tmp_path, {"jobs": []}) is None
    assert write_clustering(tmp_path, None) is None


# -------------------------------------------------------------- webapp views ---
def _record(key="greenhouse:Acme:1", **kw):
    base = {"key": key, "source": "greenhouse", "company": "Acme",
            "title": "Senior Software Engineer", "location": "New York, NY",
            "url": "https://acme.com/1", "description": "Build Python backend systems.",
            "posted_at": "2026-06-10", "fit_score": 73.2, "rank_score": 60.0,
            "cluster": 0, "filter_reason": "", "validation": "", "validation_note": ""}
    base.update(kw)
    return base


def _app(tmp_path):
    from webapp.app import create_app
    root = tmp_path
    (root / "data").mkdir()
    (root / "config").mkdir()
    (root / "reports").mkdir()
    (root / "data" / "resume.txt").write_text(
        "Test User\nSenior Software Engineer, New York, NY\n\nEXPERIENCE\nDid things.")
    (root / "config" / "settings.yaml").write_text(
        "search:\n  query: senior software engineer\n  locations: [new york]\n"
        "ranking:\n  half_life_days: 7\n  cluster_weight: 0.15\n")
    (root / "config" / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\nmanual_check: []\n")
    return create_app(root, db_path=root / "data" / "test.db"), root


def _clustering_doc():
    return {
        "generated": "2026-06-21T00:00:00+00:00",
        "params": {"n_clusters": 2, "cosine_weight": 0.85, "cluster_weight": 0.15,
                   "corpus_size": 10, "scored": 1, "scale": 150.0, "top_raw": 0.49,
                   "has_map": True},
        "resume": {"x": 0.1, "y": 0.2, "cluster": 0},
        "clusters": [
            {"id": 0, "label": "python, aws", "terms": ["python", "aws", "backend"],
             "size": 1, "corpus_size": 5, "affinity": 0.42, "is_resume_cluster": True,
             "centroid": {"x": 0.2, "y": 0.1}},
            {"id": 1, "label": "react, css", "terms": ["react", "css"],
             "size": 0, "corpus_size": 5, "affinity": 0.10, "is_resume_cluster": False,
             "centroid": {"x": -0.3, "y": 0.25}},
        ],
        "jobs": [
            {"key": "greenhouse:Acme:1", "company": "Acme",
             "title": "Senior Software Engineer", "location": "NYC", "cluster": 0,
             "cosine": 0.5, "affinity": 0.42, "cosine_contribution": 0.425,
             "cluster_contribution": 0.063, "raw": 0.488, "fit": 73.2, "rank": 1,
             "near_miss": False, "filter_reason": "",
             "match_terms": [["python", 0.21], ["aws", 0.12]],
             "top_terms": ["python", "aws", "backend"], "x": 0.21, "y": 0.12},
        ],
    }


def test_clusters_routes(tmp_path):
    from fastapi.testclient import TestClient

    from webapp import clusters as clusters_mod
    from webapp import db

    app, root = _app(tmp_path)
    client = TestClient(app)

    # Empty state before any run wrote a map.
    empty = client.get("/clusters")
    assert empty.status_code == 200 and "No fit map yet" in empty.text
    assert clusters_mod.load_clustering(root) is None

    # Now persist a clustering doc and a matching tracked job.
    db.upsert_job(app.state.conn, _record())
    (root / "reports" / "clustering.json").write_text(json.dumps(_clustering_doc()))

    high = client.get("/clusters")
    assert high.status_code == 200
    assert "Cluster 0" in high.text                 # cluster card rendered
    assert "cluster-map-data" in high.text          # scatter data island embedded
    assert "your home" in high.text                 # resume-home badge

    # map_points joins the DB id so points are clickable.
    pts = clusters_mod.map_points(_clustering_doc(),
                                  db.job_ids_by_key(app.state.conn, ["greenhouse:Acme:1"]))
    assert pts and pts[0]["id"] and pts[0]["company"] == "Acme"

    job_id = app.state.conn.execute("SELECT id FROM jobs").fetchone()["id"]
    per = client.get(f"/clusters/job/{job_id}")
    assert per.status_code == 200
    assert "How the score was built" in per.text
    assert "python" in per.text                     # an overlapping match term
    assert "0.488" in per.text                       # the raw score is shown

    # A job with no entry in the current map degrades gracefully.
    db.upsert_job(app.state.conn, _record(key="greenhouse:Acme:2", url="https://acme.com/2"))
    other_id = app.state.conn.execute(
        "SELECT id FROM jobs WHERE key = 'greenhouse:Acme:2'").fetchone()["id"]
    miss = client.get(f"/clusters/job/{other_id}")
    assert miss.status_code == 200 and "No breakdown for this posting" in miss.text

    # Unknown job id redirects back to the map rather than 500ing.
    assert client.get("/clusters/job/999999", follow_redirects=False).status_code == 303
