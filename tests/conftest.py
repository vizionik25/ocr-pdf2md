"""Shared fixtures for ocr-pdf2md end-to-end tests."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)


def _make_text_pdf(pages: list[str], path: Path) -> Path:
    """Create a PDF where each page contains extractable text."""
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines = escaped.split("\n")
        parts = ["BT", "/F1 12 Tf", "72 720 Td"]
        for i, line in enumerate(lines):
            if i > 0:
                parts.append("0 -14 Td")
            parts.append(f"({line}) Tj")
        parts.append("ET")

        stream = DecodedStreamObject()
        stream.set_data("\n".join(parts).encode())

        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        resources = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = writer._add_object(stream)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def _make_image_pdf(texts: list[str], path: Path) -> Path:
    """Create a PDF where each page is an embedded image of rendered text.

    pypdf's extract_text() returns empty for these pages, forcing the OCR path.
    """
    writer = PdfWriter()
    for text in texts:
        img = Image.new("RGB", (612, 792), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except OSError:
            font = ImageFont.load_default()
        draw.text((50, 50), text, fill="black", font=font)

        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        # Build a PDF page that embeds this image as an XObject
        page = writer.add_blank_page(width=612, height=792)

        img_stream = DecodedStreamObject()
        img_stream.set_data(img_bytes.getvalue())
        img_stream[NameObject("/Type")] = NameObject("/XObject")
        img_stream[NameObject("/Subtype")] = NameObject("/Image")
        img_stream[NameObject("/Width")] = NumberObject(612)
        img_stream[NameObject("/Height")] = NumberObject(792)
        img_stream[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
        img_stream[NameObject("/BitsPerComponent")] = NumberObject(8)
        img_stream[NameObject("/Filter")] = NameObject("/DCTDecode")

        img_ref = writer._add_object(img_stream)

        content = DecodedStreamObject()
        content.set_data(b"q 612 0 0 792 0 0 cm /Img0 Do Q")
        content_ref = writer._add_object(content)

        xobjects = DictionaryObject({NameObject("/Img0"): img_ref})
        resources = DictionaryObject({NameObject("/XObject"): xobjects})
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = content_ref

    with open(path, "wb") as f:
        writer.write(f)
    return path


@pytest.fixture()
def text_pdf(tmp_path: Path) -> Path:
    """A simple multi-page digital PDF with extractable text."""
    pages = [
        "INTRODUCTION TO TESTING\n\nThis is the first paragraph of the document.\nIt spans multiple lines across the page.\n\nAnother paragraph here with more text.",
        "SECOND CHAPTER\n\nMore content on the second page with additional detail.\n- bullet one\n- bullet two\n- bullet three",
        "FINAL NOTES\n\nClosing remarks for the document with enough text to exceed the OCR threshold easily.",
    ]
    return _make_text_pdf(pages, tmp_path / "text.pdf")


@pytest.fixture()
def toc_pdf(tmp_path: Path) -> Path:
    """A PDF with a table-of-contents page followed by content."""
    toc = "\n".join(
        [
            "Introduction.....1",
            "Chapter One.....5",
            "Chapter Two.....10",
            "Chapter Three.....15",
            "Conclusion.....20",
            "Appendix A.....25",
            "Appendix B.....30",
            "References.....35",
            "Index.....40",
            "Glossary.....45",
        ]
    )
    content = "ACTUAL CONTENT\n\nThis is real body text after the TOC."
    return _make_text_pdf([toc, content], tmp_path / "toc.pdf")


@pytest.fixture()
def unicode_pdf(tmp_path: Path) -> Path:
    """A PDF with Unicode characters that should be cleaned."""
    text = (
        "\u201cHello World\u201d \u2014 a test\n"
        "\u2022 bullet item\n"
        "\u00A9 2024 Company\n"
        "\u00BD fraction test\n"
        "\u2192 arrow test"
    )
    return _make_text_pdf([text], tmp_path / "unicode.pdf")


@pytest.fixture()
def header_footer_pdf(tmp_path: Path) -> Path:
    """A PDF with repeating headers/footers across many pages."""
    pages = []
    for i in range(15):
        pages.append(f"My Document Title\nPage content for page {i + 1} goes here with enough text.\nPage {i + 1}")
    return _make_text_pdf(pages, tmp_path / "hf.pdf")


@pytest.fixture()
def empty_pdf(tmp_path: Path) -> Path:
    """A PDF with a blank page (no text)."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    path = tmp_path / "empty.pdf"
    with open(path, "wb") as f:
        writer.write(f)
    return path


@pytest.fixture()
def scanned_pdf(tmp_path: Path) -> Path:
    """A PDF with embedded images instead of text (simulates scanned pages)."""
    return _make_image_pdf(["Hello from a scanned page"], tmp_path / "scanned.pdf")


@pytest.fixture()
def mixed_pdf(tmp_path: Path) -> Path:
    """A PDF mixing digital text pages and scanned image pages."""
    # We build this by combining a text page and an image page
    text_path = _make_text_pdf(
        ["DIGITAL PAGE\n\nThis page has real extractable text content here."],
        tmp_path / "text_part.pdf",
    )
    img_path = _make_image_pdf(
        ["Scanned page content"],
        tmp_path / "img_part.pdf",
    )

    from pypdf import PdfReader

    writer = PdfWriter()
    for p in PdfReader(text_path).pages:
        writer.add_page(p)
    for p in PdfReader(img_path).pages:
        writer.add_page(p)

    out = tmp_path / "mixed.pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out
