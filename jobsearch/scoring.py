"""Resume-fit scoring.

Postings are embedded in a shared TF-IDF token space and clustered with
K-means; the resume is projected into the same space. A posting's fit blends
direct cosine similarity to the resume with how well the resume fits the
posting's cluster. Scores are scaled so the best posting of the day is 100 —
they are relative ranks, not absolute percentages.

Two skew defenses (see docs/analysis-scoring-skew.md):

- The vectorizer and K-means are fit on the FULL fetched corpus (pass
  `corpus=`), not just the few dozen filtered survivors — IDF weights and
  clusters are meaningless on a tiny sample, and at small scale clusters
  mostly recover company authorship rather than skill-space structure.
- Per-company boilerplate (shared "about us"/benefits text) is stripped
  before vectorizing, so a company whose marketing vocabulary overlaps the
  resume doesn't get every posting inflated at once.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .models import JobPosting

COSINE_WEIGHT = 0.85
CLUSTER_WEIGHT = 0.15

# Sentences appearing in more than this share of a company's postings are
# treated as boilerplate (companies with >= MIN_POSTINGS postings only).
BOILERPLATE_SHARE = 0.6
BOILERPLATE_MIN_POSTINGS = 3

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _normalize_sentence(sentence: str) -> str:
    return " ".join(sentence.lower().split())


def strip_company_boilerplate(jobs: list[JobPosting]) -> dict[str, str]:
    """Return {job.key: cleaned description} with per-company boilerplate
    sentences removed. Originals are never mutated."""
    by_company: dict[str, list[JobPosting]] = defaultdict(list)
    for job in jobs:
        by_company[job.company].append(job)

    cleaned: dict[str, str] = {}
    for company_jobs in by_company.values():
        if len(company_jobs) < BOILERPLATE_MIN_POSTINGS:
            for job in company_jobs:
                cleaned[job.key] = job.description
            continue
        counts: Counter[str] = Counter()
        split_docs: list[list[str]] = []
        for job in company_jobs:
            sentences = [s for s in _SENTENCE_SPLIT.split(job.description) if s.strip()]
            split_docs.append(sentences)
            counts.update({_normalize_sentence(s) for s in sentences if len(s.split()) >= 5})
        threshold = max(2, int(len(company_jobs) * BOILERPLATE_SHARE))
        boilerplate = {s for s, n in counts.items() if n >= threshold}
        for job, sentences in zip(company_jobs, split_docs):
            kept = " ".join(s for s in sentences if _normalize_sentence(s) not in boilerplate)
            # Safety valve: if stripping removed ~everything (near-duplicate
            # postings), the shared text IS the signal — keep the original.
            if len(kept) < 0.1 * len(job.description):
                kept = job.description
            cleaned[job.key] = kept
    return cleaned


def _doc(job: JobPosting, descriptions: dict[str, str]) -> str:
    desc = descriptions.get(job.key, job.description)
    return f"{job.title}\n{job.location}\n{desc}"[:20000]


def pick_cluster_count(n_jobs: int, configured) -> int:
    if isinstance(configured, int) and configured > 0:
        return min(configured, n_jobs)
    if n_jobs < 6:
        return 1
    return max(2, min(20, n_jobs // 150))


def cluster_topics(vectorizer: TfidfVectorizer, centroids: np.ndarray, n_terms: int = 4) -> dict[int, str]:
    """Human-readable label per cluster: its top centroid terms."""
    terms = vectorizer.get_feature_names_out()
    topics = {}
    for idx, centroid in enumerate(centroids):
        top = np.argsort(centroid)[::-1][:n_terms]
        topics[idx] = ", ".join(terms[i] for i in top)
    return topics


def score_jobs(
    resume_text: str,
    jobs: list[JobPosting],
    clusters="auto",
    corpus: list[JobPosting] | None = None,
    cluster_weight: float = CLUSTER_WEIGHT,
    return_topics: bool = False,
):
    """Assign fit_score (0-100) and cluster labels to every job in `jobs`,
    in place.

    `corpus` is the document set used to fit the vectorizer and K-means —
    pass the full fetched corpus so IDF and clusters are estimated from
    thousands of postings rather than the filtered few. `jobs` must be a
    subset of `corpus` (or corpus=None to fit on `jobs` themselves).
    """
    if not jobs:
        return (jobs, {}) if return_topics else jobs
    corpus = corpus if corpus else jobs

    descriptions = strip_company_boilerplate(corpus)
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=30000,
        sublinear_tf=True,
        min_df=3 if len(corpus) >= 200 else 1,
    )
    X_corpus = normalize(vectorizer.fit_transform([_doc(j, descriptions) for j in corpus]))
    resume_vec = normalize(vectorizer.transform([resume_text])).toarray().ravel()

    n_clusters = pick_cluster_count(len(corpus), clusters)
    if n_clusters > 1:
        km = KMeans(
            n_clusters=n_clusters,
            n_init=3 if len(corpus) > 2000 else 10,
            random_state=0,
        )
        corpus_labels = km.fit_predict(X_corpus)
        centroids = normalize(km.cluster_centers_)
        cluster_affinity = centroids @ resume_vec
        topics = cluster_topics(vectorizer, centroids)
    else:
        corpus_labels = np.zeros(len(corpus), dtype=int)
        cluster_affinity = np.array([float(np.asarray(X_corpus @ resume_vec).mean())])
        topics = {}

    index_of = {id(job): i for i, job in enumerate(corpus)}
    rows = [index_of.get(id(job)) for job in jobs]
    if any(r is None for r in rows):  # jobs not drawn from corpus: embed separately
        X_jobs = normalize(vectorizer.transform([_doc(j, descriptions) for j in jobs]))
        labels = km.predict(X_jobs) if n_clusters > 1 else np.zeros(len(jobs), dtype=int)
    else:
        X_jobs = X_corpus[rows]
        labels = corpus_labels[rows]

    cosine_weight = 1.0 - cluster_weight
    cosine = np.asarray(X_jobs @ resume_vec).ravel()
    raw = cosine_weight * cosine + cluster_weight * cluster_affinity[labels]

    top = float(raw.max())
    scale = 100.0 / top if top > 0 else 0.0
    for job, score, label in zip(jobs, raw, labels):
        job.fit_score = round(float(score) * scale, 1)
        job.cluster = int(label)
    return (jobs, topics) if return_topics else jobs


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
