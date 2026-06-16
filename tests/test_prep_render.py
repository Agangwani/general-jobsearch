"""Tests for the prep source-chapter Markdown cleaner."""

from webapp.prep_render import to_markdown


def test_strips_page_markers_and_footers():
    raw = "\n".join([
        "My Chapter Title",
        "===== CTCI PDF_PAGE 150/712 =====",
        "Chapter 9 | System Design and Scalability",
        "This is body text that should survive.",
        "126 Cracking  the  Coding  Interview,  6th  Edition",
        "----- PDF page 51 -----",
        "More body text here.",
    ])
    md = to_markdown(raw, "ctci")
    assert md.startswith("# My Chapter Title")
    assert "PDF_PAGE" not in md and "PDF page" not in md
    assert "Cracking" not in md and "Chapter 9 |" not in md
    assert "body text that should survive" in md
    assert "More body text here." in md


def test_dehyphenates_soft_wraps():
    raw = "Title\nthis is accord-\ningly joined and multi‐\nple too."
    md = to_markdown(raw, "ddia")
    assert "accordingly" in md and "multiple" in md
    assert "accord-" not in md


def test_detects_headings_including_long_steps():
    raw = ("Title\nStep 1 - Understand the problem and establish design scope\n"
           "body.\nKey Concepts\nmore body.")
    md = to_markdown(raw, "sdi")
    assert "## Step 1 - Understand the problem and establish design scope" in md
    assert "## Key Concepts" in md


def test_bullets_gather_wrapped_continuation():
    raw = ("Title\n• Communicate: a key goal here. Stay\n"
           "engaged with the interviewer.\n• Go broad first: do not dive in.")
    md = to_markdown(raw, "ctci")
    assert "- Communicate: a key goal here. Stay engaged with the interviewer." in md
    assert "- Go broad first: do not dive in." in md


def test_numbered_code_listing_becomes_fenced_block():
    raw = "\n".join([
        "Title",
        "1 public class Restaurant {",
        "2 private static Restaurant instance = null;",
        "3 }",
    ])
    md = to_markdown(raw, "ctci")
    assert "```java" in md
    assert "public class Restaurant {" in md
    assert "\n1 public" not in md  # printed line numbers stripped


def test_dialogue_labels_render_bold():
    raw = "Title\nCandidate\n:\nWhat kind of limiter?\nInterviewer\n: Server-side."
    md = to_markdown(raw, "sdi")
    assert "**Candidate:** What kind of limiter?" in md
    assert "**Interviewer:** Server-side." in md
