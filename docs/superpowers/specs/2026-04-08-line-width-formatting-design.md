# Line Width & Page Break Formatting

## Summary

Reformat markdown output for 171-column width: right-justify page breaks to column 171, word-wrap paragraphs and list items at 171 columns with no introduced hyphenation.

## Motivation

The output is primarily used as LLM knowledge but must remain human-readable. The current 80-column page breaks waste horizontal space. A 171-column layout uses the full width while keeping clean, consistent formatting.

## Changes

### Constants

- `_LINE_WIDTH = 171` — single source of truth for output width.

### Page Breaks

- Change right-justification from `:>80` to `:>171` in both TOC and normal page output paths.

### New Function: `wrap_line(text, width, indent)`

- Splits on whitespace, accumulates words until the next word would exceed `width`.
- Starts a new line prefixed with `indent` when a word won't fit.
- Never breaks/hyphenates a word. If a single word exceeds `width`, it gets its own line.
- Default: `width=171`, `indent=""`.

### Where Wrapping Applies

| Content type | Wrapped? | Indent on continuation |
|---|---|---|
| Paragraphs | Yes | None |
| List items | Yes | 2 spaces |
| Headers | No | N/A |
| TOC lines | No | N/A |
| Page breaks | No (right-justified) | N/A |

### De-hyphenation

Unchanged. `join_with_dehyphenation()` continues to reassemble PDF-split words. Legitimately hyphenated words (e.g. "well-known") pass through untouched. The new wrapper never introduces hyphenated breaks.

## Files Modified

- `src/ocr_pdf2md/main.py` — add `_LINE_WIDTH`, add `wrap_line()`, update `convert_to_markdown()` page break format strings, apply `wrap_line()` to paragraph and list item output.
