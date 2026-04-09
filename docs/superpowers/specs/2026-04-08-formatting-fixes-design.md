# Formatting Fixes: TOC Detection, Paragraph Joining, Header Detection

## Summary

Three formatting improvements to `convert_to_markdown()`:

1. Context-based TOC detection instead of formatting-based
2. More aggressive paragraph joining across spurious blank lines
3. Tighter header detection to reject OCR garble and form field labels

## Principle

OCR extracts to raw text — that's its only job. Once text exists, every downstream function (cleanup, TOC detection, header detection, paragraph joining) runs identically regardless of text source. No OCR-specific exceptions.

## Changes

### 1. `is_toc_page()` — Context-Based Detection

Current heuristic relies on dot leaders (`'.....'`) and lines ending with numbers. This false-triggers on diagram pages with short captions.

New heuristic detects TOC by context:
- Look for a heading line containing "Table of Contents", "Contents", or "TOC"
- Look for repeated pattern: text followed by a page number (1-4 digits) at end of line
- Require a minimum number of non-empty lines (e.g. >= 5) to avoid triggering on short/garbled pages
- Dot leaders remain a signal but are not required

### 2. Paragraph Joining Across Blank Lines

Current logic unconditionally breaks paragraphs on empty lines. Scanned PDFs often produce blank lines between every line of text (wide line spacing interpreted as gaps).

Fix: when an empty line is encountered, peek at the next non-empty line. If the previous line does NOT end with terminal punctuation (`.!?`) and the next non-empty line starts lowercase, treat the blank line as a formatting artifact and continue the current paragraph.

### 3. Header Detection Tightening

Current `detect_header_level()` promotes OCR garble and form field labels to headers.

Additional rejection criteria:
- Require >= 70% alphabetic characters (rejects `| A A:`, `} -`, `=a`, etc.)
- Reject lines containing multiple consecutive special characters
- Reject lines shorter than 5 characters after stripping markdown prefixes

## Files Modified

- `src/ocr_pdf2md/main.py` — all three changes
