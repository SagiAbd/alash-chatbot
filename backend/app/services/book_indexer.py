"""
Book indexer service.

Loads JSON OCR page arrays, extracts key pages for LLM analysis,
uses the LLM to identify every work listed in the table of contents,
then extracts both work-level texts and raw pages for deterministic retrieval.
"""

import json
import logging
import re
from typing import List, Literal, Optional

from langchain_core.documents import Document as LangchainDocument
from pydantic import BaseModel

from app.services.llm.llm_factory import LLMFactory

logger = logging.getLogger(__name__)

# ─── TOC search terms (case-insensitive) ──────────────────────────────────────

TOC_PATTERNS = [
    "мазмұны",
    "мазмуны",
    "содержание",
    "table of contents",
    "contents",
]

# ─── Pydantic models ──────────────────────────────────────────────────────────


class WorkEntry(BaseModel):
    """A single work identified from the table of contents."""

    title: str
    start_page: int
    end_page: int


class TOCEntry(BaseModel):
    """The document's table of contents page span."""

    title: str
    start_page: int
    end_page: int


class BookMetadata(BaseModel):
    """Top-level metadata extracted from the book."""

    book_title: str = ""
    main_author: str = ""
    publisher: str = ""
    year: str = ""


class BookIndex(BaseModel):
    """Full structured output from LLM book analysis."""

    summary: str
    metadata: BookMetadata
    works: List[WorkEntry]
    toc: Optional[TOCEntry] = None
    toc_find_failed: bool = False
    toc_failure_reason: str = ""


class BookIndexingError(Exception):
    """Raised when the LLM fails to produce a usable book index."""


class BookMetadataResult(BaseModel):
    """Metadata extracted from the first and last pages of the book."""

    summary: str
    metadata: BookMetadata


class TOCSearchResult(BaseModel):
    """TOC search result extracted from focused page windows."""

    works: List[WorkEntry]
    toc: Optional[TOCEntry] = None
    toc_find_failed: bool = False
    toc_failure_reason: str = ""


# ─── Text cleaning ────────────────────────────────────────────────────────────

# Allowed Unicode ranges: Cyrillic, Latin, digits, basic punctuation,
# Kazakh-specific characters and common symbols.
_ALLOWED_RE = re.compile(
    r"[^\u0400-\u04FF\u0041-\u007A\u0061-\u007A\u0030-\u0039"
    r"\u0020-\u002F\u003A-\u0040\u005B-\u0060\u007B-\u007E"
    r"\u04D8\u04D9\u0492\u0493\u049A\u049B\u04A2\u04A3"
    r"\u04E8\u04E9\u04B0\u04B1\u04AE\u04AF\u04BA\u04BB\u0406\u0456"
    r"\n\r\t]",
    re.UNICODE,
)

# Lines that are purely numbers / punctuation / whitespace (e.g. page footers)
_NOISE_LINE_RE = re.compile(r"^\s*[\d\W]+\s*$")
_TOC_LINE_RE = re.compile(r"(?:\.{2,}\s*|\s)\d{1,4}\s*$")


def clean_page_text(text: str) -> str:
    """Remove OCR artefacts from a page's text.

    Args:
        text: Raw OCR text for one page.

    Returns:
        Cleaned text with artefacts removed.
    """
    # 1. Remove disallowed characters
    text = _ALLOWED_RE.sub(" ", text)

    # 2. Collapse runs of 4+ identical chars to 3
    text = re.sub(r"(.)\1{3,}", lambda m: m.group(1) * 3, text)

    # 3. Drop pure-noise lines (only digits/punctuation)
    lines = [ln for ln in text.splitlines() if not _NOISE_LINE_RE.match(ln)]

    return "\n".join(lines).strip()


def _parse_page_number(value: object, fallback: int) -> int:
    """Coerce a JSON page field into a positive integer."""

    try:
        page_number = int(value)
    except (TypeError, ValueError):
        return fallback

    return page_number if page_number > 0 else fallback


def _page_number(page: LangchainDocument, fallback: int) -> int:
    """Read the canonical OCR page number from document metadata."""

    return _parse_page_number(page.metadata.get("page"), fallback)


def _contains_toc_pattern(text: str) -> bool:
    """Return True when the page explicitly mentions the table of contents."""

    text_lower = text.lower()
    return any(pattern in text_lower for pattern in TOC_PATTERNS)


def _looks_like_toc_page(text: str) -> bool:
    """Heuristically detect TOC continuation pages without a heading."""

    if _contains_toc_pattern(text):
        return True

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    toc_like_lines = sum(
        1
        for line in lines[:40]
        if _TOC_LINE_RE.search(line) and any(char.isalpha() for char in line)
    )
    return toc_like_lines >= 2


def find_toc_page_indexes(pages: List[LangchainDocument]) -> List[int]:
    """Find the OCR page indexes that belong to the table of contents."""

    selected: dict[int, None] = {}
    total_pages = len(pages)

    for index, page in enumerate(pages):
        if not _contains_toc_pattern(page.page_content):
            continue

        selected[index] = None
        for next_index in range(index + 1, min(index + 6, total_pages)):
            if not _looks_like_toc_page(pages[next_index].page_content):
                break
            selected[next_index] = None

    return sorted(selected)


AnalysisMode = Literal["candidate_toc", "last_pages", "first_pages"]


def _render_page_block(
    pages: List[LangchainDocument],
    indexes: List[int],
) -> str:
    """Render OCR pages as numbered blocks for the analysis prompt."""

    parts: List[str] = []
    for idx in indexes:
        page_num = _page_number(pages[idx], idx + 1)
        parts.append(f"--- Page {page_num} ---\n{pages[idx].page_content}")
    return "\n\n".join(parts)


def _analysis_section(
    title: str,
    pages: List[LangchainDocument],
    indexes: List[int],
    empty_text: str,
) -> str:
    """Build one labeled analysis section for the LLM prompt."""

    if indexes:
        return f"{title}:\n{_render_page_block(pages, indexes)}"
    return f"{title}:\n{empty_text}"


def _window_indexes(
    pages: List[LangchainDocument],
    *,
    from_start: bool,
    window_size: int,
) -> List[int]:
    """Return a contiguous page window from the start or end."""

    if not pages:
        return []

    if from_start:
        return list(range(min(window_size, len(pages))))

    start = max(0, len(pages) - window_size)
    return list(range(start, len(pages)))


def build_metadata_input(pages: List[LangchainDocument]) -> str:
    """Collect first and last pages for metadata extraction."""

    n = len(pages)
    first_indexes = list(range(min(3, n)))
    last_indexes = list(range(max(0, n - 2), n))

    sections = [
        _analysis_section(
            "First pages",
            pages,
            first_indexes,
            "(document is empty)",
        ),
        _analysis_section(
            "Last pages",
            pages,
            last_indexes,
            "(document is empty)",
        ),
    ]

    return "\n\n".join(section for section in sections if section.strip())


def _select_pages_in_range(
    pages: List[LangchainDocument],
    start_page: int,
    end_page: int,
) -> List[LangchainDocument]:
    """Select OCR pages by their actual page numbers, not list positions."""

    return [
        page
        for index, page in enumerate(pages, start=1)
        if start_page <= _page_number(page, index) <= end_page
    ]


# ─── Page loading ─────────────────────────────────────────────────────────────


def load_pages_from_json(file_path: str) -> List[LangchainDocument]:
    """Load and clean pages from a JSON OCR file.

    Expected format: ``[{"page": 2, "file": "0002.png", "text": "..."}, ...]``

    Args:
        file_path: Local filesystem path to the JSON file.

    Returns:
        List of LangchainDocument objects sorted by page number, with
        cleaned text and ``page`` in metadata.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise BookIndexingError("JSON file must be a list of page objects")

    pages = sorted(data, key=lambda item: _parse_page_number(item.get("page"), 0))
    return [
        LangchainDocument(
            page_content=clean_page_text(item.get("text", "")),
            metadata={"page": _parse_page_number(item.get("page"), idx + 1)},
        )
        for idx, item in enumerate(pages)
    ]


# ─── Analysis input construction ─────────────────────────────────────────────


def build_analysis_input(
    pages: List[LangchainDocument],
    mode: AnalysisMode = "candidate_toc",
    window_size: int = 15,
) -> str:
    """Collect the focused pages sent to the LLM for TOC analysis.

    Args:
        pages: Full list of cleaned page documents.
        mode: Which focused page set to include for TOC/work discovery.
        window_size: Number of pages to include for first/last page strategies.

    Returns:
        Concatenated text with ``--- Page N ---`` separators.
    """
    focus_title: str
    focus_indexes: List[int]
    empty_text: str

    if mode == "candidate_toc":
        focus_title = "Candidate TOC pages"
        focus_indexes = find_toc_page_indexes(pages)
        empty_text = "(none detected)"
    elif mode == "last_pages":
        focus_title = f"Last {window_size} pages"
        focus_indexes = _window_indexes(
            pages,
            from_start=False,
            window_size=window_size,
        )
        empty_text = "(document is empty)"
    else:
        focus_title = f"First {window_size} pages"
        focus_indexes = _window_indexes(
            pages,
            from_start=True,
            window_size=window_size,
        )
        empty_text = "(document is empty)"

    return _analysis_section(focus_title, pages, focus_indexes, empty_text)


# ─── LLM analysis ─────────────────────────────────────────────────────────────

_METADATA_PROMPT_TEMPLATE = """\
You are analyzing the first pages and last pages of a scanned book.
This is a book about a Kazakh and Alash intellectual figure from the early 20th
century.
The book may contain poems, articles, monologues, textbooks, legal texts,
or texts from any field.

{known_authors_hint}

Extract structured information as JSON.
Respond with ONLY valid JSON, no markdown, no explanation.

{{
  "summary": "Short description of the main author and the book contents",
  "metadata": {{
    "book_title": "Title of the book as it appears",
    "main_author": "Full name of the main subject of the book",
    "publisher": "Publisher name if visible, else empty string",
    "year": "Publication year if visible, else empty string"
  }}
}}

Rules:
- main_author is the person this book is about, NOT the editor or foreword writer
- If the author appears in the known authors list below, use the exact same spelling
- Write the summary in the same language as the book content
  (Kazakh if the book is in Kazakh, Russian if Russian)

You are given: the first pages of the book and the last pages of the book.

Text:
{metadata_input}
"""

_TOC_PROMPT_TEMPLATE = """\
You are analyzing a focused page section from a scanned book to determine
whether it contains a real table of contents.
This is a book about a Kazakh and Alash intellectual figure from the early 20th
century.
The book may contain poems, articles, monologues, textbooks, legal texts,
or texts from any field.

Extract structured information as JSON.
Respond with ONLY valid JSON, no markdown, no explanation.

{{
  "toc": {{
    "title": "Visible heading of the actual table of contents page",
    "start_page": <first actual TOC page number>,
    "end_page": <last actual TOC page number>
  }},
  "toc_find_failed": false,
  "toc_failure_reason": "",
  "works": [
    {{
      "title": "Title of the work exactly as it appears in the table of contents",
      "start_page": <page number exactly as shown in the --- Page N --- markers>,
      "end_page": <page number exactly as shown in the --- Page N --- markers>
    }}
  ]
}}

Rules:
- Page numbers come ONLY from the table of contents, not from your general knowledge
- Page numbers correspond to the --- Page N --- markers in the text below
- The focused section may be labeled "Candidate TOC pages", "Last N pages",
  or "First N pages" depending on the search attempt
- Decide yourself whether the focused section really contains a table of contents
- Fill toc.title/start_page/end_page from the actual
  table of contents pages when they are valid
- Include every titled entry from the table of contents in works[]
- end_page for a work is start_page of the next work minus 1
  (or last page of the book for the final work)
- If the focused section does not actually look like a table of contents,
  or no valid TOC is visible, set toc to null, set toc_find_failed to true,
  explain why in toc_failure_reason, and return works: []
- If TOC looks valid, set toc_find_failed to false and toc_failure_reason to ""

Text:
{analysis_input}
"""


def _invoke_json_llm(
    prompt: str,
) -> dict:
    """Invoke the configured LLM and parse a JSON object response."""

    llm = LLMFactory.create(temperature=0, streaming=False)

    try:
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        raise BookIndexingError(f"LLM call failed: {exc}") from exc

    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BookIndexingError(
            f"LLM returned invalid JSON: {exc}\nResponse was:\n{raw[:500]}"
        ) from exc


def extract_book_metadata(
    metadata_input: str,
    known_authors: Optional[List[str]] = None,
) -> BookMetadataResult:
    """Use the LLM to extract summary and top-level metadata.

    Args:
        metadata_input: Text from build_metadata_input().
        known_authors: List of author names already in the DB, for spelling consistency.

    Returns:
        Metadata summary and book-level fields.

    Raises:
        BookIndexingError: If the LLM response cannot be parsed.
    """
    if known_authors:
        hint = (
            "Known authors already in the database "
            "(use exact spelling if the author matches):\n"
            + "\n".join(f"- {a}" for a in known_authors)
            + "\n"
        )
    else:
        hint = ""

    prompt = _METADATA_PROMPT_TEMPLATE.format(
        known_authors_hint=hint,
        metadata_input=metadata_input,
    )

    data = _invoke_json_llm(prompt)

    try:
        return BookMetadataResult.model_validate(data)
    except Exception as exc:
        raise BookIndexingError(
            f"LLM JSON did not match expected schema: {exc}"
        ) from exc


def index_book(
    analysis_input: str,
) -> TOCSearchResult:
    """Use the LLM to locate a table of contents and extract work ranges.

    Args:
        analysis_input: Text from build_analysis_input().

    Returns:
        TOC search result with TOC status and works list.

    Raises:
        BookIndexingError: If the LLM response cannot be parsed.
    """
    prompt = _TOC_PROMPT_TEMPLATE.format(analysis_input=analysis_input)
    data = _invoke_json_llm(prompt)

    try:
        return TOCSearchResult.model_validate(data)
    except Exception as exc:
        raise BookIndexingError(
            f"LLM JSON did not match expected schema: {exc}"
        ) from exc


# ─── Work extraction ──────────────────────────────────────────────────────────


def extract_works(
    pages: List[LangchainDocument],
    index: BookIndex,
    file_name: str,
) -> List[LangchainDocument]:
    """Extract each work's text from the full page list.

    For each WorkEntry in the index, joins OCR pages whose actual page numbers
    fall inside ``[start_page - 1, end_page + 1]`` for a small context margin.

    Args:
        pages: Full list of cleaned page documents.
        index: BookIndex from index_book().
        file_name: Source file name (stored in chunk metadata).

    Returns:
        List of LangchainDocument objects, one per work, with rich metadata.
    """
    docs: List[LangchainDocument] = []

    for work in index.works:
        extracted_pages = _select_pages_in_range(
            pages,
            max(1, work.start_page - 1),
            work.end_page + 1,
        )
        text = "\n\n".join(
            page.page_content for page in extracted_pages if page.page_content.strip()
        )

        if not extracted_pages:
            logger.warning(
                "Work '%s' pages %s-%s matched no OCR pages, skipping",
                work.title,
                work.start_page,
                work.end_page,
            )
            continue

        if len(text.strip()) < 50:
            logger.warning(
                "Work '%s' pages %s-%s produced < 50 chars, skipping",
                work.title,
                work.start_page,
                work.end_page,
            )
            continue

        docs.append(
            LangchainDocument(
                page_content=text,
                metadata={
                    "source": file_name,
                    "work_title": work.title,
                    "main_author": index.metadata.main_author,
                    "book_title": index.metadata.book_title,
                    "start_page": work.start_page,
                    "end_page": work.end_page,
                },
            )
        )

    return docs

def extract_pages(
    pages: List[LangchainDocument],
    book_index: BookIndex,
    file_name: str,
) -> List[LangchainDocument]:
    """Extract clean raw pages as standalone retrieval records.

    Args:
        pages: Full list of cleaned page documents.
        book_index: BookIndex from index_book().
        file_name: Source file name (stored in chunk metadata).

    Returns:
        List of LangchainDocument objects, one per cleaned page.
    """
    docs: List[LangchainDocument] = []

    for page_index, page in enumerate(pages, start=1):
        page_number = _page_number(page, page_index)
        if not page.page_content.strip():
            continue

        docs.append(
            LangchainDocument(
                page_content=page.page_content,
                metadata={
                    "source": file_name,
                    "page_number": page_number,
                    "main_author": book_index.metadata.main_author,
                    "book_title": book_index.metadata.book_title,
                },
            )
        )

    return docs
