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
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.preprocessing import normalize

from .models import JobPosting
from .utils import strip_html

COSINE_WEIGHT = 0.85
CLUSTER_WEIGHT = 0.15

# Posting-boilerplate vocabulary (compensation, EEO, benefits) — says nothing
# about the role, but survives sentence-level boilerplate stripping because the
# wording varies, and it was dominating cluster topics.
EXTRA_STOP_WORDS = frozenset({
    "benefits", "salary", "salaries", "compensation", "equity", "stock", "bonus",
    "insurance", "diversity", "inclusion", "equal", "opportunity", "gender",
    "race", "religion", "veteran", "disability", "accommodation", "accommodations",
    "applicant", "applicants", "candidate", "candidates", "hiring", "apply",
    "click", "employment", "employer", "eeo", "401k", "pto", "parental",
    "medical", "dental", "vision", "annual", "range", "ranges", "pay", "paid",
    "perks", "wellness",
})

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


def _company_name_re(company: str) -> re.Pattern | None:
    """Pattern matching the company's own name tokens (>= 3 chars), so its
    name can't act as a clustering feature for its own postings."""
    tokens = [re.escape(t) for t in re.findall(r"[A-Za-z0-9]+", company) if len(t) >= 3]
    return re.compile(r"\b(" + "|".join(tokens) + r")\b", re.I) if tokens else None


def _doc(job: JobPosting, descriptions: dict[str, str], name_res: dict[str, re.Pattern | None]) -> str:
    desc = descriptions.get(job.key, job.description)
    # Safety net: a fetcher that forgets to strip_html (or a cached corpus from
    # before it was fixed) would otherwise let tag/style tokens (li, h3, span
    # style, font weight, nbsp) dominate the TF-IDF space and form spurious
    # markup clusters. Idempotent on already-plain text.
    text = strip_html(f"{job.title}\n{job.location}\n{desc}")[:20000]
    name_re = name_res.get(job.company)
    return name_re.sub(" ", text) if name_re else text


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


# --------------------------------------------------------------- explanation ---
# Everything below powers the "how was this fit scored?" visualization
# (webapp /clusters): a 2-D map of the TF-IDF space plus a per-job breakdown of
# the cosine + cluster terms that produced each score. It re-uses the exact
# vectors score_jobs already computed, so the numbers shown always match the
# fit_score the pipeline assigned.

def _empty_explanation() -> dict:
    """Shape returned for an empty job set, so callers can unpack unconditionally."""
    from datetime import datetime, timezone
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "params": {"n_clusters": 0, "cosine_weight": 0.0, "cluster_weight": 0.0,
                   "corpus_size": 0, "scored": 0, "scale": 0.0, "top_raw": 0.0,
                   "has_map": False},
        "resume": {"x": None, "y": None, "cluster": 0},
        "clusters": [],
        "jobs": [],
    }


def _top_terms_from_centroid(centroid: np.ndarray, terms: np.ndarray, n: int = 8) -> list[str]:
    order = np.argsort(centroid)[::-1][:n]
    return [str(terms[i]) for i in order if centroid[i] > 0]


def _doc_top_terms(row, terms: np.ndarray, n: int = 8) -> list[str]:
    """The heaviest TF-IDF terms in one posting's own vector — what the model
    'reads' the posting as being about."""
    if row.nnz == 0:
        return []
    order = np.argsort(row.data)[::-1][:n]
    return [str(terms[row.indices[i]]) for i in order]


def _match_terms(row, resume_vec: np.ndarray, terms: np.ndarray, n: int = 8) -> list[list]:
    """Terms shared by the posting and the resume, ranked by how much each
    contributed to the cosine similarity (posting_weight × resume_weight). The
    sum of all such products *is* the cosine, so these are literally the words
    that earned the match."""
    if row.nnz == 0:
        return []
    contrib = row.data * resume_vec[row.indices]
    order = np.argsort(contrib)[::-1][:n]
    out = []
    for i in order:
        if contrib[i] <= 0:
            break
        out.append([str(terms[row.indices[i]]), round(float(contrib[i]), 4)])
    return out


def _project_2d(X_corpus, X_jobs, resume_vec: np.ndarray, centroids):
    """Project the TF-IDF space onto 2 dimensions (LSA) so the corpus can be
    drawn as a scatter. Fit on the corpus, then transform the things we plot:
    the scored jobs, the resume, and the cluster centroids. Returns None when
    the corpus is too small to decompose (the views then skip the map)."""
    n_samples, n_features = X_corpus.shape
    if n_samples <= 2 or n_features <= 2:
        return None
    svd = TruncatedSVD(n_components=2, random_state=0)
    # On degenerate tiny corpora sklearn divides by a zero total variance while
    # computing explained_variance_ratio_ (unused here) — quiet that warning.
    with np.errstate(invalid="ignore", divide="ignore"):
        svd.fit(X_corpus)
    jobs_xy = svd.transform(X_jobs)
    resume_xy = svd.transform(resume_vec.reshape(1, -1))[0]
    centroids_xy = svd.transform(centroids) if centroids is not None else None
    return {"jobs": jobs_xy, "resume": resume_xy, "centroids": centroids_xy}


def _xy(point) -> dict | None:
    return None if point is None else {"x": round(float(point[0]), 4),
                                       "y": round(float(point[1]), 4)}


def _build_explanation(*, jobs, X_jobs, labels, cosine, raw, scale, resume_vec,
                       cosine_weight, cluster_weight, cluster_affinity, topics,
                       corpus, corpus_labels, centroids, n_clusters, vectorizer,
                       X_corpus) -> dict:
    """Assemble the per-run clustering record consumed by the visualization."""
    from datetime import datetime, timezone

    terms = vectorizer.get_feature_names_out()
    coords = _project_2d(X_corpus, X_jobs, resume_vec, centroids)
    job_xy = coords["jobs"] if coords else None
    resume_point = _xy(coords["resume"]) if coords else None

    scored_sizes = Counter(int(c) for c in labels)
    corpus_sizes = Counter(int(c) for c in corpus_labels)
    resume_cluster = int(np.argmax(cluster_affinity)) if len(cluster_affinity) else 0

    clusters = []
    for c in range(n_clusters):
        if coords and coords["centroids"] is not None:
            centroid_xy = _xy(coords["centroids"][c])
        elif coords and job_xy is not None and scored_sizes.get(c):
            # Single-cluster runs have no centroid — sit it at its members' mean.
            members = [job_xy[i] for i in range(len(jobs)) if int(labels[i]) == c]
            centroid_xy = _xy(np.mean(members, axis=0)) if members else None
        else:
            centroid_xy = None
        clusters.append({
            "id": c,
            "label": topics.get(c) or "all postings",
            "terms": (_top_terms_from_centroid(centroids[c], terms)
                      if centroids is not None else []),
            "size": scored_sizes.get(c, 0),
            "corpus_size": corpus_sizes.get(c, 0),
            "affinity": round(float(cluster_affinity[c]), 4),
            "is_resume_cluster": c == resume_cluster,
            "centroid": centroid_xy,
        })

    order = sorted(range(len(jobs)), key=lambda i: -jobs[i].fit_score)
    rank_of = {i: r + 1 for r, i in enumerate(order)}
    jobs_out = []
    for i, job in enumerate(jobs):
        c = int(labels[i])
        cos = float(cosine[i])
        aff = float(cluster_affinity[c])
        # Round the two parts, then derive raw from them so the breakdown adds
        # up exactly on the per-job page (it differs from the true raw only in
        # the 4th decimal; the displayed fit comes from the true fit_score).
        cos_contribution = round(cosine_weight * cos, 4)
        cluster_contribution = round(cluster_weight * aff, 4)
        jobs_out.append({
            "key": job.key,
            "company": job.company,
            "title": job.title,
            "location": job.location,
            "cluster": c,
            "cosine": round(cos, 4),
            "affinity": round(aff, 4),
            "cosine_contribution": cos_contribution,
            "cluster_contribution": cluster_contribution,
            "raw": round(cos_contribution + cluster_contribution, 4),
            "fit": job.fit_score,
            "rank": rank_of[i],
            "near_miss": bool(job.filter_reason),
            "filter_reason": job.filter_reason,
            "match_terms": _match_terms(X_jobs[i], resume_vec, terms),
            "top_terms": _doc_top_terms(X_jobs[i], terms),
            # Map coords; None on corpora too small to project (params.has_map).
            **((_xy(job_xy[i]) if job_xy is not None else None) or {"x": None, "y": None}),
        })

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "params": {
            "n_clusters": n_clusters,
            "cosine_weight": round(float(cosine_weight), 3),
            "cluster_weight": round(float(cluster_weight), 3),
            "corpus_size": len(corpus),
            "scored": len(jobs),
            "scale": round(float(scale), 4),
            "top_raw": round(float(raw.max()), 4) if len(raw) else 0.0,
            "has_map": coords is not None,
        },
        "resume": {**(resume_point or {"x": None, "y": None}),
                   "cluster": resume_cluster},
        "clusters": clusters,
        "jobs": jobs_out,
    }


def score_jobs(
    resume_text: str,
    jobs: list[JobPosting],
    clusters="auto",
    corpus: list[JobPosting] | None = None,
    cluster_weight: float = CLUSTER_WEIGHT,
    return_topics: bool = False,
    return_explanation: bool = False,
):
    """Assign fit_score (0-100) and cluster labels to every job in `jobs`,
    in place.

    `corpus` is the document set used to fit the vectorizer and K-means —
    pass the full fetched corpus so IDF and clusters are estimated from
    thousands of postings rather than the filtered few. `jobs` must be a
    subset of `corpus` (or corpus=None to fit on `jobs` themselves).

    Return shape grows with the optional flags (jobs are always mutated in
    place): `jobs`, then `topics` if `return_topics`, then a clustering
    `explanation` dict if `return_explanation` — the latter powering the
    /clusters visualization (a 2-D map + a per-job score breakdown).
    """
    def _result(explanation=None):
        out = [jobs]
        if return_topics:
            out.append(topics)
        if return_explanation:
            out.append(explanation if explanation is not None else _empty_explanation())
        return tuple(out) if len(out) > 1 else jobs

    if not jobs:
        topics = {}
        return _result()
    corpus = corpus if corpus else jobs

    descriptions = strip_company_boilerplate(corpus)
    name_res = {c: _company_name_re(c) for c in {j.company for j in corpus}}
    vectorizer = TfidfVectorizer(
        stop_words=list(ENGLISH_STOP_WORDS | EXTRA_STOP_WORDS),
        ngram_range=(1, 2),
        max_features=30000,
        sublinear_tf=True,
        min_df=3 if len(corpus) >= 200 else 1,
    )
    X_corpus = normalize(vectorizer.fit_transform([_doc(j, descriptions, name_res) for j in corpus]))
    resume_vec = normalize(vectorizer.transform([resume_text])).toarray().ravel()

    n_clusters = pick_cluster_count(len(corpus), clusters)
    centroids = None
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
        X_jobs = normalize(vectorizer.transform([_doc(j, descriptions, name_res) for j in jobs]))
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

    explanation = None
    if return_explanation:
        explanation = _build_explanation(
            jobs=jobs, X_jobs=X_jobs, labels=labels, cosine=cosine, raw=raw,
            scale=scale, resume_vec=resume_vec, cosine_weight=cosine_weight,
            cluster_weight=cluster_weight, cluster_affinity=cluster_affinity,
            topics=topics, corpus=corpus, corpus_labels=corpus_labels,
            centroids=centroids, n_clusters=n_clusters, vectorizer=vectorizer,
            X_corpus=X_corpus)
    return _result(explanation)


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
