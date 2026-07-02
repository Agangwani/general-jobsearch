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

import os
import re
from collections import Counter
from pathlib import Path

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

SAMPLE_RESUME = "data/sample_resume.txt"
LOCAL_USER = "local"

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
    yields no extractable text (scanned image, encrypted) or cannot be parsed
    (a truncated/corrupt file with a valid %PDF header but an unreadable body —
    pypdf raises PdfStreamError/PdfReadError, neither a ValueError, so we
    translate them here so callers get one friendly error to handle)."""
    import io

    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PyPdfError as exc:
        raise ValueError("that file isn't a valid PDF") from exc
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


def _resume_from_db(root: Path, user_id: str) -> str | None:
    """The user's resume text from the application DB, or None. Best-effort: the
    DB is only consulted when it already exists (hosted, or a webapp user) so a
    pure-CLI clone with no DB stays entirely file-based; any failure falls back
    to the file/sample."""
    db_path = root / "data" / "jobsearch.db"
    if not db_path.exists() and not os.environ.get("JOBSEARCH_DATABASE_URL"):
        return None
    try:
        from webapp import db
        conn = db.connect(db_path)
        try:
            return db.get_resume(conn, user_id)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - DB unavailable → fall back to the file
        return None


def load_resume_text(root: Path, settings: dict,
                     user_id: str = LOCAL_USER) -> tuple[str, bool]:
    """Return (resume text, is_sample) for a user.

    - Local (single-user): data/resume.txt is the source of truth — a hand-edit
      to it must win (jobsearch/CLAUDE.md) — then the DB, then the bundled
      sample. Unchanged from before per-user support.
    - Hosted per-user: the resume stored in the DB (durable — the filesystem is
      ephemeral on hosted deploys), then the bundled sample. It must NEVER fall
      back to the shared data/resume.txt, which is another user's resume.

    The bundled sample keeps a fresh clone working before anything is uploaded."""
    sample = root / SAMPLE_RESUME
    if user_id == LOCAL_USER:
        configured = root / settings.get("resume", "data/resume.txt")
        if configured.exists():
            return configured.read_text(), False
        stored = _resume_from_db(root, user_id)
        if stored:
            return stored, False
        return sample.read_text(), True
    # Non-local: DB only, then the neutral sample — never the owner's file.
    stored = _resume_from_db(root, user_id)
    if stored:
        return stored, False
    return sample.read_text(), True
