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
# headings (##/###), -/* and 1. lists (incl. nesting + soft-wrapped items),
# pipe tables, > blockquotes, fenced + inline code, **bold**, *italic*, and
# [text](url) links. Everything is HTML-escaped first — content is trusted
# (we author it) but escaping keeps `<`, `&`, and code samples rendering right.
#
# Design note: the renderer is *block-oriented*. It groups consecutive
# non-blank source lines into one logical block, then classifies and
# inline-formats the assembled block. Markdown treats soft-wrapped lines as one
# block, so a list item or paragraph split across lines must be joined *before*
# inline formatting — otherwise `**bold**`/`*italic*` that straddle a wrap break,
# and wrapped list items shatter into stray paragraphs.
_MD_INLINE_CODE = re.compile(r"`([^`]+)`")
_MD_BOLD = re.compile(r"\*\*([^*]+?)\*\*")
# Single-* emphasis, guarded so it never eats `**bold**` (consumed first) or a
# bare multiplication/footnote `*` adjacent to a word char or bounded by spaces.
_MD_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_MD_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_MD_LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def _md_inline(s: str) -> str:
    s = html.escape(s)
    s = _MD_INLINE_CODE.sub(r"<code>\1</code>", s)
    s = _MD_BOLD.sub(r"<strong>\1</strong>", s)
    s = _MD_ITALIC.sub(r"<em>\1</em>", s)
    s = _MD_LINK.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


def _is_table_row(s: str) -> bool:
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_table_sep(s: str) -> bool:
    # A separator like |----|:--:|---| — only pipes/dashes/colons/space, has both.
    return bool(s) and set(s) <= set("|:- ") and "-" in s and "|" in s


def _table_cells(s: str) -> list[str]:
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _render_table(header: str, rows: list[str]) -> str:
    out = ["<table><thead><tr>"]
    out += [f"<th>{_md_inline(c)}</th>" for c in _table_cells(header)]
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in _table_cells(row)) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _block_starter(line: str) -> bool:
    """True if `line` begins a new block and so cannot be a soft-wrap
    continuation of the current paragraph/list item."""
    s = line.strip()
    return (not s or s.startswith("```") or s.startswith(">")
            or bool(_MD_HEADING.match(s)) or bool(_MD_LIST.match(line))
            or _is_table_row(s))


def _render_list(lines: list[str], i: int, n: int) -> tuple[str, int]:
    """Render one list block (with nesting by indent and soft-wrapped items)
    starting at line `i`; return (html, index_after_block).

    Two phases so inline formatting never straddles a soft wrap: first collect
    each item's full text (joining wrapped continuation lines), then emit HTML.
    """
    items: list[dict] = []  # {indent, tag, text}
    while i < n:
        raw = lines[i]
        if not raw.strip():
            break
        m = _MD_LIST.match(raw)
        if m:
            items.append({"indent": len(m.group(1)),
                          "tag": "ol" if m.group(2).endswith(".") else "ul",
                          "text": m.group(3).strip()})
            i += 1
            continue
        # A non-marker, non-blank line that isn't a new block = soft-wrap
        # continuation of the item just above it.
        if _block_starter(raw) or not items:
            break
        items[-1]["text"] += " " + raw.strip()
        i += 1

    out: list[str] = []
    stack: list[list] = []  # each: [indent, tag, li_open]

    def close_li(level: list) -> None:
        if level[2]:
            out.append("</li>")
            level[2] = False

    for it in items:
        indent, tag, text = it["indent"], it["tag"], it["text"]
        while stack and stack[-1][0] > indent:      # leave deeper nested lists
            lvl = stack.pop()
            close_li(lvl)
            out.append(f"</{lvl[1]}>")
        if stack and stack[-1][0] == indent:        # sibling at this level
            close_li(stack[-1])
            if stack[-1][1] != tag:                 # switched - / 1. at same depth
                lvl = stack.pop()
                out.append(f"</{lvl[1]}>")
                out.append(f"<{tag}>")
                stack.append([indent, tag, False])
        else:                                       # first item or a deeper nest
            out.append(f"<{tag}>")
            stack.append([indent, tag, False])
        out.append("<li>" + _md_inline(text))
        stack[-1][2] = True

    while stack:
        lvl = stack.pop()
        if lvl[2]:
            out.append("</li>")
        out.append(f"</{lvl[1]}>")
    return "".join(out), i


def prep_markdown(text: str) -> Markup:
    lines = (text or "").split("\n")
    out: list[str] = []
    i, n = 0, len(lines)

    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        if not stripped:                                    # blank line
            i += 1
            continue

        if stripped.startswith("```"):                      # fenced code
            lang = stripped[3:].strip()
            i += 1
            code: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i]); i += 1
            i += 1  # skip closing fence
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>" + html.escape("\n".join(code)) + "</code></pre>")
            continue

        heading = _MD_HEADING.match(stripped)               # ## heading
        if heading:
            level = min(len(heading.group(1)) + 1, 4)       # '#' -> h2, '##' -> h3 ...
            out.append(f"<h{level}>{_md_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if _is_table_row(stripped) and i + 1 < n and _is_table_sep(lines[i + 1].strip()):
            header = stripped                               # pipe table
            i += 2  # consume header + separator
            rows: list[str] = []
            while i < n and _is_table_row(lines[i].strip()):
                rows.append(lines[i].strip()); i += 1
            out.append(_render_table(header, rows))
            continue

        if stripped.startswith(">"):                        # blockquote
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]).strip()); i += 1
            out.append(f"<blockquote>{_md_inline(' '.join(q for q in quote if q))}</blockquote>")
            continue

        if _MD_LIST.match(raw):                             # -/* or 1. list
            block, i = _render_list(lines, i, n)
            out.append(block)
            continue

        para = [stripped]                                   # paragraph (gather wraps)
        i += 1
        while i < n and not _block_starter(lines[i]):
            para.append(lines[i].strip()); i += 1
        out.append("<p>" + _md_inline(" ".join(para)) + "</p>")

    return Markup("".join(out))
