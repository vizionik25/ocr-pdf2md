# ocr-pdf2md

A CLI tool that converts PDF documents to clean Markdown. Handles both digital PDFs (with extractable text) and scanned/image-based PDFs via OCR.

## Installation

```bash
uv tool install ocr-pdf2md
```

### OCR requirement

For scanned or image-based PDFs, [Tesseract](https://github.com/tesseract-ocr/tesseract) must be installed on your system:

- **Ubuntu/Debian:** `sudo apt install tesseract-ocr`
- **macOS:** `brew install tesseract`
- **Windows:** https://github.com/tesseract-ocr/tesseract

Tesseract is only invoked when a page has little or no extractable text. Fully digital PDFs work without it.

## Usage

```bash
ocr-pdf2md input.pdf output.md
```

## Features

- Extracts text from digital PDFs using pypdf
- Falls back to OCR (Tesseract) for scanned/image pages
- Detects and removes repeating headers and footers
- Identifies and reformats Table of Contents pages
- Detects headings (ALL CAPS -> H2, Title Case -> H3)
- Formats bullet and numbered lists
- Rejoins hyphenated words split across lines
- Cleans Unicode characters to ASCII equivalents

## Acknowledgments

Inspired by [rubysash/pdf2md](https://github.com/rubysash/pdf2md). This project adds OCR support for scanned PDFs, improved type hints, and other enhancements.

## License

MIT
