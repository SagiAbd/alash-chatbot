"""Extract DOCX files into ocr.json-shaped page lists."""

import logging
from typing import List

from docx import Document as DocxDocument

logger = logging.getLogger(__name__)

_CHUNK_CHAR_LIMIT = 3000
_WORDML_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _paragraph_has_page_break(paragraph) -> bool:
    """Detect an explicit ``w:br w:type='page'`` inside a paragraph."""
    for element in paragraph._p.iter():
        if element.tag == f"{_WORDML_NS}br":
            if element.get(f"{_WORDML_NS}type") == "page":
                return True
    return False


def extract_pages_from_docx(file_path: str) -> List[dict]:
    """Read a DOCX file and split into ocr.json-style page records.

    Uses explicit page breaks when present, otherwise groups paragraphs into
    chunks of roughly ``_CHUNK_CHAR_LIMIT`` characters so that long documents
    without page breaks still produce workable retrieval units.
    """
    document = DocxDocument(file_path)
    buckets: List[List[str]] = [[]]
    current_size = 0

    for paragraph in document.paragraphs:
        text = paragraph.text or ""
        buckets[-1].append(text)
        current_size += len(text)

        if _paragraph_has_page_break(paragraph) or current_size >= _CHUNK_CHAR_LIMIT:
            buckets.append([])
            current_size = 0

    pages: List[dict] = []
    for index, lines in enumerate(buckets):
        joined = "\n".join(line for line in lines if line.strip()).strip()
        if not joined:
            continue
        pages.append({"page": len(pages) + 1, "text": joined})

    logger.info("Extracted %d pages from DOCX file", len(pages))
    return pages
