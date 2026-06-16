"""Turn raw extracted book-chapter text into clean Markdown.

The chapter ``.txt`` files under ``data/prep_sources/chapters/`` are raw PDF
text dumps: page-break markers, repeated running headers/footers, soft-hyphen
line wraps, collapsed double-spacing, code listings carrying their printed
line numbers, and OCR noise. This module reconstructs readable Markdown —
paragraphs, headings, bullet lists, and fenced code blocks — so the prep
"view source" page renders nicely instead of dumping the raw text.

Deterministic and dependency-free. The output is the small Markdown subset
that ``webapp.textfmt.prep_markdown`` knows how to render (#/## headings,
-/1. lists, ``` fences, **bold**, `code`, links), with blank lines between
blocks so that renderer can separate them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Page / section markers the extractors leave behind:
#   CtCI:      ===== CTCI PDF_PAGE 150/712 =====   and  ========== … ==========
#   DDIA/SDI:  ----- PDF page 163 -----
_MARKER = re.compile(r"^\s*(={3,}.*={3,}|-{3,}\s*PDF\s+page\b.*-{3,})\s*$", re.I)

# "Chapter 9 | System Design…" footer (OCR may turn | into [ ] or I).
_CHAP_FOOTER = re.compile(r"(?i)^chapter\s+\d+\s*[|\[\]I]")

# A leading printed code-line number: "  12 public void foo() {".
_CODE_NUM = re.compile(r"^\s*\d{1,3}\s+(\S.*)$")
_CODE_HINT = re.compile(
    r"[{};]|=>|\b(public|private|protected|static|final|abstract|interface|class|enum|"
    r"void|return|new|import|package|extends|implements|null|true|false|"
    r"if|else|for|while|switch|case|try|catch|throw|throws|"
    r"int|long|char|byte|short|float|double|boolean|String|def|function|var|let|const)\b"
)

_BULLET = re.compile(r"^\s*[•·∙▪◦‣]\s*(.*)$")
_DASH_BULLET = re.compile(r"^\s*[-*]\s+(\S.*)$")
_NUM_BULLET = re.compile(r"^\s*\d+[.)]\s+(\S.*)$")
_STEP = re.compile(r"(?i)^step\s+\d+\b")
# SDI interview transcripts: a lone "Candidate" / "Interviewer" speaker label.
_LABEL = re.compile(r"(?i)^(candidate|interviewer)\s*:?$")


def _norm(s: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", s.strip())


def _is_footer(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    low = re.sub(r"\s+", " ", s.lower())  # the dumps double-space everything
    if len(s) < 70 and ("cracking the coding interview" in low
                        or "crackingthecoding" in low):
        return True
    if _CHAP_FOOTER.match(s):
        return True
    if re.fullmatch(r"\d{1,3}", s):                       # lone page number
        return True
    if re.fullmatch(r"(?i)part\s+[ivxlc]+", s):           # "PART II"
        return True
    if len(s) < 40 and re.search(r"(?i)\bedition\b", s):
        return True
    if re.fullmatch(r"(?i)[ivx]{1,5}\.", s):              # footnote "i." "ii."
        return True
    if re.fullmatch(r"(?i)\[\s*\d+\s*\][.\s]*[ivx]*\.?", s):  # "[1].i", "[ 4]"
        return True
    return False


def _is_heading(line: str) -> bool:
    s = line.strip().rstrip(":")
    if not s or len(s) > 70:
        return False
    if line.strip().endswith((".", ",", ";", "?", "!")):
        return False
    if _STEP.match(s):                       # "Step 4: Identify the Key Issues"
        return True
    if s.isupper() and len(s) > 2:           # "CHAPTER 4: DESIGN A RATE LIMITER"
        return True
    words = s.split()
    if len(words) > 9:
        return False
    sig = [w for w in words if len(w) > 3]   # Title Case section header
    if sig and sum(1 for w in sig if w[:1].isupper()) >= len(sig) - 1:
        return True
    return False


def _dehyphenate(lines: list[str]) -> list[str]:
    """Join soft-hyphen line wraps: ``multi‐\\nple`` → ``multiple``,
    ``accord-\\ningly`` → ``accordingly`` (only when the next line continues
    in lowercase, so real hyphenated compounds at a line end survive)."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        while i + 1 < len(lines):
            nxt = lines[i + 1].lstrip()
            if line.endswith("‐") and nxt[:1].islower():
                line = line[:-1] + nxt
                i += 1
                continue
            if re.search(r"[A-Za-z]-$", line) and nxt[:1].islower():
                line = line[:-1] + nxt
                i += 1
                continue
            break
        out.append(line)
        i += 1
    return out


def _code_block(lines: list[str], i: int) -> tuple[str, int] | None:
    """If a run of numbered code lines starts at ``i``, return the fenced
    Markdown block and the index past it; else None."""
    body: list[str] = []
    j = i
    while j < len(lines):
        m = _CODE_NUM.match(lines[j])
        if not m:
            break
        c = m.group(1).rstrip()
        body.append("}" if c == ">" else c)  # OCR renders a lone "}" as ">"
        j += 1
    if len(body) < 2:
        return None
    if sum(1 for c in body if _CODE_HINT.search(c)) < max(2, len(body) // 3):
        return None
    return "```java\n" + "\n".join(body) + "\n```", j


def _continuation(lines: list[str], start: int, n: int) -> tuple[str, int]:
    """Collect wrapped continuation lines for a list item / speaker turn,
    stopping at the next structural boundary."""
    buf: list[str] = []
    j = start
    while j < n:
        l2 = _norm(lines[j])
        if not l2:
            break
        if (_BULLET.match(lines[j]) or _DASH_BULLET.match(l2)
                or _NUM_BULLET.match(l2) or _is_heading(l2)
                or _LABEL.match(l2) or _code_block(lines, j)):
            break
        buf.append(l2)
        j += 1
    return " ".join(buf), j


def to_markdown(raw: str, book: str = "") -> str:
    lines = [ln for ln in raw.split("\n")
             if not _MARKER.match(ln) and not _is_footer(ln)]
    lines = _dehyphenate(lines)

    blocks: list[str] = []
    para: list[str] = []
    items: list[str] = []
    title_done = False

    def flush_para() -> None:
        if para:
            blocks.append(" ".join(para))
            para.clear()

    def flush_list() -> None:
        if items:
            blocks.append("\n".join(items))
            items.clear()

    n = len(lines)
    i = 0
    while i < n:
        line = _norm(lines[i])
        if not line:
            flush_para()
            flush_list()
            i += 1
            continue

        if not title_done:
            flush_para()
            blocks.append("# " + line)
            title_done = True
            i += 1
            continue

        code = _code_block(lines, i)
        if code:
            flush_para()
            flush_list()
            blocks.append(code[0])
            i = code[1]
            continue

        label = _LABEL.match(line)
        if label:
            flush_para()
            flush_list()
            j = i + 1
            while j < n and (not lines[j].strip() or lines[j].strip() == ":"):
                j += 1
            text, j = _continuation(lines, j, n)
            text = re.sub(r"^:\s*", "", text)  # the ":" often rides the next line
            blocks.append(f"**{label.group(1).capitalize()}:** {text}".strip())
            i = j
            continue

        mb = _BULLET.match(line)
        if mb is not None:
            content = mb.group(1).strip()
            flush_para()
            if content and _is_heading(content):
                flush_list()
                blocks.append("## " + content.rstrip(":"))
                i += 1
                continue
            cont, j = _continuation(lines, i + 1, n)
            text = (content + " " + cont).strip()
            if text:
                items.append("- " + text)
            i = j
            continue

        md = _DASH_BULLET.match(line) or _NUM_BULLET.match(line)
        if md:
            flush_para()
            cont, j = _continuation(lines, i + 1, n)
            items.append("- " + (md.group(1).strip() + " " + cont).strip())
            i = j
            continue

        if _is_heading(line):
            flush_para()
            flush_list()
            blocks.append("## " + line.rstrip(":"))
            i += 1
            continue

        flush_list()
        para.append(line)
        i += 1

    flush_para()
    flush_list()
    return "\n\n".join(b for b in blocks if b.strip()) + "\n"


def _book_of(name: str) -> str:
    return name.split("_", 1)[0]


def convert_dir(chapters_dir: Path) -> int:
    count = 0
    for txt in sorted(chapters_dir.glob("*.txt")):
        md = to_markdown(txt.read_text(errors="ignore"), _book_of(txt.name))
        txt.with_suffix(".md").write_text(md)
        count += 1
        print(f"{txt.name} -> {txt.stem}.md ({len(md):,} chars)")
    return count


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "data/prep_sources/chapters")
    total = convert_dir(d)
    print(f"\nConverted {total} chapter(s).")
