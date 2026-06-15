"""Score referral candidates against a job description and the user's resume.

The same TF-IDF vectorizer fits one shared vocabulary across {resume,
job_description, every candidate document} so the three cosines live in the
same space — comparable, and computed once per discovery run instead of
three separate fits. Reuses the EXTRA_STOP_WORDS list from scoring.py so
boilerplate ("equal opportunity employer", "we are looking for", …) doesn't
inflate spurious matches against thin LinkedIn headlines.

Scores are returned as 0-100 floats for direct display. `combined` is the
plain mean of job_match and user_match — neither one alone is enough (a
candidate who's a perfect role fit but shares no background with the user
won't reply; a candidate who shares your alma mater but works in a totally
different team can't help).
"""

from __future__ import annotations

from dataclasses import dataclass

from .sources.linkedin import CandidateHit


@dataclass
class ScoredCandidate:
    hit: CandidateHit
    job_match: float       # 0-100
    user_match: float      # 0-100
    combined: float        # 0-100


def rank_candidates(
    hits: list[CandidateHit],
    job_description: str,
    resume_text: str,
) -> list[ScoredCandidate]:
    """Score each hit against the job and the resume. Empty job or resume
    text degrades gracefully — that axis just scores 0 instead of NaN."""
    if not hits:
        return []

    import numpy as np
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
    from sklearn.preprocessing import normalize

    from ..scoring import EXTRA_STOP_WORDS

    candidate_docs = [h.document() for h in hits]
    # job and resume are appended at the END so we can slice them off after
    # one shared fit.
    corpus = candidate_docs + [job_description or "", resume_text or ""]
    vectorizer = TfidfVectorizer(
        stop_words=list(ENGLISH_STOP_WORDS | EXTRA_STOP_WORDS),
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    matrix = normalize(vectorizer.fit_transform(corpus))
    cand_matrix = matrix[: len(hits)]
    job_vec = matrix[len(hits)]
    resume_vec = matrix[len(hits) + 1]

    job_scores = np.asarray((cand_matrix @ job_vec.T).todense()).ravel()
    resume_scores = np.asarray((cand_matrix @ resume_vec.T).todense()).ravel()

    scored: list[ScoredCandidate] = []
    for hit, jscore, rscore in zip(hits, job_scores, resume_scores):
        jpct = round(float(jscore) * 100, 1)
        rpct = round(float(rscore) * 100, 1)
        combined = round((jpct + rpct) / 2, 1)
        scored.append(ScoredCandidate(
            hit=hit, job_match=jpct, user_match=rpct, combined=combined,
        ))
    scored.sort(key=lambda s: s.combined, reverse=True)
    return scored
