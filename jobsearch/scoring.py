"""Resume-fit scoring.

All postings are embedded in a shared TF-IDF token space and clustered with
K-means. The resume is projected into the same space; a posting's fit blends
direct cosine similarity to the resume with how well the resume fits the
posting's cluster. Scores are scaled so the best posting of the day is 100 —
they are relative ranks, not absolute percentages.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .models import JobPosting

COSINE_WEIGHT = 0.7
CLUSTER_WEIGHT = 0.3


def _doc(job: JobPosting) -> str:
    return f"{job.title}\n{job.location}\n{job.description}"[:20000]


def pick_cluster_count(n_jobs: int, configured) -> int:
    if isinstance(configured, int) and configured > 0:
        return min(configured, n_jobs)
    if n_jobs < 6:
        return 1
    return max(2, min(12, n_jobs // 15))


def score_jobs(resume_text: str, jobs: list[JobPosting], clusters="auto") -> list[JobPosting]:
    """Assign fit_score (0-100) and cluster labels to every job, in place."""
    if not jobs:
        return jobs

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=30000,
        sublinear_tf=True,
        min_df=1,
    )
    X = normalize(vectorizer.fit_transform([_doc(j) for j in jobs]))
    resume_vec = normalize(vectorizer.transform([resume_text])).toarray().ravel()

    n_clusters = pick_cluster_count(len(jobs), clusters)
    if n_clusters > 1:
        km = KMeans(n_clusters=n_clusters, n_init=10, random_state=0)
        labels = km.fit_predict(X)
        centroids = normalize(km.cluster_centers_)
        cluster_affinity = centroids @ resume_vec  # resume vs. each cluster centroid
    else:
        labels = np.zeros(len(jobs), dtype=int)
        cluster_affinity = np.array([float(np.asarray(X @ resume_vec).mean())])

    cosine = np.asarray(X @ resume_vec).ravel()
    raw = COSINE_WEIGHT * cosine + CLUSTER_WEIGHT * cluster_affinity[labels]

    top = float(raw.max())
    scale = 100.0 / top if top > 0 else 0.0
    for job, score, label in zip(jobs, raw, labels):
        job.fit_score = round(float(score) * scale, 1)
        job.cluster = int(label)
    return jobs


def apply_recency(jobs: list[JobPosting], half_life_days: float = 7.0, unknown_age_days: float = 14.0) -> list[JobPosting]:
    """rank_score = fit * 0.5 ** (age / half_life); newer postings win ties decisively."""
    for job in jobs:
        age = job.age_days()
        if age is None:
            age = unknown_age_days
        job.rank_score = round(job.fit_score * (0.5 ** (age / half_life_days)), 2)
    jobs.sort(key=lambda j: (-j.rank_score, -j.fit_score, j.company, j.title))
    return jobs


def rank_companies(jobs: list[JobPosting], top_n: int = 3) -> dict[str, float]:
    """Company fit = mean fit of its strongest `top_n` matching postings."""
    by_company: dict[str, list[float]] = {}
    for job in jobs:
        by_company.setdefault(job.company, []).append(job.fit_score)
    return {
        name: round(sum(sorted(scores, reverse=True)[:top_n]) / min(len(scores), top_n), 1)
        for name, scores in by_company.items()
    }
