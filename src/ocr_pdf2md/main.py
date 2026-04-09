#!/usr/bin/env python3
"""
PDF to Markdown Converter with improved TOC formatting
Usage: ocr-pdf2md input.pdf output.md
"""

import io
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import pytesseract
from PIL import Image
from pypdf import PageObject, PdfReader

# Pages with fewer characters than this after pypdf extraction are treated as
# scanned images and sent to OCR.
_OCR_TEXT_THRESHOLD = 50

# Maximum column width for output lines.  Page breaks are right-justified to
# this column; paragraphs and list items are word-wrapped at this width.
_LINE_WIDTH = 171


def _check_tesseract() -> None:
    """Exit with a clear message if Tesseract is not installed."""
    try:
        pytesseract.get_tesseract_version()
    except (pytesseract.TesseractNotFoundError, FileNotFoundError):
        print(
            "Error: Tesseract is not installed.\n"
            "  Ubuntu/Debian: sudo apt install tesseract-ocr\n"
            "  macOS:         brew install tesseract\n"
            "  Windows:       https://github.com/tesseract-ocr/tesseract"
        )
        sys.exit(1)


def ocr_page(page: "PageObject") -> str:
    """Extract text from a scanned PDF page using OCR.

    Pulls embedded images from the page via pypdf, passes them to Tesseract,
    and returns the combined recognised text.
    """
    texts = []
    for image_obj in page.images:
        img = Image.open(io.BytesIO(image_obj.data))
        text = pytesseract.image_to_string(img)
        if text.strip():
            texts.append(text.strip())
    return "\n".join(texts)


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U00002600-\U000027BF"  # misc symbols
    "\U0001F200-\U0001F2FF"  # enclosed characters
    "\U0001F000-\U0001F02F"  # mahjong tiles
    "\U0001F0A0-\U0001F0FF"  # playing cards
    "]+",
    flags=re.UNICODE,
)


def clean_unicode(text: str) -> str:
    """Convert unicode characters to ASCII equivalents"""

    # Specific replacements for common characters
    replacements = {
        # Quotes
        '\u2018': "'", '\u2019': "'",  # Single quotes
        '\u201C': '"', '\u201D': '"',  # Double quotes
        '\u201A': "'", '\u201B': "'",  # Other single quotes
        '\u201E': '"', '\u201F': '"',  # Other double quotes
        '\u2039': '<', '\u203A': '>',  # Angle quotes
        '\u00AB': '<<', '\u00BB': '>>', # Guillemets

        # Dashes and hyphens
        '\u2010': '-', '\u2011': '-',  # Hyphens
        '\u2012': '-', '\u2013': '-',  # En dash
        '\u2014': '--', '\u2015': '--', # Em dash
        '\u2212': '-',                  # Minus sign

        # Spaces
        '\u00A0': ' ',  # Non-breaking space
        '\u2000': ' ', '\u2001': ' ', '\u2002': ' ',
        '\u2003': ' ', '\u2004': ' ', '\u2005': ' ',
        '\u2006': ' ', '\u2007': ' ', '\u2008': ' ',
        '\u2009': ' ', '\u200A': ' ', '\u200B': '',

        # Ellipsis
        '\u2026': '...',

        # Bullets and symbols
        '\u2022': '-',  # Bullet
        '\u2023': '-',  # Triangular bullet
        '\u2043': '-',  # Hyphen bullet
        '\u25CF': '-',  # Black circle
        '\u25E6': '-',  # White bullet
        '\u2219': '*',  # Bullet operator
        '\u25AA': '-',  # Black small square
        '\u25AB': '-',  # White small square

        # Apostrophes and primes
        '\u02BC': "'",  # Modifier letter apostrophe
        '\u2032': "'",  # Prime
        '\u2033': "''", # Double prime

        # Copyright, trademark, etc.
        '\u00A9': '(c)',   # Copyright
        '\u00AE': '(R)',   # Registered
        '\u2122': '(TM)',  # Trademark
        '\u00B0': ' deg',  # Degree
        '\u00B1': '+/-',   # Plus-minus
        '\u00D7': 'x',     # Multiplication
        '\u00F7': '/',     # Division

        # Fractions
        '\u00BC': '1/4', '\u00BD': '1/2', '\u00BE': '3/4',
        '\u2153': '1/3', '\u2154': '2/3',

        # Arrows
        '\u2190': '<-', '\u2191': '^', '\u2192': '->', '\u2193': 'v',
        '\u2194': '<->', '\u21D2': '=>', '\u21D4': '<=>',
    }

    # Apply specific replacements
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Remove emojis
    text = _EMOJI_PATTERN.sub('', text)

    # Remove other non-printable characters but keep newlines and tabs
    text = ''.join(char for char in text if ord(char) < 128 or char in '\n\t\r')

    return text


def extract_text_from_pdf(pdf_path: Path) -> list[str]:
    """Extract all text from PDF with page boundaries.

    Pages with fewer than ``_OCR_TEXT_THRESHOLD`` characters of extractable
    text are assumed to be scanned images and are sent through OCR.
    """
    reader = PdfReader(pdf_path)
    pages = []
    ocr_needed = False

    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""

        if len(page_text.strip()) < _OCR_TEXT_THRESHOLD:
            if not ocr_needed:
                _check_tesseract()
                ocr_needed = True
            print(f"  Page {i + 1}: OCR (scanned/image page)")
            page_text = ocr_page(page)

        if page_text.strip():
            pages.append(page_text)

    return pages


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

    # Check if entire line is essentially just the stamp — drop it.
    # Only applies when line is not much longer than the candidate.
    for candidate in candidates:
        if len(line_norm) <= len(candidate) * 1.25:
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
            # Re-check if remainder is itself essentially the stamp (double-stamp case)
            if len(cleaned) <= cand_len * 1.25:
                if SequenceMatcher(None, cleaned, candidate).ratio() >= threshold:
                    return None

    # If nothing meaningful remains, return None
    meaningful = sum(1 for c in cleaned if c.isalnum())
    if meaningful < 5:
        return None

    return cleaned if cleaned != line_norm else line


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


def format_toc_line(line: str) -> str:
    """Format a TOC line: move page number to front, remove dots"""
    line = line.strip()

    # Pattern 1: Text with dots leading to page number: "Text.....123"
    match = re.search(r'^(.+?)(\.{2,})(\d+)\s*$', line)
    if match:
        text = match.group(1).strip()
        page_num = match.group(3).strip()
        return f"{page_num} ... {text}"

    # Pattern 2: Text with dots leading to roman numerals: "Text.....iii"
    match = re.search(r'^(.+?)(\.{2,})([ivxlcdm]+)\s*$', line, re.IGNORECASE)
    if match:
        text = match.group(1).strip()
        page_num = match.group(3).strip()
        return f"{page_num} ... {text}"

    # Pattern 3: Text with spaces and page number at end: "Text  123" or "Text 123"
    match = re.search(r'^(.+?)\s+(\d+)\s*$', line)
    if match:
        text = match.group(1).strip()
        page_num = match.group(2).strip()
        # Only format if page number is reasonable (1-4 digits)
        if len(page_num) <= 4:
            return f"{page_num} ... {text}"

    # Pattern 4: Text with spaces and roman numeral at end
    match = re.search(r'^(.+?)\s+([ivxlcdm]+)\s*$', line, re.IGNORECASE)
    if match:
        text = match.group(1).strip()
        page_num = match.group(2).strip()
        # Only if it's a valid-looking roman numeral (1-5 chars)
        if len(page_num) <= 5:
            return f"{page_num} ... {text}"

    # Pattern 5: Line ends with just a number (page num on next line scenario)
    if re.match(r'^\d+$', line) and len(line) <= 4:
        return f"{line} ..."

    # Pattern 6: Line is just a roman numeral
    if re.match(r'^[ivxlcdm]+$', line, re.IGNORECASE) and len(line) <= 5:
        return f"{line} ..."

    # If no page number found, return as-is
    return line


def is_toc_page(text: str) -> bool:
    """Detect if a page is part of table of contents"""
    lines = text.split('\n')
    dot_lines = sum(1 for line in lines if '.....' in line or '......' in line)
    number_heavy = sum(1 for line in lines if re.search(r'\d+\s*$', line.strip()))

    total_lines = len([ln for ln in lines if ln.strip()])
    if total_lines > 0:
        if (dot_lines / total_lines > 0.3) or (number_heavy / total_lines > 0.3):
            return True
    return False


def detect_header_level(line: str, prev_line: str | None = None) -> int | None:
    """Detect if line is a header and what level"""
    line = line.strip()

    if not line or len(line) < 3:
        return None

    if line.startswith(('-', '*', '•', '●')):
        return None

    if len(line) > 80 and line.endswith(('.', '!', '?')):
        return None

    # Lines starting with ### (from PDF)
    if line.startswith('###'):
        return 3

    # Check if this looks like a continuation of previous line
    # (doesn't start with capital, starts with lowercase or special chars)
    if prev_line and line[0].islower():
        return None  # Likely continuation, not a header

    # Check if line looks incomplete (ends with hyphen, comma, or conjunction)
    if prev_line:
        incomplete_ending = prev_line.endswith(('-', ','))
        trailing_conjunctions = ['and', 'or', 'but', 'the', 'a', 'an']
        trailing_word = prev_line.split()[-1].lower() if prev_line.split() else ''
        if incomplete_ending or trailing_word in trailing_conjunctions:
            return None  # Previous line was incomplete, this continues it

    # ALL CAPS short lines = H2
    if line.isupper() and 3 < len(line) < 60 and len(line.split()) >= 2:
        return 2

    # Title Case = H3
    words = line.split()
    if 2 <= len(words) <= 12 and len(line) < 80:
        caps_count = sum(1 for w in words if w and w[0].isupper())
        if caps_count >= len(words) * 0.7 and not line.endswith(('.', '!', '?', ',')):
            return 3

    return None


def is_bullet_or_list(line: str) -> str | None:
    """Check if line starts a bullet or numbered list"""
    line = line.strip()
    if line.startswith(('•', '●', '◦', '▪', '-', '*')):
        return 'bullet'
    if re.match(r'^\d+[\.\)]\s', line):
        return 'numbered'
    return None


def join_with_dehyphenation(lines: list[str]) -> str:
    """Join lines, handling hyphenation"""
    if not lines:
        return ''

    result = []
    for line in lines:
        if result and result[-1].endswith('-'):
            result[-1] = result[-1][:-1] + line
        else:
            result.append(line)

    return ' '.join(result)


def wrap_line(text: str, width: int = _LINE_WIDTH, indent: str = "") -> str:
    """Word-wrap *text* to *width* columns.

    Continuation lines are prefixed with *indent*.  Words are never broken or
    hyphenated — if a single word exceeds *width* it is placed on its own line.
    """
    words = text.split()
    if not words:
        return text

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        # Width available on this line (first line has no indent)
        prefix = indent if lines else ""
        if len(prefix + current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word

    lines.append(current)

    # First line as-is; continuation lines get indent
    return "\n".join(
        line if i == 0 else indent + line for i, line in enumerate(lines)
    )


def convert_to_markdown(pages: list[str], headers_footers: list[str]) -> str:
    """Convert pages to markdown"""
    markdown_lines = []
    current_paragraph = []
    current_list_item = []
    in_list = False

    for page_num, page_text in enumerate(pages):
        page_text = clean_unicode(page_text)

        # Check if TOC page
        if page_num < 20 and is_toc_page(page_text):
            if current_paragraph:
                markdown_lines.append(wrap_line(join_with_dehyphenation(current_paragraph)))
                current_paragraph = []
            if current_list_item:
                markdown_lines.append(wrap_line(join_with_dehyphenation(current_list_item), indent="  "))
                current_list_item = []
                in_list = False

            if not any('Table of Contents' in line for line in markdown_lines[-5:] if line):
                markdown_lines.append('')
                markdown_lines.append('## Table of Contents\n')

            for line in page_text.split('\n'):
                line = line.strip()
                if line and not (headers_footers and is_fuzzy_match(line, headers_footers)):
                    formatted = format_toc_line(line)
                    markdown_lines.append(formatted)

            markdown_lines.append(f"{'--- Page ' + str(page_num + 1):>{_LINE_WIDTH}}")
            markdown_lines.append('')
            continue

        # Process normal content pages
        lines = page_text.split('\n')
        i = 0
        prev_line = None

        while i < len(lines):
            line = lines[i].strip()
            i += 1

            # Skip headers/footers (fuzzy match)
            if headers_footers and is_fuzzy_match(line, headers_footers):
                cleaned = remove_stamp_from_line(line, headers_footers)
                if cleaned is not None:
                    line = cleaned
                else:
                    prev_line = line
                    continue

            # Empty line
            if not line:
                if current_list_item:
                    markdown_lines.append(wrap_line(join_with_dehyphenation(current_list_item), indent="  "))
                    current_list_item = []
                if current_paragraph:
                    markdown_lines.append(wrap_line(join_with_dehyphenation(current_paragraph)))
                    current_paragraph = []
                    markdown_lines.append('')
                in_list = False
                prev_line = None
                continue

            # Check for header (pass previous line for context)
            header_level = detect_header_level(line, prev_line)
            if header_level:
                if current_list_item:
                    markdown_lines.append(wrap_line(join_with_dehyphenation(current_list_item), indent="  "))
                    current_list_item = []
                if current_paragraph:
                    markdown_lines.append(wrap_line(join_with_dehyphenation(current_paragraph)))
                    current_paragraph = []
                    markdown_lines.append('')

                clean_line = re.sub(r'^#{1,3}\s*', '', line)
                markdown_lines.append(f"{'#' * header_level} {clean_line}")
                markdown_lines.append('')
                in_list = False
                prev_line = line
                continue

            # Check for bullet or numbered list
            list_type = is_bullet_or_list(line)

            if list_type:
                if current_list_item:
                    markdown_lines.append(wrap_line(join_with_dehyphenation(current_list_item), indent="  "))
                    current_list_item = []

                if current_paragraph:
                    markdown_lines.append(wrap_line(join_with_dehyphenation(current_paragraph)))
                    current_paragraph = []
                    markdown_lines.append('')

                if list_type == 'bullet':
                    clean_line = re.sub(r'^[•●◦▪\-\*]\s*', '- ', line)
                else:
                    clean_line = line

                current_list_item = [clean_line]
                in_list = True

                while i < len(lines):
                    next_line = lines[i].strip()

                    if not next_line:
                        break

                    if headers_footers and is_fuzzy_match(next_line, headers_footers):
                        i += 1
                        continue

                    prev_for_detect = lines[i - 1].strip() if i > 0 else None
                    if is_bullet_or_list(next_line) or detect_header_level(next_line, prev_for_detect):
                        break

                    current_list_item.append(next_line)
                    i += 1

                    if next_line.endswith(('.', '!', '?')) and i < len(lines):
                        peek_next = lines[i].strip()
                        if not peek_next or is_bullet_or_list(peek_next) or detect_header_level(peek_next, next_line):
                            break

                prev_line = line
                continue

            # Regular paragraph text
            if in_list:
                if current_list_item:
                    markdown_lines.append(wrap_line(join_with_dehyphenation(current_list_item), indent="  "))
                    current_list_item = []
                in_list = False

            # Add to current paragraph
            if not current_paragraph:
                current_paragraph = [line]
            elif line.endswith('-') or not current_paragraph[-1].endswith(('.', '!', '?', ':', '"')):
                current_paragraph.append(line)
            else:
                markdown_lines.append(wrap_line(join_with_dehyphenation(current_paragraph)))
                markdown_lines.append('')
                current_paragraph = [line]
            prev_line = line

        # Flush and append page break marker
        if current_list_item:
            markdown_lines.append(wrap_line(join_with_dehyphenation(current_list_item), indent="  "))
            current_list_item = []
        if current_paragraph:
            markdown_lines.append(wrap_line(join_with_dehyphenation(current_paragraph)))
            current_paragraph = []
        in_list = False
        markdown_lines.append("")
        markdown_lines.append(f"{'--- Page ' + str(page_num + 1):>{_LINE_WIDTH}}")
        markdown_lines.append("")

    # Join and cleanup
    markdown = '\n'.join(markdown_lines)
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    markdown = re.sub(r'\s+([.,!?;:])', r'\1', markdown)
    markdown = '\n'.join(line.rstrip() for line in markdown.split('\n'))

    return markdown


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: ocr-pdf2md input.pdf output.md")
        sys.exit(1)

    input_pdf = Path(sys.argv[1])
    output_md = Path(sys.argv[2])

    if not input_pdf.exists():
        print(f"Error: {input_pdf} not found")
        sys.exit(1)

    print(f"Converting {input_pdf}...")

    try:
        pages = extract_text_from_pdf(input_pdf)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)

    print(f"  Extracted {len(pages)} pages")

    print("\nDetecting headers/footers...")
    headers_footers = identify_headers_footers(pages)
    for hf_line in sorted(headers_footers):
        print(f"  Removing header/footer: {hf_line[:50]}")

    print("\nConverting to markdown...")
    markdown = convert_to_markdown(pages, headers_footers)

    output_md.write_text(markdown, encoding='utf-8')

    print(f"\nDone: {output_md}")
    print(f"  Lines: {len(markdown.splitlines())}")
    print(f"  Size: {len(markdown)} characters")


if __name__ == "__main__":
    main()
