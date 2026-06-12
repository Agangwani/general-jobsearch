"""Render stored plain-text job descriptions as readable HTML.

Descriptions arrive from the pipeline via strip_html(): one line per block
element, list items prefixed with `• `. This module turns that into
paragraphs, <ul> lists, and section headings. Descriptions ingested before
the structure-preserving strip_html (a single huge line) fall back to
sentence-grouped paragraphs so they are at least readable until the next
run re-captures them.

Everything is HTML-escaped — descriptions are external content.
"""

from __future__ import annotations

import html
import re

from markupsafe import Markup

_BULLET = re.compile(r"^[•·∙▪◦‣–\-\*]\s+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"])")


def _is_heading(line: str) -> bool:
    if len(line) > 70 or len(line.split()) > 8:
        return False
    if line.endswith(":"):
        return True
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def description_html(text: str) -> Markup:
    text = (text or "").strip()
    if not text:
        return Markup("")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) == 1:  # legacy one-line description
        sentences = _SENTENCE.split(lines[0])
        lines = [" ".join(sentences[i:i + 3]) for i in range(0, len(sentences), 3)]

    out: list[str] = []
    items: list[str] = []

    def flush_list() -> None:
        if items:
            out.append("<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in lines:
        match = _BULLET.match(line)
        if match:
            items.append(line[match.end():])
            continue
        flush_list()
        if _is_heading(line):
            out.append(f"<h3>{html.escape(line.rstrip(':'))}</h3>")
        else:
            out.append(f"<p>{html.escape(line)}</p>")
    flush_list()
    return Markup("".join(out))
