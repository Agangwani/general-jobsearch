"""Link prep modules to the source-book chapter they were distilled from.

A module's ``source_refs`` (e.g. "CtCI Ch. 1, pp. 88–104", "DDIA Ch.5 …",
"SDI Ch.3 …") names a book and chapter. We resolve that to:
  - the extracted chapter text under data/prep_sources/chapters/, and
  - the local book PDF under prep_work/ (opened at the chapter's PDF page,
    read from the ``PDF_PAGE n`` marker the extractor leaves in the text).

Both source files are large/local-only (gitignored), so every lookup is
best-effort and degrades to "not available" when a file is missing.
"""

from __future__ import annotations

import re
from pathlib import Path

# book key → display name + glob for the local PDF (globbed to dodge the unicode
# punctuation in the DDIA filename).
BOOKS: dict[str, dict] = {
    "ctci": {"name": "Cracking the Coding Interview",
             "pdf_glob": "Cracking-the-Coding-Interview*.pdf"},
    "ddia": {"name": "Designing Data-Intensive Applications",
             "pdf_glob": "*Designing-Data-Intensive*.pdf"},
    "sdi": {"name": "System Design Interview", "pdf_glob": "SystemDesignInterview*.pdf"},
}

_BOOK_PATTERNS = [
    ("ctci", re.compile(r"\bctci\b|cracking the coding", re.I)),
    ("ddia", re.compile(r"\bddia\b|designing data-intensive", re.I)),
    ("sdi", re.compile(r"\bsdi\b|system design interview", re.I)),
]
_CHAPTER = re.compile(r"\bch(?:apter)?\.?\s*(\d+)", re.I)
# Two extractor formats: CtCI "PDF_PAGE 100/712" and DDIA/SDI "PDF page 163".
_PDF_PAGE = re.compile(r"PDF[_ ]PAGE\s+(\d+)", re.I)


def parse_ref(source_refs: str) -> tuple[str, int | None] | None:
    """``(book_key, chapter)`` from a source_refs string, or None if no known
    book is named. ``chapter`` is None for roman-numeral / part refs (front
    matter), which have no dedicated chapter file."""
    if not source_refs:
        return None
    book = next((key for key, rx in _BOOK_PATTERNS if rx.search(source_refs)), None)
    if not book:
        return None
    match = _CHAPTER.search(source_refs)
    return (book, int(match.group(1)) if match else None)


def chapter_path(chapters_dir: Path, book: str, chapter: int | None) -> Path | None:
    if chapter is None:
        return None
    hits = sorted(Path(chapters_dir).glob(f"{book}_ch{chapter:02d}_*.txt"))
    return hits[0] if hits else None


def pdf_path(root: Path, book: str) -> Path | None:
    meta = BOOKS.get(book)
    if not meta:
        return None
    hits = sorted((Path(root) / "prep_work").glob(meta["pdf_glob"]))
    return hits[0] if hits else None


def first_pdf_page(text: str) -> int | None:
    match = _PDF_PAGE.search(text or "")
    return int(match.group(1)) if match else None


def source_for(root: Path, source_refs: str) -> dict | None:
    """Resolve everything the UI needs to offer "open the source chapter", or
    None when source_refs names no known book."""
    parsed = parse_ref(source_refs)
    if parsed is None:
        return None
    book, chapter = parsed
    root = Path(root)
    text_path = chapter_path(root / "data" / "prep_sources" / "chapters", book, chapter)
    pdf = pdf_path(root, book)
    info = {
        "book": book, "book_name": BOOKS[book]["name"], "chapter": chapter,
        "text_path": str(text_path) if text_path else "",
        "has_text": text_path is not None,
        "has_pdf": pdf is not None, "pdf_page": None,
    }
    if text_path is not None:
        info["pdf_page"] = first_pdf_page(text_path.read_text(errors="ignore"))
    return info


def available(root: Path, source_refs: str) -> bool:
    """True when there's a chapter text or a local PDF to open."""
    info = source_for(root, source_refs)
    return bool(info and (info["has_text"] or info["has_pdf"]))
