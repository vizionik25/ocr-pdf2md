"""End-to-end tests for the ocr-pdf2md CLI pipeline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from ocr_pdf2md.main import (
    _check_tesseract,
    clean_unicode,
    convert_to_markdown,
    detect_header_level,
    extract_text_from_pdf,
    format_toc_line,
    identify_headers_footers,
    is_bullet_or_list,
    is_page_number_line,
    is_toc_page,
    join_with_dehyphenation,
    main,
    ocr_page,
)

_ENTRY = "from ocr_pdf2md import main; main()"


# ── CLI entry point ─────────────────────────────────────────────────


class TestCLI:
    def test_missing_args_exits(self):
        result = subprocess.run(
            [sys.executable, "-c", _ENTRY],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Usage" in result.stdout

    def test_nonexistent_file_exits(self, tmp_path: Path):
        result = subprocess.run(
            [sys.executable, "-c", _ENTRY, str(tmp_path / "nope.pdf"), str(tmp_path / "out.md")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stdout

    def test_full_conversion(self, text_pdf: Path, tmp_path: Path):
        out = tmp_path / "result.md"
        result = subprocess.run(
            [sys.executable, "-c", _ENTRY, str(text_pdf), str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert out.exists()
        md = out.read_text()
        assert len(md) > 0
        assert "Done" in result.stdout

    def test_main_function_writes_output(self, text_pdf: Path, tmp_path: Path):
        out = tmp_path / "output.md"
        with patch("sys.argv", ["ocr-pdf2md", str(text_pdf), str(out)]):
            main()
        assert out.exists()
        assert len(out.read_text()) > 0


# ── Text extraction ─────────────────────────────────────────────────


class TestExtractText:
    def test_extracts_pages(self, text_pdf: Path):
        pages = extract_text_from_pdf(text_pdf)
        assert len(pages) == 3

    def test_page_content(self, text_pdf: Path):
        pages = extract_text_from_pdf(text_pdf)
        assert "first paragraph" in pages[0]
        assert "bullet" in pages[1]

    def test_empty_pdf_returns_empty(self, empty_pdf: Path):
        """Empty page has no text and no images, so nothing to extract."""
        try:
            pages = extract_text_from_pdf(empty_pdf)
        except SystemExit:
            pytest.skip("tesseract not installed — blank page triggers OCR check")
        assert pages == []


# ── OCR ──────────────────────────────────────────────────────────────


class TestOCR:
    def test_check_tesseract_passes(self):
        """Succeeds if tesseract is installed on this system."""
        try:
            _check_tesseract()
        except SystemExit:
            pytest.skip("tesseract not installed")

    def test_check_tesseract_missing(self):
        """Exits with install instructions when tesseract is absent."""
        import pytesseract as pt

        with patch.object(pt, "get_tesseract_version", side_effect=pt.TesseractNotFoundError()):
            with pytest.raises(SystemExit) as exc_info:
                _check_tesseract()
            assert exc_info.value.code == 1

    def test_ocr_scanned_pdf(self, scanned_pdf: Path):
        """OCR extracts text from a scanned image page."""
        try:
            _check_tesseract()
        except SystemExit:
            pytest.skip("tesseract not installed")

        pages = extract_text_from_pdf(scanned_pdf)
        assert len(pages) >= 1
        combined = " ".join(pages).lower()
        assert "hello" in combined or "scanned" in combined

    def test_mixed_pdf_preserves_order(self, mixed_pdf: Path):
        """Digital + scanned pages both appear and maintain order."""
        try:
            _check_tesseract()
        except SystemExit:
            pytest.skip("tesseract not installed")

        pages = extract_text_from_pdf(mixed_pdf)
        assert len(pages) >= 2
        assert "DIGITAL PAGE" in pages[0] or "Digital" in pages[0]

    def test_ocr_page_no_images(self):
        """ocr_page returns empty string for a page with no images."""
        from unittest.mock import MagicMock

        mock_page = MagicMock()
        mock_page.images = []
        assert ocr_page(mock_page) == ""


# ── Unicode cleaning ─────────────────────────────────────────────────


class TestCleanUnicode:
    def test_smart_quotes(self):
        assert clean_unicode("\u201cHello\u201d") == '"Hello"'

    def test_em_dash(self):
        assert clean_unicode("\u2014") == "--"

    def test_bullet(self):
        assert clean_unicode("\u2022 item") == "- item"

    def test_copyright(self):
        assert clean_unicode("\u00A9") == "(c)"

    def test_fraction(self):
        assert clean_unicode("\u00BD") == "1/2"

    def test_arrow(self):
        assert clean_unicode("\u2192") == "->"

    def test_ellipsis(self):
        assert clean_unicode("\u2026") == "..."

    def test_non_breaking_space(self):
        assert clean_unicode("\u00A0") == " "

    def test_emoji_removed(self):
        assert clean_unicode("hello \U0001F600 world") == "hello  world"

    def test_non_ascii_stripped(self):
        result = clean_unicode("café")
        assert all(ord(c) < 128 for c in result)

    def test_newlines_preserved(self):
        assert "\n" in clean_unicode("line1\nline2")


# ── Header/footer detection ─────────────────────────────────────────


class TestHeadersFooters:
    def test_detects_repeating_lines(self):
        pages = [f"Header Line\nContent {i}\nFooter Line" for i in range(15)]
        hf = identify_headers_footers(pages)
        assert "Header Line" in hf
        assert "Footer Line" in hf

    def test_ignores_infrequent_lines(self):
        pages = ["Unique Header\nContent\nUnique Footer"]
        hf = identify_headers_footers(pages)
        assert len(hf) == 0

    def test_ignores_long_lines(self):
        long_line = "A" * 65
        pages = [f"{long_line}\nContent {i}\nEnd" for i in range(15)]
        hf = identify_headers_footers(pages)
        assert long_line not in hf

    def test_header_footer_pdf(self, header_footer_pdf: Path):
        pages = extract_text_from_pdf(header_footer_pdf)
        hf = identify_headers_footers(pages)
        assert "My Document Title" in hf


# ── Page number line detection ──────────────────────────────────────


class TestPageNumberLine:
    def test_bare_digit(self):
        assert is_page_number_line("5") is True

    def test_bare_multi_digit(self):
        assert is_page_number_line("123") is True

    def test_dashed_page_number(self):
        assert is_page_number_line("- 5 -") is True

    def test_double_dashed(self):
        assert is_page_number_line("-- 12 --") is True

    def test_page_prefix(self):
        assert is_page_number_line("Page 5") is True

    def test_page_prefix_lowercase(self):
        assert is_page_number_line("page 42") is True

    def test_roman_numeral(self):
        assert is_page_number_line("iv") is True

    def test_roman_numeral_upper(self):
        assert is_page_number_line("XII") is True

    def test_regular_text_not_page_number(self):
        assert is_page_number_line("This is regular text") is False

    def test_long_number_not_page_number(self):
        assert is_page_number_line("123456") is False

    def test_empty_string(self):
        assert is_page_number_line("") is False


# ── TOC detection & formatting ──────────────────────────────────────


class TestTOC:
    def test_is_toc_page_with_dots(self):
        toc = "\n".join([f"Chapter {i}.....{i * 10}" for i in range(1, 11)])
        assert is_toc_page(toc) is True

    def test_is_toc_page_normal_content(self):
        text = "This is normal paragraph text.\nAnother line of content.\nNo page numbers here."
        assert is_toc_page(text) is False

    def test_format_toc_dots_number(self):
        assert format_toc_line("Introduction.....1") == "1 ... Introduction"

    def test_format_toc_dots_roman(self):
        assert format_toc_line("Preface.....iii") == "iii ... Preface"

    def test_format_toc_spaces_number(self):
        assert format_toc_line("Chapter One  42") == "42 ... Chapter One"

    def test_format_toc_bare_number(self):
        assert format_toc_line("123") == "123 ..."

    def test_format_toc_bare_roman(self):
        assert format_toc_line("iv") == "iv ..."

    def test_format_toc_no_number(self):
        assert format_toc_line("Just a line") == "Just a line"

    def test_toc_pdf_conversion(self, toc_pdf: Path, tmp_path: Path):
        pages = extract_text_from_pdf(toc_pdf)
        hf = identify_headers_footers(pages)
        md = convert_to_markdown(pages, hf)
        assert "Table of Contents" in md


# ── Header detection ─────────────────────────────────────────────────


class TestDetectHeaderLevel:
    def test_all_caps_is_h2(self):
        assert detect_header_level("INTRODUCTION TO TESTING") == 2

    def test_title_case_is_h3(self):
        assert detect_header_level("Chapter One Summary") == 3

    def test_short_line_ignored(self):
        assert detect_header_level("Hi") is None

    def test_bullet_line_ignored(self):
        assert detect_header_level("- not a header") is None

    def test_long_sentence_ignored(self):
        line = "This is a very long sentence that ends with a period and is clearly not a header at all really." + "."
        assert detect_header_level(line) is None

    def test_continuation_lowercase(self):
        assert detect_header_level("continued from above", prev_line="Something") is None

    def test_prev_line_incomplete(self):
        assert detect_header_level("Next Part Here", prev_line="started with,") is None

    def test_prev_line_trailing_conjunction(self):
        assert detect_header_level("Next Part Here", prev_line="something and") is None

    def test_prev_line_none_no_crash(self):
        result = detect_header_level("SOME HEADER LINE", prev_line=None)
        assert result == 2

    def test_hash_prefix(self):
        assert detect_header_level("### Subsection") == 3


# ── Bullet/list detection ───────────────────────────────────────────


class TestBulletOrList:
    def test_bullet_dash(self):
        assert is_bullet_or_list("- item") == "bullet"

    def test_bullet_unicode(self):
        assert is_bullet_or_list("• item") == "bullet"

    def test_numbered(self):
        assert is_bullet_or_list("1. item") == "numbered"

    def test_numbered_paren(self):
        assert is_bullet_or_list("2) item") == "numbered"

    def test_regular_text(self):
        assert is_bullet_or_list("Just text") is None


# ── Dehyphenation ────────────────────────────────────────────────────


class TestDehyphenation:
    def test_joins_hyphenated(self):
        assert join_with_dehyphenation(["hyphen-", "ated"]) == "hyphenated"

    def test_joins_normal(self):
        assert join_with_dehyphenation(["line one", "line two"]) == "line one line two"

    def test_empty(self):
        assert join_with_dehyphenation([]) == ""

    def test_single_line(self):
        assert join_with_dehyphenation(["only"]) == "only"


# ── Full markdown conversion ────────────────────────────────────────


class TestConvertToMarkdown:
    def test_basic_conversion(self, text_pdf: Path):
        pages = extract_text_from_pdf(text_pdf)
        hf = identify_headers_footers(pages)
        md = convert_to_markdown(pages, hf)
        assert "## INTRODUCTION TO TESTING" in md
        assert "first paragraph" in md

    def test_bullets_formatted(self, text_pdf: Path):
        pages = extract_text_from_pdf(text_pdf)
        hf = identify_headers_footers(pages)
        md = convert_to_markdown(pages, hf)
        assert "- bullet one" in md
        assert "- bullet two" in md

    def test_no_excessive_blank_lines(self, text_pdf: Path):
        pages = extract_text_from_pdf(text_pdf)
        hf = identify_headers_footers(pages)
        md = convert_to_markdown(pages, hf)
        assert "\n\n\n" not in md

    def test_headers_footers_removed(self, header_footer_pdf: Path):
        pages = extract_text_from_pdf(header_footer_pdf)
        hf = identify_headers_footers(pages)
        md = convert_to_markdown(pages, hf)
        # "My Document Title" is detected as header/footer and should be removed
        # from body content (it may appear as a markdown heading on first occurrence)
        lines = [l.strip() for l in md.split("\n") if l.strip()]
        bare_title_lines = [l for l in lines if l == "My Document Title"]
        assert len(bare_title_lines) == 0

    def test_unicode_cleaned(self):
        """Verify clean_unicode + convert_to_markdown strips unicode."""
        page_text = "\u201cHello World\u201d \u2014 a test\n\u2022 bullet item\n\u00A9 2024"
        md = convert_to_markdown([page_text], set())
        assert "\u201c" not in md
        assert '"' in md
        assert "--" in md
        assert "(c)" in md

    def test_empty_pages_produce_empty_output(self):
        md = convert_to_markdown([], set())
        assert md.strip() == ""
