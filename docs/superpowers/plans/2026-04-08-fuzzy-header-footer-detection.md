# Fuzzy Header/Footer Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace exact-match header/footer detection with fuzzy SequenceMatcher-based detection that handles OCR text corruption, add `--- Page N` break markers, and preserve page numbers.

**Architecture:** New helper functions (`is_page_number_line`, `is_fuzzy_match`, `remove_stamp_from_line`) support a rewritten `identify_headers_footers()` that clusters similar lines across pages using `difflib.SequenceMatcher` at 0.55 threshold. `convert_to_markdown()` switches from exact set membership to fuzzy matching for removal, and appends right-justified page break markers after each page.

**Tech Stack:** Python 3.14, difflib (stdlib), pytest

**Spec:** `docs/superpowers/specs/2026-04-08-fuzzy-header-footer-detection-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/ocr_pdf2md/main.py` | Modify | Add `is_page_number_line()`, `is_fuzzy_match()`, `remove_stamp_from_line()`; rewrite `identify_headers_footers()`; modify `convert_to_markdown()` |
| `tests/test_e2e.py` | Modify | Add/update tests for fuzzy detection, page numbers, mid-line removal, page markers |

---

### Task 1: Add `is_page_number_line()` helper

**Files:**
- Modify: `src/ocr_pdf2md/main.py` (add after line 166, after `extract_text_from_pdf`)
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_e2e.py` — new import and new test class. First, update the import block at line 12-25 to include the new function:

```python
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
```

Then add the test class after `TestHeadersFooters` (after line 210):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestPageNumberLine -v`
Expected: FAIL — `ImportError: cannot import name 'is_page_number_line'`

- [ ] **Step 3: Write the implementation**

Add to `src/ocr_pdf2md/main.py` after `extract_text_from_pdf()` (after line 165), before `identify_headers_footers()`:

```python
_PAGE_NUM_PATTERN = re.compile(
    r'^(?:'
    r'-{1,2}\s*\d{1,4}\s*-{1,2}'    # - 5 - or -- 12 --
    r'|page\s+\d{1,4}'               # Page 5, page 42
    r'|\d{1,4}'                       # bare number 1-9999
    r'|[ivxlcdm]{1,5}'               # roman numerals lowercase
    r')$',
    re.IGNORECASE,
)


def is_page_number_line(line: str) -> bool:
    """Check if a line is a bare page number (should not be treated as header/footer)."""
    line = line.strip()
    if not line:
        return False
    return _PAGE_NUM_PATTERN.match(line) is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestPageNumberLine -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ocr_pdf2md/main.py tests/test_e2e.py
git commit -m "feat: add is_page_number_line() helper for page number detection"
```

---

### Task 2: Add `is_fuzzy_match()` helper

**Files:**
- Modify: `src/ocr_pdf2md/main.py` (add after `is_page_number_line`)
- Modify: `src/ocr_pdf2md/main.py:1-10` (add `difflib` import)
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Write the failing tests**

Add new import to the import block in `tests/test_e2e.py`:

```python
from ocr_pdf2md.main import (
    _check_tesseract,
    clean_unicode,
    convert_to_markdown,
    detect_header_level,
    extract_text_from_pdf,
    format_toc_line,
    identify_headers_footers,
    is_bullet_or_list,
    is_fuzzy_match,
    is_page_number_line,
    is_toc_page,
    join_with_dehyphenation,
    main,
    ocr_page,
)
```

Add test class after `TestPageNumberLine`:

```python
class TestFuzzyMatch:
    def test_exact_match(self):
        candidates = ["Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5"]
        assert is_fuzzy_match("Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5", candidates) is True

    def test_ocr_variant_matches(self):
        candidates = ["Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5"]
        assert is_fuzzy_match("Approved For Release 2003/09/10: SIA-RDP96-00788R001700210016-5", candidates) is True

    def test_heavily_corrupted_matches(self):
        candidates = ["Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5"]
        assert is_fuzzy_match("Approved For Release 2003/09/10: GIA-RDP96-00788R001700210016-5 a...", candidates) is True

    def test_unrelated_line_no_match(self):
        candidates = ["Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5"]
        assert is_fuzzy_match("This is regular paragraph content about physics.", candidates) is False

    def test_empty_candidates(self):
        assert is_fuzzy_match("any line", []) is False

    def test_short_unrelated_no_match(self):
        candidates = ["Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5"]
        assert is_fuzzy_match("Figure A", candidates) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestFuzzyMatch -v`
Expected: FAIL — `ImportError: cannot import name 'is_fuzzy_match'`

- [ ] **Step 3: Write the implementation**

First, add the import at the top of `src/ocr_pdf2md/main.py` (after line 4, with the other stdlib imports):

```python
from difflib import SequenceMatcher
```

Then add after `is_page_number_line()`:

```python
def is_fuzzy_match(line: str, candidates: list[str], threshold: float = 0.55) -> bool:
    """Check if a line fuzzy-matches any header/footer candidate."""
    if not candidates:
        return False
    line_norm = " ".join(line.split())
    for candidate in candidates:
        ratio = SequenceMatcher(None, line_norm, candidate).ratio()
        if ratio >= threshold:
            return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestFuzzyMatch -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ocr_pdf2md/main.py tests/test_e2e.py
git commit -m "feat: add is_fuzzy_match() for SequenceMatcher-based line matching"
```

---

### Task 3: Add `remove_stamp_from_line()` helper

**Files:**
- Modify: `src/ocr_pdf2md/main.py` (add after `is_fuzzy_match`)
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Write the failing tests**

Add `remove_stamp_from_line` to the import block in `tests/test_e2e.py`:

```python
from ocr_pdf2md.main import (
    _check_tesseract,
    clean_unicode,
    convert_to_markdown,
    detect_header_level,
    extract_text_from_pdf,
    format_toc_line,
    identify_headers_footers,
    is_bullet_or_list,
    is_fuzzy_match,
    is_page_number_line,
    is_toc_page,
    join_with_dehyphenation,
    main,
    ocr_page,
    remove_stamp_from_line,
)
```

Add test class:

```python
class TestRemoveStampFromLine:
    _STAMP = "Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5"

    def test_pure_stamp_returns_none(self):
        result = remove_stamp_from_line(self._STAMP, [self._STAMP])
        assert result is None

    def test_stamp_with_noise_returns_none(self):
        line = "oye fy " + self._STAMP + " rs"
        result = remove_stamp_from_line(line, [self._STAMP])
        assert result is None

    def test_stamp_at_end_preserves_content(self):
        line = "This is real content. " + self._STAMP
        result = remove_stamp_from_line(line, [self._STAMP])
        assert result is not None
        assert "real content" in result
        assert "Approved" not in result

    def test_stamp_at_start_preserves_content(self):
        line = self._STAMP + " This is real content after the stamp."
        result = remove_stamp_from_line(line, [self._STAMP])
        assert result is not None
        assert "real content" in result

    def test_no_match_returns_original(self):
        line = "This line has no stamp in it at all."
        result = remove_stamp_from_line(line, [self._STAMP])
        assert result == line

    def test_residual_garbage_returns_none(self):
        line = "rs " + self._STAMP
        result = remove_stamp_from_line(line, [self._STAMP])
        assert result is None

    def test_double_stamp_returns_none(self):
        line = self._STAMP + " oye fy " + self._STAMP
        result = remove_stamp_from_line(line, [self._STAMP])
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestRemoveStampFromLine -v`
Expected: FAIL — `ImportError: cannot import name 'remove_stamp_from_line'`

- [ ] **Step 3: Write the implementation**

Add after `is_fuzzy_match()` in `src/ocr_pdf2md/main.py`:

```python
def remove_stamp_from_line(
    line: str, candidates: list[str], threshold: float = 0.55
) -> str | None:
    """Remove header/footer stamp embedded in a line.

    Returns the cleaned line, or None if nothing meaningful remains
    (pure stamp, or residual text < 5 non-whitespace characters).
    """
    if not candidates:
        return line

    line_norm = " ".join(line.split())

    # Check if entire line is a match — drop it
    for candidate in candidates:
        if SequenceMatcher(None, line_norm, candidate).ratio() >= threshold:
            return None

    # Try sliding window to find embedded stamp
    cleaned = line_norm
    for candidate in candidates:
        cand_len = len(candidate)
        min_win = max(10, int(cand_len * 0.7))
        max_win = int(cand_len * 1.3)

        best_ratio = 0.0
        best_start = -1
        best_end = -1

        for win_size in range(min_win, min(max_win + 1, len(cleaned) + 1)):
            for start in range(0, len(cleaned) - win_size + 1):
                window = cleaned[start : start + win_size]
                ratio = SequenceMatcher(None, window, candidate).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_start = start
                    best_end = start + win_size

        if best_ratio >= threshold and best_start >= 0:
            cleaned = (cleaned[:best_start] + " " + cleaned[best_end:]).strip()
            cleaned = " ".join(cleaned.split())

    # If nothing meaningful remains, return None
    meaningful = sum(1 for c in cleaned if c.isalnum())
    if meaningful < 5:
        return None

    return cleaned if cleaned != line_norm else line
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestRemoveStampFromLine -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ocr_pdf2md/main.py tests/test_e2e.py
git commit -m "feat: add remove_stamp_from_line() for mid-line stamp extraction"
```

---

### Task 4: Rewrite `identify_headers_footers()` with fuzzy clustering

**Files:**
- Modify: `src/ocr_pdf2md/main.py:168-184` (replace function body)
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Write the failing tests**

Replace the existing `TestHeadersFooters` class (lines 189-210 in `tests/test_e2e.py`) and add new tests:

```python
class TestHeadersFooters:
    def test_detects_repeating_lines_fuzzy(self):
        """Lines appearing on 3+ pages are detected even with OCR variation."""
        pages = [
            "Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5\nContent page 1",
            "Approved For Release 2003/09/10: SIA-RDP96-00788R001700210016-5\nContent page 2",
            "Approved For Release 2003/09/10: GIA-RDP96-00788R001700210016-5\nContent page 3",
        ]
        hf = identify_headers_footers(pages)
        assert len(hf) >= 1

    def test_three_page_threshold(self):
        """Lines on only 2 pages are not flagged."""
        pages = [
            "Some Header\nContent page 1",
            "Some Header\nContent page 2",
        ]
        hf = identify_headers_footers(pages)
        assert len(hf) == 0

    def test_three_page_threshold_met(self):
        """Lines on exactly 3 pages are flagged."""
        pages = [
            "Some Header\nContent page 1",
            "Some Header\nContent page 2",
            "Some Header\nContent page 3",
        ]
        hf = identify_headers_footers(pages)
        assert len(hf) >= 1

    def test_detects_lines_anywhere_on_page(self):
        """Header/footer lines in the middle of a page are still detected."""
        pages = [
            "Content before\nRepeated Stamp Line\nContent after",
            "Other content\nRepeated Stamp Line\nMore content",
            "Yet more\nRepeated Stamp Line\nAnd more",
        ]
        hf = identify_headers_footers(pages)
        assert len(hf) >= 1

    def test_ignores_long_lines(self):
        """Lines over 120 chars are not considered candidates."""
        long_line = "A" * 130
        pages = [f"{long_line}\nContent {i}" for i in range(5)]
        hf = identify_headers_footers(pages)
        long_matches = [c for c in hf if len(c) > 120]
        assert len(long_matches) == 0

    def test_page_numbers_excluded(self):
        """Bare page number lines are not flagged as headers/footers."""
        pages = [f"Content for page {i}\n{i}" for i in range(1, 6)]
        hf = identify_headers_footers(pages)
        page_num_matches = [c for c in hf if c.strip().isdigit()]
        assert len(page_num_matches) == 0

    def test_header_footer_pdf(self, header_footer_pdf: Path):
        pages = extract_text_from_pdf(header_footer_pdf)
        hf = identify_headers_footers(pages)
        # "My Document Title" repeats across 15 pages — must be detected
        assert any("My Document Title" in c or SequenceMatcher(None, c, "My Document Title").ratio() >= 0.55 for c in hf)
```

Add `SequenceMatcher` import at the top of the test file:

```python
from difflib import SequenceMatcher
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestHeadersFooters -v`
Expected: Some tests FAIL (fuzzy detection not implemented yet, old function uses exact matching and 10-count threshold)

- [ ] **Step 3: Write the implementation**

Replace `identify_headers_footers()` in `src/ocr_pdf2md/main.py` (lines 168-184) with:

```python
def identify_headers_footers(
    pages: list[str], threshold: float = 0.55, min_pages: int = 3
) -> list[str]:
    """Identify repeating header/footer lines using fuzzy matching.

    Scans all lines on every page (not just first/last). Lines under 120 chars
    are clustered using SequenceMatcher. Clusters spanning *min_pages* or more
    distinct pages are returned as header/footer candidates.
    """
    # Collect (normalized_line, page_index) pairs
    line_page_pairs: list[tuple[str, int]] = []
    for page_idx, page in enumerate(pages):
        for raw_line in page.split("\n"):
            norm = " ".join(raw_line.split())
            if not norm or len(norm) > 120:
                continue
            if is_page_number_line(norm):
                continue
            line_page_pairs.append((norm, page_idx))

    # Cluster similar lines
    # Each cluster: (representative, set_of_page_indices)
    clusters: list[tuple[str, set[int]]] = []

    for norm_line, page_idx in line_page_pairs:
        matched = False
        for i, (rep, page_set) in enumerate(clusters):
            ratio = SequenceMatcher(None, norm_line, rep).ratio()
            if ratio >= threshold:
                page_set.add(page_idx)
                matched = True
                break
        if not matched:
            clusters.append((norm_line, {page_idx}))

    # Return representatives of clusters spanning enough pages
    results = [
        (rep, len(page_set))
        for rep, page_set in clusters
        if len(page_set) >= min_pages
    ]
    results.sort(key=lambda x: x[1], reverse=True)
    return [rep for rep, _ in results]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestHeadersFooters -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ocr_pdf2md/main.py tests/test_e2e.py
git commit -m "feat: rewrite identify_headers_footers() with fuzzy SequenceMatcher clustering"
```

---

### Task 5: Modify `convert_to_markdown()` for fuzzy removal and page markers

**Files:**
- Modify: `src/ocr_pdf2md/main.py:317-471` (update `convert_to_markdown`)
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Write the failing tests**

Add test classes to `tests/test_e2e.py`:

```python
class TestPageMarkers:
    def test_page_markers_present(self):
        pages = ["Content on page one.", "Content on page two."]
        md = convert_to_markdown(pages, [])
        assert "--- Page 1" in md
        assert "--- Page 2" in md

    def test_page_markers_right_justified(self):
        pages = ["Content here."]
        md = convert_to_markdown(pages, [])
        for line in md.split("\n"):
            if "--- Page" in line:
                assert len(line) == 80
                assert line.endswith("--- Page 1")
                break
        else:
            assert False, "No page marker found"

    def test_last_page_has_marker(self):
        pages = ["Page one.", "Page two.", "Page three."]
        md = convert_to_markdown(pages, [])
        lines = [l for l in md.split("\n") if "--- Page" in l]
        assert len(lines) == 3
        assert "--- Page 3" in lines[-1]

    def test_marker_after_content(self):
        pages = ["Some actual content here."]
        md = convert_to_markdown(pages, [])
        lines = md.split("\n")
        marker_idx = next(i for i, l in enumerate(lines) if "--- Page 1" in l)
        # There should be content before the marker
        content_before = [l for l in lines[:marker_idx] if l.strip()]
        assert len(content_before) > 0


class TestFuzzyRemovalInMarkdown:
    _STAMP = "Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5"

    def test_fuzzy_stamps_removed(self):
        pages = ["Real content here.\n" + self._STAMP]
        md = convert_to_markdown(pages, [self._STAMP])
        assert "Approved" not in md
        assert "Real content" in md

    def test_mid_line_stamp_extracted(self):
        pages = ["Important text. " + self._STAMP + " More important text."]
        md = convert_to_markdown(pages, [self._STAMP])
        assert "Important text" in md
        assert "Approved" not in md

    def test_clean_content_preserved(self):
        pages = ["This is perfectly normal paragraph text with no stamps."]
        md = convert_to_markdown(pages, [self._STAMP])
        assert "perfectly normal" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestPageMarkers tests/test_e2e.py::TestFuzzyRemovalInMarkdown -v`
Expected: FAIL — no page markers in output, stamps not removed by fuzzy matching

- [ ] **Step 3: Update the function signature and type annotation**

In `src/ocr_pdf2md/main.py`, change the `convert_to_markdown` signature (line 317) from:

```python
def convert_to_markdown(pages: list[str], headers_footers: set[str]) -> str:
```

to:

```python
def convert_to_markdown(pages: list[str], headers_footers: list[str]) -> str:
```

- [ ] **Step 4: Replace exact header/footer checks with fuzzy matching**

In `convert_to_markdown()`, replace the exact membership check at line 360:

```python
            if line in headers_footers:
```

with:

```python
            if headers_footers and is_fuzzy_match(line, headers_footers):
                cleaned = remove_stamp_from_line(line, headers_footers)
                if cleaned is not None:
                    line = cleaned
                else:
                    prev_line = line
                    continue
```

Similarly, replace the check at line 422 inside the list-continuation loop:

```python
                    if next_line in headers_footers:
```

with:

```python
                    if headers_footers and is_fuzzy_match(next_line, headers_footers):
```

- [ ] **Step 5: Add page break markers**

At the end of the page loop in `convert_to_markdown()`, just before `continue` for TOC pages and at the end of the `for page_num, page_text in enumerate(pages):` loop body, add the page marker. The cleanest approach is to add it once right before the loop increments. Replace the closing section of the page loop.

After the `while i < len(lines):` loop ends (the last line of processing for a normal page), add:

```python
        # Append page break marker
        if current_list_item:
            markdown_lines.append(join_with_dehyphenation(current_list_item))
            current_list_item = []
        if current_paragraph:
            markdown_lines.append(join_with_dehyphenation(current_paragraph))
            current_paragraph = []
        in_list = False
        markdown_lines.append("")
        markdown_lines.append(f"{'--- Page ' + str(page_num + 1):>80}")
        markdown_lines.append("")
```

Also add the page marker after the TOC page `continue` block. Before the existing `continue` for TOC pages, add:

```python
            markdown_lines.append(f"{'--- Page ' + str(page_num + 1):>80}")
            markdown_lines.append("")
```

- [ ] **Step 6: Remove the old flush logic at the end**

The "Flush remaining content" block at lines 459-462 is now handled by the per-page flush above. Remove:

```python
    # Flush remaining content
    if current_list_item:
        markdown_lines.append(join_with_dehyphenation(current_list_item))
    if current_paragraph:
        markdown_lines.append(join_with_dehyphenation(current_paragraph))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestPageMarkers tests/test_e2e.py::TestFuzzyRemovalInMarkdown -v`
Expected: All PASS

- [ ] **Step 8: Run full test suite**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py -v`
Expected: All PASS. Some existing tests may need minor adjustments due to the new page markers appearing in output — if so, update assertions to account for `--- Page N` lines.

- [ ] **Step 9: Commit**

```bash
git add src/ocr_pdf2md/main.py tests/test_e2e.py
git commit -m "feat: fuzzy header/footer removal in convert_to_markdown with page break markers"
```

---

### Task 6: Update `main()` and fix existing tests

**Files:**
- Modify: `src/ocr_pdf2md/main.py:474-512` (update `main()` print output)
- Modify: `tests/test_e2e.py` (fix any broken existing tests)

- [ ] **Step 1: Update `main()` to work with list return type**

In `src/ocr_pdf2md/main.py`, the `main()` function at line 497-499 currently does:

```python
    headers_footers = identify_headers_footers(pages)
    for hf_line in sorted(headers_footers):
        print(f"  Removing header/footer: {hf_line[:50]}")
```

This still works since `sorted()` works on lists too. No change needed here.

- [ ] **Step 2: Run full test suite and fix failures**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py -v`

Likely fixes needed in existing tests:

In `TestConvertToMarkdown.test_basic_conversion` — add awareness of page markers:

```python
    def test_basic_conversion(self, text_pdf: Path):
        pages = extract_text_from_pdf(text_pdf)
        hf = identify_headers_footers(pages)
        md = convert_to_markdown(pages, hf)
        assert "## INTRODUCTION TO TESTING" in md
        assert "first paragraph" in md
        assert "--- Page 1" in md
```

In `TestConvertToMarkdown.test_headers_footers_removed` — the header/footer detection now uses fuzzy matching and threshold of 3 pages instead of 10, so verify the test fixture still produces expected results. The `header_footer_pdf` fixture creates 15 pages with "My Document Title" repeated, so this should still be detected.

In `TestConvertToMarkdown.test_empty_pages_produce_empty_output` — empty pages list should produce empty output with no markers:

```python
    def test_empty_pages_produce_empty_output(self):
        md = convert_to_markdown([], [])
        assert md.strip() == ""
```

Note the second argument changes from `set()` to `[]`.

In `TestConvertToMarkdown.test_unicode_cleaned`:

```python
    def test_unicode_cleaned(self):
        page_text = "\u201cHello World\u201d \u2014 a test\n\u2022 bullet item\n\u00A9 2024"
        md = convert_to_markdown([page_text], [])
        assert "\u201c" not in md
        assert '"' in md
        assert "--" in md
        assert "(c)" in md
```

- [ ] **Step 3: Run full test suite again**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/ocr_pdf2md/main.py tests/test_e2e.py
git commit -m "fix: update existing tests for fuzzy detection and page marker changes"
```

---

### Task 7: Integration test with real OCR-like data

**Files:**
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Write integration test**

Add a test class that simulates the real-world OCR problem from the sample document:

```python
class TestOCRHeaderFooterIntegration:
    """Integration test simulating real OCR output with corrupted stamps."""

    _VARIANTS = [
        "Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5",
        "Approved For Release 2003/09/10: SIA-RDP96-00788R001700210016-5",
        "Approved For Release 2003/09/10: GIA-RDP96-00788R001700210016-5 a...",
        "c F, Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5",
        "Approved For Release 2003/09/10: CLA-RDP96-00788R001700210016-5 oye fy",
    ]

    def test_all_variants_detected(self):
        pages = []
        for i, variant in enumerate(self._VARIANTS):
            pages.append(f"{variant}\nReal content for page {i + 1} goes here with enough detail.")
        hf = identify_headers_footers(pages)
        assert len(hf) >= 1

    def test_all_variants_removed_from_output(self):
        pages = []
        for i, variant in enumerate(self._VARIANTS):
            pages.append(f"{variant}\nReal content for page {i + 1} goes here with enough detail.")
        hf = identify_headers_footers(pages)
        md = convert_to_markdown(pages, hf)
        assert "Approved" not in md
        assert "CIA-RDP" not in md
        assert "SIA-RDP" not in md
        for i in range(len(self._VARIANTS)):
            assert f"Real content for page {i + 1}" in md

    def test_page_markers_present_for_all_pages(self):
        pages = []
        for i, variant in enumerate(self._VARIANTS):
            pages.append(f"{variant}\nReal content for page {i + 1} goes here with enough detail.")
        hf = identify_headers_footers(pages)
        md = convert_to_markdown(pages, hf)
        for i in range(1, len(self._VARIANTS) + 1):
            assert f"--- Page {i}" in md

    def test_duplicate_stamps_on_single_page(self):
        stamp = "Approved For Release 2003/09/10: CIA-RDP96-00788R001700210016-5"
        pages = [
            f"{stamp}\nContent page 1.\n{stamp}",
            f"{stamp} oye fy {stamp}\nContent page 2.",
            f"Content page 3.\n{stamp} a...\n{stamp}",
        ]
        hf = identify_headers_footers(pages)
        md = convert_to_markdown(pages, hf)
        assert "Approved" not in md
        assert "Content page 1" in md
        assert "Content page 2" in md
        assert "Content page 3" in md
```

- [ ] **Step 2: Run the integration tests**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py::TestOCRHeaderFooterIntegration -v`
Expected: All PASS

- [ ] **Step 3: Run complete test suite one final time**

Run: `cd /home/nik/pdf2md && uv run pytest tests/test_e2e.py -v --tb=short`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add OCR header/footer integration tests with real-world stamp variants"
```
