"""Resume intake: text extraction and dynamic keyword extraction.

The pipeline is resume-agnostic by design — scoring projects whatever resume
text it is given into the same TF-IDF space as the postings (scoring.py), and
the profile panel seeds itself from the resume header (webapp/profile.py).
This module supplies the missing intake pieces:

- `pdf_to_text` so the UI can accept a PDF upload directly;
- `extract_keywords`, a dependency-light summary of what the resume is about,
  shown on the /resume page and used to sanity-check that extraction worked
  (garbled PDF text yields garbled keywords — visible at a glance);
- `load_resume_text`, the single place that resolves which resume the
  pipeline scores against, falling back to the bundled sample so a fresh
  clone works before anything is uploaded.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

SAMPLE_RESUME = "data/sample_resume.txt"

# Resume-boilerplate words that say nothing about the candidate's domain.
_RESUME_STOP = frozenset({
    "experience", "experienced", "work", "worked", "working", "team", "teams",
    "year", "years", "month", "months", "summary", "skills", "education",
    "present", "led", "built", "designed", "developed", "improved", "reduced",
    "increased", "drove", "responsible", "using", "strong", "new",
})

_WORD = re.compile(r"[a-zA-Z][a-zA-Z+#.]{1,}")


def pdf_to_text(data: bytes) -> str:
    """Extract plain text from PDF bytes. Raises ValueError when the PDF
    yields no extractable text (scanned image, encrypted)."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages).strip()
    if len(text) < 100:
        raise ValueError(
            "could not extract text from this PDF (is it a scanned image?) — "
            "paste or upload your resume as plain text instead")
    return text


def extract_keywords(text: str, top_n: int = 24) -> list[str]:
    """The resume's most salient terms: frequency-ranked unigrams and bigrams
    with stop/boilerplate words removed. Pure and offline-testable."""
    words = [w.lower() for w in _WORD.findall(text)]
    kept = [w for w in words
            if len(w) >= 2 and w not in ENGLISH_STOP_WORDS and w not in _RESUME_STOP]
    counts: Counter[str] = Counter(kept)
    # Bigrams over the kept sequence catch phrases like "distributed systems".
    bigram_counts: Counter[str] = Counter()
    prev_idx = {}
    sequence = [w for w in words if w not in ENGLISH_STOP_WORDS]
    for a, b in zip(sequence, sequence[1:]):
        if a not in _RESUME_STOP and b not in _RESUME_STOP:
            bigram_counts[f"{a} {b}"] += 1
    scored = [(count, term) for term, count in counts.items() if count >= 2]
    scored += [(count * 2, term) for term, count in bigram_counts.items() if count >= 2]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    result, seen_parts = [], set()
    for _, term in scored:
        # A bigram supersedes its parts ("distributed systems" over "distributed").
        if term in seen_parts:
            continue
        result.append(term)
        seen_parts.update(term.split())
        if len(result) >= top_n:
            break
    return result


def load_resume_text(root: Path, settings: dict) -> tuple[str, bool]:
    """Return (resume text, is_sample). Resolution order: the configured
    resume path (data/resume.txt — written by the UI upload), then the
    bundled sample so first runs work out of the box."""
    configured = root / settings.get("resume", "data/resume.txt")
    if configured.exists():
        return configured.read_text(), False
    sample = root / SAMPLE_RESUME
    return sample.read_text(), True
