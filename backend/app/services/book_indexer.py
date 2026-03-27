"""
Book indexer service.

Loads JSON OCR page arrays, extracts key pages for LLM analysis,
uses the LLM to identify every work listed in the table of contents,
then extracts each work's text as a standalone document for the vector store.
"""
import json
import logging
import re
from typing import List, Optional

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


class BookIndexingError(Exception):
    """Raised when the LLM fails to produce a usable book index."""


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

    pages = sorted(data, key=lambda x: int(x.get("page", 0)))
    return [
        LangchainDocument(
            page_content=clean_page_text(item.get("text", "")),
            metadata={"page": int(item.get("page", idx))},
        )
        for idx, item in enumerate(pages)
    ]


# ─── Analysis input construction ─────────────────────────────────────────────


def build_analysis_input(pages: List[LangchainDocument]) -> str:
    """Collect the pages sent to the LLM for analysis.

    Gathers:
    - First 5 pages
    - Last 3 pages
    - TOC pages (pages containing any TOC keyword) plus the next 3 pages each

    Args:
        pages: Full list of cleaned page documents.

    Returns:
        Concatenated text with ``--- Page N ---`` separators.
    """
    n = len(pages)
    selected: dict[int, LangchainDocument] = {}

    # First 3
    for i in range(min(3, n)):
        selected[i] = pages[i]

    # Last 2
    for i in range(max(0, n - 2), n):
        selected[i] = pages[i]

    # TOC pages + next 3 (dict keyed by index deduplicates overlapping pages)
    for i, page in enumerate(pages):
        text_lower = page.page_content.lower()
        if any(pat in text_lower for pat in TOC_PATTERNS):
            for j in range(i, min(i + 4, n)):
                selected[j] = pages[j]

    parts: List[str] = []
    for idx in sorted(selected):
        page_num = selected[idx].metadata.get("page", idx)
        parts.append(f"--- Page {page_num} ---\n{selected[idx].page_content}")

    return "\n\n".join(parts)


# ─── LLM analysis ─────────────────────────────────────────────────────────────

_PROMPT_TEMPLATE = """\
You are analyzing the first pages, last pages, and table of contents of a scanned book.
This is likely a book about a Kazakh intellectual figure from the early 20th century (Alash era).
The book may contain poems, articles, monologues, textbooks, legal texts, or texts from any field.

{known_authors_hint}

Extract structured information as JSON. Respond with ONLY valid JSON, no markdown, no explanation.

{{
  "summary": "Description of the book's main author and a brief summary of its contents based on the table of contents",
  "metadata": {{
    "book_title": "Title of the book as it appears",
    "main_author": "Full name of the main subject of the book (the Alash figure this book is about)",
    "publisher": "Publisher name if visible, else empty string",
    "year": "Publication year if visible, else empty string"
  }},
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
- main_author is the person this book is about, NOT the editor or foreword writer
- If the author appears in the known authors list below, use the exact same spelling
- Include every titled entry from the table of contents in works[]
- end_page for a work is start_page of the next work minus 1 (or last page of the book for the final work)
- If no table of contents is visible, return works: []
- Write the summary in the same language as the book content (Kazakh if the book is in Kazakh, Russian if Russian)

You are given: the first pages of the book, the last pages, and the table of contents pages.

Text:
{analysis_input}
"""


def index_book(
    analysis_input: str,
    known_authors: Optional[List[str]] = None,
) -> BookIndex:
    """Use the LLM to extract the book's structure from key pages.

    Args:
        analysis_input: Text from build_analysis_input().
        known_authors: List of author names already in the DB, for spelling consistency.

    Returns:
        BookIndex with summary, metadata, and works list.

    Raises:
        BookIndexingError: If the LLM response cannot be parsed.
    """
    if known_authors:
        hint = (
            "Known authors already in the database (use exact spelling if the author matches):\n"
            + "\n".join(f"- {a}" for a in known_authors)
            + "\n"
        )
    else:
        hint = ""

    prompt = _PROMPT_TEMPLATE.format(
        known_authors_hint=hint,
        analysis_input=analysis_input,
    )

    llm = LLMFactory.create(temperature=0, streaming=False)

    try:
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        raise BookIndexingError(f"LLM call failed: {exc}") from exc

    # Strip accidental markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BookIndexingError(
            f"LLM returned invalid JSON: {exc}\nResponse was:\n{raw[:500]}"
        ) from exc

    try:
        return BookIndex.model_validate(data)
    except Exception as exc:
        raise BookIndexingError(f"LLM JSON did not match expected schema: {exc}") from exc


# ─── Work extraction ──────────────────────────────────────────────────────────


def extract_works(
    pages: List[LangchainDocument],
    index: BookIndex,
    file_name: str,
) -> List[LangchainDocument]:
    """Extract each work's text from the full page list.

    For each WorkEntry in the index, joins pages in the range
    [start_page - 1, end_page + 1] (with ±1 page margin for context).

    Args:
        pages: Full list of cleaned page documents.
        index: BookIndex from index_book().
        file_name: Source file name (stored in chunk metadata).

    Returns:
        List of LangchainDocument objects, one per work, with rich metadata.
    """
    n = len(pages)
    docs: List[LangchainDocument] = []

    for work in index.works:
        # Page numbers from the LLM are 1-indexed (matching --- Page N --- markers).
        # pages list is 0-indexed: page P → index P-1.
        # Apply ±1 page padding around each work.
        #   start index = (start_page - 1) - 1 = start_page - 2
        #   end index   = (end_page   - 1) + 1 = end_page
        start = max(0, work.start_page - 2)
        end = min(n - 1, work.end_page)
        text = " ".join(p.page_content for p in pages[start : end + 1])

        if len(text.strip()) < 50:
            logger.warning(
                f"Work '{work.title}' pages {start}-{end} produced < 50 chars, skipping"
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
