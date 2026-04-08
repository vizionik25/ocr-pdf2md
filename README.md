# ocr-pdf2md

A CLI tool that converts PDF documents to clean Markdown. Handles both digital PDFs (with extractable text) and scanned/image-based PDFs via OCR.

## Installation

# As a cli tool

```bash
uv tool install ocr-pdf2md
```

# As a a dependency in another project

```bash
uv add ocr-pdf2md
```

### OCR requirement

For scanned or image-based PDFs, [Tesseract](https://github.com/tesseract-ocr/tesseract) must be installed on your system:

- **Ubuntu/Debian:** `sudo apt install tesseract-ocr`
- **macOS:** `brew install tesseract`
- **Windows:** https://github.com/tesseract-ocr/tesseract

Tesseract is only invoked when a page has little or no extractable text. Fully digital PDFs work without invoking it, but due
to the fact that there are so little modern pdf's that are fully digital or image free it is a REQUIREMENT of this package.

## Usage

### CLI

```bash
ocr-pdf2md input.pdf output.md
```

### As a library

```python
from pathlib import Path
from ocr_pdf2md.main import (
    convert_to_markdown,
    extract_text_from_pdf,
    identify_headers_footers,
)

pdf_path = Path("input.pdf")

pages = extract_text_from_pdf(pdf_path)
headers_footers = identify_headers_footers(pages)
markdown = convert_to_markdown(pages, headers_footers)

Path("output.md").write_text(markdown)
```

### OCR on individual pages

`extract_text_from_pdf` automatically falls back to OCR for scanned pages, but you can also OCR pages directly:

```python
from pypdf import PdfReader
from ocr_pdf2md.main import ocr_page

reader = PdfReader("scanned.pdf")
for i, page in enumerate(reader.pages):
    text = ocr_page(page)
    print(f"--- Page {i + 1} ---\n{text}")
```

## Features

- Extracts text from digital PDFs using pypdf
- Falls back to OCR (Tesseract) for scanned/image pages
- Detects and removes repeating headers and footers -> # TODO: fix so that this works with OCR as currently it does not.
- Identifies and reformats Table of Contents pages
- Detects headings (ALL CAPS -> H2, Title Case -> H3)
- Formats bullet and numbered lists
- Rejoins hyphenated words split across lines
- Cleans Unicode characters to ASCII equivalents

## Acknowledgments

Inspired by [rubysash/pdf2md](https://github.com/rubysash/pdf2md). This project adds OCR support for scanned PDFs, improved type hints, and other enhancements.

## License

MIT
