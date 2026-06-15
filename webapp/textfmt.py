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


# --------------------------------------------------------------- prep markdown
# A small, dependency-free Markdown subset for the interview-prep lesson bodies:
# headings (##/###), -/* and 1. lists, fenced + inline code, **bold**, and
# [text](url) links. Everything is HTML-escaped first — content is trusted
# (we author it) but escaping keeps `<`, `&`, and code samples rendering right.
_MD_INLINE_CODE = re.compile(r"`([^`]+)`")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_MD_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_MD_UL = re.compile(r"^[-*]\s+(.*)$")
_MD_OL = re.compile(r"^\d+\.\s+(.*)$")


def _md_inline(s: str) -> str:
    s = html.escape(s)
    s = _MD_INLINE_CODE.sub(r"<code>\1</code>", s)
    s = _MD_BOLD.sub(r"<strong>\1</strong>", s)
    s = _MD_LINK.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


def prep_markdown(text: str) -> Markup:
    lines = (text or "").split("\n")
    out: list[str] = []
    para: list[str] = []
    ul: list[str] = []
    ol: list[str] = []

    def flush_para() -> None:
        if para:
            out.append("<p>" + " ".join(_md_inline(x) for x in para) + "</p>")
            para.clear()

    def flush_ul() -> None:
        if ul:
            out.append("<ul>" + "".join(f"<li>{_md_inline(x)}</li>" for x in ul) + "</ul>")
            ul.clear()

    def flush_ol() -> None:
        if ol:
            out.append("<ol>" + "".join(f"<li>{_md_inline(x)}</li>" for x in ol) + "</ol>")
            ol.clear()

    def flush_all() -> None:
        flush_para(); flush_ul(); flush_ol()

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            flush_all()
            i += 1
            code: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i]); i += 1
            i += 1  # skip closing fence
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            continue
        if not stripped:
            flush_all(); i += 1; continue
        heading = _MD_HEADING.match(stripped)
        if heading:
            flush_all()
            level = min(len(heading.group(1)) + 1, 4)  # '#' -> h2, '##' -> h3 ...
            out.append(f"<h{level}>{_md_inline(heading.group(2))}</h{level}>")
            i += 1; continue
        bullet = _MD_UL.match(stripped)
        if bullet:
            flush_para(); flush_ol()
            ul.append(bullet.group(1)); i += 1; continue
        numbered = _MD_OL.match(stripped)
        if numbered:
            flush_para(); flush_ul()
            ol.append(numbered.group(1)); i += 1; continue
        flush_ul(); flush_ol()
        para.append(stripped); i += 1
    flush_all()
    return Markup("".join(out))
