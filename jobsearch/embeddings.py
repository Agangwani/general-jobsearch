"""Optional semantic-embedding matching backend (opt-in, off by default).

Fit scoring (jobsearch/scoring.py) uses TF-IDF cosine by default. When
``ranking.match_backend == "embedding"``, the *direct* resume-to-posting
similarity term — the dominant 0.95-weight component of the fit score — is
computed from sentence-transformer embeddings instead, over the SAME cleaned
posting text scoring already builds (title + description, location excluded,
per-company boilerplate stripped). That preserves the two product decisions the
TF-IDF tuning encodes: location must not influence fit, and company authorship
must not dominate (clustering + de-clustering stay on TF-IDF).

``sentence-transformers`` (and torch) is an **optional** dependency — the default
TF-IDF path never imports it. If it or the model is unavailable, ``embed_texts``
returns ``None`` and scoring falls back to TF-IDF (logging a note), so a machine
without the extra never breaks. Enable with::

    pip install sentence-transformers

Research caveat (see the deep-research briefing): off-the-shelf embeddings are
not automatically better than TF-IDF for resume-to-posting matching — resumes
and postings are *complementary* text — so this stays opt-in until it can be
validated (ideally with a cross-encoder rerank / fine-tuning) rather than made
the default.
"""

from __future__ import annotations

import sys

import numpy as np

DEFAULT_MODEL = "all-MiniLM-L6-v2"
# Cache loaded models (and the None sentinel for "unavailable") per process so a
# scoring run doesn't reload the model or re-attempt a failed import each call.
_MODEL_CACHE: dict[str, object] = {}


def _load_model(name: str):
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    model = None
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(name)
    except ImportError:
        print("embedding backend requested but sentence-transformers is not "
              "installed (`pip install sentence-transformers`) — falling back to "
              "TF-IDF.", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - model download/load failure → fall back
        print(f"embedding model {name!r} could not be loaded ({exc}) — falling "
              "back to TF-IDF.", file=sys.stderr)
    _MODEL_CACHE[name] = model
    return model


def embed_texts(texts, model_name: str = DEFAULT_MODEL):
    """L2-normalized embeddings for ``texts`` as an ``(n, d)`` float array, or
    ``None`` when sentence-transformers / the model is unavailable (the caller
    then falls back to TF-IDF). Never raises."""
    model = _load_model(model_name)
    if model is None:
        return None
    try:
        vecs = model.encode(list(texts), normalize_embeddings=True,
                            show_progress_bar=False)
    except Exception as exc:  # noqa: BLE001 - encode failure must not sink scoring
        print(f"embedding encode failed ({exc}) — falling back to TF-IDF.",
              file=sys.stderr)
        return None
    return np.asarray(vecs, dtype=float)


def resume_job_cosine(resume_text: str, job_texts: list[str],
                      model_name: str = DEFAULT_MODEL):
    """Cosine similarity of each job text to the resume in embedding space, as a
    length-``len(job_texts)`` array — or ``None`` if embeddings are unavailable.
    Both sides are L2-normalized, so the dot product is the cosine."""
    if not job_texts:
        return np.zeros(0, dtype=float)
    matrix = embed_texts([resume_text, *job_texts], model_name)
    if matrix is None or matrix.shape[0] != len(job_texts) + 1:
        return None
    resume_vec = matrix[0]
    job_vecs = matrix[1:]
    return np.asarray(job_vecs @ resume_vec, dtype=float).ravel()
