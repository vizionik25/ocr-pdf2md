# Fuzzy Header/Footer Detection and Removal

## Problem

The current `identify_headers_footers()` function only checks the first and last lines of each page and requires exact string matches appearing 10+ times. This fails completely for OCR-extracted text where:

1. **Position is unpredictable** — Tesseract does not guarantee spatial ordering, so headers/footers land anywhere in the extracted text, not just at the top/bottom of the page.
2. **Duplication within pages** — the same header/footer often appears 2-5 times on a single page of OCR output.
3. **OCR character corruption** — Tesseract produces variants of the same text: `CIA` becomes `SIA`, `GIA`, `CLA`, `E1A`, `ci&`, `CH0`, etc. Exact matching misses all of these.
4. **Noise concatenation** — OCR glues random characters onto stamps: `oye fy`, `a...`, `rs`, `oa` appended to otherwise recognizable header text.

Since ocr-pdf2md is a preprocessing tool for LLM ingestion, leaving redundant headers/footers in the output directly causes hallucination. Aggressive removal is preferred over conservative preservation.

## Requirements

- Detect and remove repeating headers/footers regardless of where they appear on the page.
- Handle fuzzy OCR variants — lines that are visually the same header but differ in characters due to OCR errors.
- Threshold: a line (or fuzzy cluster of lines) appearing on **3+ distinct pages** is considered a header/footer.
- **Preserve page numbers** — bare page number lines (e.g., `5`, `- 5 -`, `Page 5`) must not be flagged as headers/footers.
- Add `--- Page N` markers (right-justified) after each page's content as a reference anchor for human learners receiving LLM instruction.
- Handle mid-line stamps — where a header/footer string is embedded within a line of real content, extract and remove only the stamp portion.
- Drop residual OCR garbage lines (under ~5 meaningful characters after stamp removal).

## Design

### Detection: Fuzzy Line Matching with SequenceMatcher

Replace `identify_headers_footers()` with a new function:

1. Split every page into lines. Consider **all lines**, not just first/last.
2. Filter to candidate lines under ~120 characters (headers/footers are not paragraphs).
3. Normalize lines before comparison: strip whitespace, collapse multiple spaces.
4. Exclude page number lines from consideration (see `is_page_number_line()` below).
5. Compare lines across pages using `difflib.SequenceMatcher`.
   - Similarity threshold: **0.55** (tuned for OCR corruption levels seen in real samples).
6. Cluster similar lines together. If a cluster spans **3+ distinct pages**, the cluster's representative string is a header/footer candidate.
7. Return a list of candidate representative strings (ordered by cluster size descending).

Clustering approach:
- Iterate through all short lines from all pages.
- For each line, check if it matches any existing cluster representative at >= 0.55 similarity.
- If yes, add it to that cluster (and record which page it came from).
- If no, start a new cluster with this line as the representative.
- After processing all lines, return representatives of clusters that span 3+ distinct pages.

### Removal: Line-Level Filtering

During `convert_to_markdown()`, for each line:

1. Compare against all candidate representatives using SequenceMatcher at the same 0.55 threshold.
2. If the **entire line** matches a candidate: drop it.
3. If a candidate string is **embedded within a longer line** (the line contains real content plus a stamp): attempt to identify and remove the stamp portion, keeping the remaining content. Detection uses a sliding window: for each candidate, slide a window of `len(candidate) +/- 30%` characters across the line and check each window against the candidate at >= 0.55 similarity. The best-matching window is removed.
4. After removal, if the remaining line has fewer than ~5 meaningful characters: drop it as OCR residue.

### Page Number Handling

`is_page_number_line(line: str) -> bool`:
- Returns True for lines that are bare page numbers: `5`, `- 5 -`, `Page 5`, `-- 5 --`, roman numerals like `iv`, `xii`.
- These lines are excluded from header/footer candidate detection.
- They are also dropped from output since canonical `--- Page N` markers replace them.

### Page Break Markers

After each page's content is processed and appended to the output, append:

```
                                                                    --- Page N
```

Right-justified to column 80, on its own line, acting as a page break separator. `N` is the 1-based page index (derived from position, not OCR). Every page gets one, including the last. Implementation: `f"{'--- Page ' + str(n):>80}"`.

## File Changes

### `src/ocr_pdf2md/main.py`

1. **New import:** `from difflib import SequenceMatcher`
2. **New function `is_page_number_line(line: str) -> bool`** — identifies bare page number lines.
3. **Replace `identify_headers_footers(pages)`** — new implementation using fuzzy clustering as described above. Same function signature, but returns a list of representative strings instead of a set of exact strings.
4. **New function `is_fuzzy_match(line: str, candidates: list[str], threshold: float = 0.55) -> bool`** — checks if a line fuzzy-matches any candidate.
5. **New function `remove_stamp_from_line(line: str, candidates: list[str], threshold: float = 0.55) -> str | None`** — for mid-line stamps, returns the cleaned line or None if nothing meaningful remains.
6. **Modify `convert_to_markdown()`**:
   - Change header/footer check from `line in headers_footers` (exact set membership) to fuzzy matching via `is_fuzzy_match()`.
   - For lines that partially match, use `remove_stamp_from_line()`.
   - Append `--- Page N` (right-justified) after each page's content.

### `tests/test_e2e.py`

7. **Update `TestHeadersFooters`**:
   - Test that fuzzy variants (e.g., `CIA` vs `SIA` vs `GIA`) are clustered together.
   - Test 3-page threshold (2 pages = not detected, 3 pages = detected).
   - Test that lines appearing anywhere on the page (not just first/last) are caught.
8. **New `TestPageNumbers`**:
   - Test that bare page number lines are not flagged as headers/footers.
   - Test that `--- Page N` markers appear in output, right-justified, after each page.
9. **New `TestMidLineStampRemoval`**:
   - Test that a line like `"real content Approved For Release... real content"` has the stamp removed but content preserved.
   - Test that residual garbage lines (< 5 chars after removal) are dropped.

## Future Work (Roadmap)

### Stage A: Normalized Substring Matching

A fast pre-filter that runs before SequenceMatcher. Extract canonical tokens from each line (strip punctuation, normalize whitespace, lowercase). Look for lines sharing long common substrings (15+ characters). If a normalized substring appears on 3+ pages, it is a high-confidence candidate. This reduces the number of comparisons SequenceMatcher needs to make.

### Stage C: Regex Pattern Generation

Auto-generate OCR-tolerant character-class regexes from confirmed candidates. For example, `CIA` becomes `[CSGEc][IlL1][Aa&]`. These compiled patterns enable fast removal and better mid-line extraction for heavily corrupted OCR output. Built from Stage A + B confirmed candidates.
