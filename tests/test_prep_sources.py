"""Mapping a prep module's source_refs to its book chapter + local PDF."""

from webapp import prep_sources


def test_parse_ref_detects_book_and_chapter():
    assert prep_sources.parse_ref("CtCI Ch. 1, pp. 88–104") == ("ctci", 1)
    assert prep_sources.parse_ref("DDIA Ch.5 (Kleppmann), pp.145-190") == ("ddia", 5)
    # chapter in parens, after the page range
    assert prep_sources.parse_ref("DDIA pp.191-208 (Kleppmann, …, Ch.6)") == ("ddia", 6)
    assert prep_sources.parse_ref("SDI Ch.3, pp.42-50; Grokking SDI") == ("sdi", 3)
    # roman-numeral front matter → book known, no chapter file
    assert prep_sources.parse_ref("CtCI Ch. VI, pp. 38–62") == ("ctci", None)
    assert prep_sources.parse_ref("just some notes, no book") is None
    assert prep_sources.parse_ref("") is None


def test_chapter_path_and_source_resolution(tmp_path):
    chapters = tmp_path / "data" / "prep_sources" / "chapters"
    chapters.mkdir(parents=True)
    (chapters / "ctci_ch01_arrays-and-strings.txt").write_text(
        "Arrays and Strings\n===== CTCI PDF_PAGE 100/712 PRINTED_PAGE 1 =====\nbody text")
    pw = tmp_path / "prep_work"
    pw.mkdir()
    (pw / "Cracking-the-Coding-Interview-6th-Edition.pdf").write_bytes(b"%PDF-1.4")

    assert prep_sources.chapter_path(chapters, "ctci", 1).name \
        == "ctci_ch01_arrays-and-strings.txt"
    assert prep_sources.chapter_path(chapters, "ctci", 99) is None

    info = prep_sources.source_for(tmp_path, "CtCI Ch. 1, pp. 88-104")
    assert info["book"] == "ctci" and info["has_text"] and info["has_pdf"]
    assert info["pdf_page"] == 100                      # read from the PDF_PAGE marker
    assert prep_sources.pdf_path(tmp_path, "ctci").name.startswith("Cracking")
    assert prep_sources.available(tmp_path, "CtCI Ch. 1") is True


def test_source_for_unknown_book_or_missing_files(tmp_path):
    assert prep_sources.source_for(tmp_path, "no book named here") is None
    # book known but no chapter file / PDF present → flags false, no crash
    info = prep_sources.source_for(tmp_path, "DDIA Ch.5")
    assert info["book"] == "ddia" and not info["has_text"] and not info["has_pdf"]
    assert prep_sources.available(tmp_path, "DDIA Ch.5") is False
