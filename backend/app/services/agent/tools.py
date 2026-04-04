"""Deterministic non-vector retrieval tools for the Alash agent.

Tools combine:
- metadata/title/author search over indexed documents
- structured browsing (authors -> books -> works)
- raw page search and page-window inspection for verification
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List

from langchain_core.tools import tool
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.minio import get_minio_client
from app.models.knowledge import Document, DocumentChunk
from app.services.book_indexer import clean_page_text

logger = logging.getLogger(__name__)

_CHARS_PER_PAGE = 15_000
_MAX_SEARCH_LIMIT = 10
_NORMALIZE_RE = re.compile(r"[^\w\u0400-\u04FF]+", re.UNICODE)
_NAME_SUFFIXES = (
    "ұлы",
    "улы",
    "қызы",
    "кызы",
    "ов",
    "ев",
    "ова",
    "ева",
    "ин",
    "ина",
)


@dataclass
class WorkInfo:
    """A single work inside a book."""

    work_num: int
    title: str
    document_id: int
    start_page: int
    end_page: int


@dataclass
class BookInfo:
    """A book (= one uploaded Document)."""

    document_id: int
    title: str
    author: str
    summary: str
    publisher: str
    year: str
    works: List[WorkInfo] = field(default_factory=list)


@dataclass
class AuthorInfo:
    """An author derived from documents."""

    author_num: int
    name: str
    book_ids: List[int] = field(default_factory=list)


@dataclass
class PageRecord:
    """A clean raw page used for page-level verification."""

    page_number: int
    content: str


@dataclass
class KBIndex:
    """In-memory index of authors/books/works across selected KBs."""

    authors: Dict[int, AuthorInfo] = field(default_factory=dict)
    books: Dict[int, BookInfo] = field(default_factory=dict)
    works: Dict[int, WorkInfo] = field(default_factory=dict)
    author_by_name: Dict[str, int] = field(default_factory=dict)


def _normalize_text(text: str) -> str:
    """Normalize text for lightweight fuzzy keyword matching."""
    cleaned = _NORMALIZE_RE.sub(" ", (text or "").lower())
    return " ".join(cleaned.split())


def _tokenize(text: str) -> List[str]:
    """Split normalized text into searchable tokens."""
    return [token for token in _normalize_text(text).split() if len(token) > 1]


def _token_variants(token: str) -> set[str]:
    """Build lightweight fuzzy variants for personal names and title tokens."""
    variants = {token}

    for suffix in _NAME_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            variants.add(token[: -len(suffix)])

    return {variant for variant in variants if len(variant) > 1}


def _is_short_author_like_query(query: str) -> bool:
    """Detect short queries that are likely intended as a person name."""
    tokens = _tokenize(query)
    return 0 < len(tokens) <= 2


def _score_match(
    query: str,
    primary_fields: List[str],
    secondary_fields: List[str] | None = None,
) -> int:
    """Score a query against candidate fields using normalized substring overlap."""
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return 0

    query_tokens = _tokenize(query)
    score = 0

    def _score_field(field: str, *, primary: bool) -> int:
        normalized_field = _normalize_text(field)
        if not normalized_field:
            return 0

        field_score = 0
        field_tokens = set(normalized_field.split())
        field_variants = {
            variant for token in field_tokens for variant in _token_variants(token)
        }
        multiplier = 2 if primary else 1

        if normalized_query == normalized_field:
            field_score += 30 * multiplier
        elif normalized_query in normalized_field:
            field_score += 18 * multiplier

        for token in query_tokens:
            token_variants = _token_variants(token)
            if token in field_tokens:
                field_score += 6 * multiplier
            elif token_variants & field_variants:
                field_score += 5 * multiplier
            elif token in normalized_field:
                field_score += 2 * multiplier

        return field_score

    for candidate in primary_fields:
        score += _score_field(candidate, primary=True)

    for candidate in secondary_fields or []:
        score += _score_field(candidate, primary=False)

    return score


def build_kb_index(
    db: Session,
    knowledge_base_ids: List[int],
) -> KBIndex:
    """Query the DB and build a numbered index of authors, books, and works."""
    index = KBIndex()

    documents = (
        db.query(Document)
        .filter(Document.knowledge_base_id.in_(knowledge_base_ids))
        .order_by(Document.id)
        .all()
    )

    work_counter = 0

    for doc in documents:
        analysis = doc.analysis or {}
        metadata = analysis.get("metadata", {})
        author_name = metadata.get("main_author", "").strip() or "Белгісіз автор"
        book_title = metadata.get("book_title", "") or doc.file_name
        summary = analysis.get("summary", "")
        publisher = metadata.get("publisher", "")
        year = metadata.get("year", "")

        if author_name not in index.author_by_name:
            author_num = len(index.authors) + 1
            index.authors[author_num] = AuthorInfo(
                author_num=author_num, name=author_name
            )
            index.author_by_name[author_name] = author_num

        author_num = index.author_by_name[author_name]
        index.authors[author_num].book_ids.append(doc.id)

        book = BookInfo(
            document_id=doc.id,
            title=book_title,
            author=author_name,
            summary=summary,
            publisher=publisher,
            year=year,
        )

        for work_meta in analysis.get("works", []):
            title = (work_meta.get("title") or "").strip()
            if not title:
                continue

            work_counter += 1
            work = WorkInfo(
                work_num=work_counter,
                title=title,
                document_id=doc.id,
                start_page=int(work_meta.get("start_page") or 0),
                end_page=int(work_meta.get("end_page") or 0),
            )
            book.works.append(work)
            index.works[work_counter] = work

        index.books[doc.id] = book

    logger.info(
        "KBIndex built: %d authors, %d books, %d works",
        len(index.authors),
        len(index.books),
        len(index.works),
    )
    return index


def create_tools(db: Session, knowledge_base_ids: List[int]) -> list:
    """Create agent tools with a pre-built KB index bound via closure."""
    index = build_kb_index(db, knowledge_base_ids)
    page_cache: Dict[int, List[PageRecord]] = {}

    def _clamp_limit(limit: int) -> int:
        return max(1, min(limit, _MAX_SEARCH_LIMIT))

    def _load_raw_pages(document_id: int) -> List[PageRecord]:
        """Load raw page records from DB chunks or from the source OCR JSON."""
        if document_id in page_cache:
            return page_cache[document_id]

        page_rows = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_type == "page",
            )
            .order_by(DocumentChunk.page_number.asc(), DocumentChunk.id.asc())
            .all()
        )

        if page_rows:
            records = [
                PageRecord(
                    page_number=int(
                        row.page_number
                        or (row.chunk_metadata or {}).get("page_number")
                        or 0
                    ),
                    content=(
                        (row.chunk_metadata or {}).get("page_content") or ""
                    ).strip(),
                )
                for row in page_rows
                if ((row.chunk_metadata or {}).get("page_content") or "").strip()
            ]
            page_cache[document_id] = records
            return records

        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            page_cache[document_id] = []
            return []

        response = None
        try:
            minio_client = get_minio_client()
            response = minio_client.get_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=document.file_path,
            )
            raw_data = json.loads(response.read().decode("utf-8"))
            if not isinstance(raw_data, list):
                page_cache[document_id] = []
                return []

            records = []
            for idx, item in enumerate(
                sorted(raw_data, key=lambda row: int(row.get("page", 0)))
            ):
                page_number = int(item.get("page", idx + 1))
                content = clean_page_text(item.get("text", ""))
                if content.strip():
                    records.append(PageRecord(page_number=page_number, content=content))

            page_cache[document_id] = records
            return records
        except Exception as exc:
            logger.warning(
                "Failed to load raw pages for document %s: %s", document_id, exc
            )
            page_cache[document_id] = []
            return []
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def _format_page_excerpt(content: str, query: str, max_len: int = 240) -> str:
        """Create a compact page excerpt around the first match if possible."""
        normalized_query = _normalize_text(query)
        normalized_content = _normalize_text(content)
        if normalized_query and normalized_query in normalized_content:
            content_lower = content.lower()
            query_lower = query.lower()
            start = max(0, content_lower.find(query_lower) - 80)
            excerpt = content[start : start + max_len]
        else:
            excerpt = content[:max_len]
        excerpt = " ".join(excerpt.split())
        return excerpt + ("..." if len(content) > len(excerpt) else "")

    def _find_work_chunk(work: WorkInfo) -> DocumentChunk | None:
        """Resolve the stored work chunk for a logical work entry."""
        filters = [
            DocumentChunk.document_id == work.document_id,
            or_(DocumentChunk.chunk_type == "work", DocumentChunk.chunk_type.is_(None)),
            DocumentChunk.chunk_label == work.title,
        ]

        if work.start_page:
            filters.append(
                or_(
                    DocumentChunk.start_page == work.start_page,
                    DocumentChunk.start_page.is_(None),
                )
            )
        if work.end_page:
            filters.append(
                or_(
                    DocumentChunk.end_page == work.end_page,
                    DocumentChunk.end_page.is_(None),
                )
            )

        chunk = (
            db.query(DocumentChunk)
            .filter(*filters)
            .order_by(DocumentChunk.id.asc())
            .first()
        )
        if chunk is not None:
            return chunk

        return (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == work.document_id,
                or_(
                    DocumentChunk.chunk_type == "work",
                    DocumentChunk.chunk_type.is_(None),
                ),
                DocumentChunk.chunk_metadata["work_title"].as_string() == work.title,
            )
            .order_by(DocumentChunk.id.asc())
            .first()
        )

    def _works_for_page(book: BookInfo, page_number: int) -> List[str]:
        """Find work titles whose page ranges cover a raw page."""
        matches = []
        for work in book.works:
            if work.start_page and work.end_page:
                if work.start_page <= page_number <= work.end_page:
                    matches.append(work.title)
        return matches

    @tool
    async def search_catalog(query: str, limit: int = 8) -> str:
        """Search authors, books, and work titles using normalized keyword matching.

        This is the primary non-vector retrieval tool for ambiguous questions,
        partial titles, misspellings, author names, metadata lookups, and
        cases where exact matching is unlikely to work.

        Args:
            query: Natural-language search query or partial title/name.
            limit: Maximum number of ranked matches to return.
        """
        limit = _clamp_limit(limit)
        author_like_query = _is_short_author_like_query(query)
        results: List[tuple[int, int, str]] = []

        for author in index.authors.values():
            score = _score_match(query, [author.name])
            if score > 0:
                if author_like_query:
                    score += 8
                results.append(
                    (
                        score,
                        0,
                        f"Автор сәйкестігі: {author.name} "
                        f"[internal: author_number={author.author_num}]",
                    )
                )

        for book in index.books.values():
            score = _score_match(
                query,
                [book.title],
                [book.author, book.summary, book.publisher, book.year],
            )
            if score > 0:
                year_str = f", {book.year}" if book.year else ""
                results.append(
                    (
                        score,
                        1,
                        f'Кітап сәйкестігі: "{book.title}" '
                        f"(автор: {book.author}{year_str}) "
                        f"[internal: book_number={book.document_id}]",
                    )
                )

        for work in index.works.values():
            book = index.books[work.document_id]
            page_range = ""
            if work.start_page and work.end_page:
                page_range = f", бб. {work.start_page}-{work.end_page}"
            score = _score_match(
                query,
                [work.title],
                [book.title, book.author, book.summary],
            )
            if score > 0:
                results.append(
                    (
                        score,
                        2,
                        f'Шығарма сәйкестігі: "{work.title}" | '
                        f'Кітап: "{book.title}" | '
                        f"Автор: {book.author}{page_range} "
                        f"[internal: work_number={work.work_num}, "
                        f"book_number={book.document_id}]",
                    )
                )

        if not results:
            return f'Сұраныс бойынша сәйкестік табылмады: "{query}".'

        lines = [f'Сұраныс: "{query}"', "", "Үздік сәйкестіктер:"]
        for rank, (_, _, line) in enumerate(
            sorted(results, key=lambda item: (-item[0], item[1], item[2]))[:limit],
            start=1,
        ):
            lines.append(f"{rank}. {line}")

        return "\n".join(lines)

    @tool
    async def get_authors_and_books() -> str:
        """Get the full list of authors and their books in the knowledge base."""
        if not index.authors:
            return "Білім қорында құжаттар жоқ."

        lines: List[str] = []
        for author in index.authors.values():
            lines.append(f"Автор #{author.author_num}: {author.name}")
            for book_id in author.book_ids:
                book = index.books[book_id]
                work_count = len(book.works)
                year_str = f", {book.year}" if book.year else ""
                lines.append(
                    f'  Кітап #{book.document_id}: "{book.title}" '
                    f"({work_count} шығарма{year_str})"
                )
            lines.append("")

        return "\n".join(lines).strip()

    @tool
    async def get_book_details(book_number: int) -> str:
        """Get detailed information about a specific book and its works."""
        book = index.books.get(book_number)
        if not book:
            return f"Кітап #{book_number} табылмады."

        lines = [
            f'Кітап #{book.document_id}: "{book.title}"',
            f"Автор: {book.author}",
        ]
        if book.publisher:
            lines.append(f"Баспа: {book.publisher}")
        if book.year:
            lines.append(f"Жыл: {book.year}")
        lines.append(f"\nАннотация: {book.summary}")
        lines.append(f"\nШығармалар ({len(book.works)}):")

        for work in book.works:
            page_range = ""
            if work.start_page and work.end_page:
                page_range = f" (бб. {work.start_page}-{work.end_page})"
            lines.append(f"  Шығарма #{work.work_num}: {work.title}{page_range}")

        return "\n".join(lines)

    @tool
    async def get_author_works(author_number: int) -> str:
        """Get all books and works by a specific author."""
        author = index.authors.get(author_number)
        if not author:
            return f"Автор #{author_number} табылмады."

        lines = [f"Автор #{author.author_num}: {author.name}\n"]

        for book_id in author.book_ids:
            book = index.books[book_id]
            lines.append(f'--- Кітап #{book.document_id}: "{book.title}" ---')
            if book.summary:
                lines.append(f"Аннотация: {book.summary}")
            lines.append(f"Шығармалар ({len(book.works)}):")
            for work in book.works:
                page_range = ""
                if work.start_page and work.end_page:
                    page_range = f" (бб. {work.start_page}-{work.end_page})"
                lines.append(f"  Шығарма #{work.work_num}: {work.title}{page_range}")
            lines.append("")

        return "\n".join(lines).strip()

    @tool
    async def get_work_content(
        work_number: int,
        page_offset: int = 0,
    ) -> str:
        """Read the stored work-level text content of a specific work.

        Use this for summaries and broad reading, but remember this text is
        built from TOC-derived work boundaries with a small page padding. That
        means adjacent pages can introduce irrelevant or neighboring-work
        context. Verify quotes, dates, disputed details, page-specific claims,
        and unclear attribution with raw pages when needed.

        Args:
            work_number: The work number from search or browsing tools.
            page_offset: Segment index (0 = first segment, 1 = second, etc.).
        """
        work = index.works.get(work_number)
        if not work:
            return f"Шығарма #{work_number} табылмады."

        chunk = _find_work_chunk(work)
        if not chunk:
            return f"Шығарма #{work_number} мазмұны табылмады."

        content = (chunk.chunk_metadata or {}).get("page_content", "")
        if not content:
            return f"Шығарма #{work_number} мазмұны бос."

        book = index.books.get(work.document_id)
        header = (
            f'Шығарма #{work.work_num}: "{work.title}"\n'
            f'Кітап: "{book.title}" — {book.author}\n'
        )
        if work.start_page and work.end_page:
            header += f"Беттер: {work.start_page}-{work.end_page}\n"

        total_segments = max(1, -(-len(content) // _CHARS_PER_PAGE))
        start = page_offset * _CHARS_PER_PAGE
        end = start + _CHARS_PER_PAGE

        if start >= len(content):
            return (
                f"Шығарма #{work_number}: бұл сегмент жоқ "
                f"(бар болғаны {total_segments} сегмент)."
            )

        segment = content[start:end]
        segment_info = ""
        if total_segments > 1:
            segment_info = f"\n[Сегмент {page_offset + 1}/{total_segments}. "
            if end < len(content):
                segment_info += "Жалғасы бар, келесі сегментті де оқуға болады.]"
            else:
                segment_info += "Бұл соңғы сегмент.]"

        return f"{header}\n{segment}{segment_info}"

    @tool
    async def search_pages(
        query: str,
        book_number: int = 0,
        work_number: int = 0,
        page_from: int = 0,
        page_to: int = 0,
        limit: int = 5,
    ) -> str:
        """Search raw OCR-cleaned pages with optional book/work/page filters.

        Use this to verify quotes, names, dates, terms, and claims that should
        be checked against the original pages instead of only TOC-derived work
        boundaries.

        Args:
            query: Text, phrase, or keywords to search for.
            book_number: Optional book/document number filter.
            work_number: Optional work filter; limits pages to that work's range.
            page_from: Optional lower page bound.
            page_to: Optional upper page bound.
            limit: Maximum number of page hits to return.
        """
        limit = _clamp_limit(limit)

        work: WorkInfo | None = None
        if work_number:
            work = index.works.get(work_number)
            if work is None:
                return f"Шығарма #{work_number} табылмады."
            book_number = work.document_id

        if book_number:
            book = index.books.get(book_number)
            if book is None:
                return f"Кітап #{book_number} табылмады."
            books_to_search = [book]
        else:
            books_to_search = list(index.books.values())

        effective_page_from = page_from
        effective_page_to = page_to
        if work is not None:
            if work.start_page:
                effective_page_from = max(effective_page_from, work.start_page)
            if work.end_page:
                effective_page_to = (
                    min(effective_page_to, work.end_page)
                    if effective_page_to
                    else work.end_page
                )

        results: List[tuple[int, str]] = []

        for book in books_to_search:
            for page in _load_raw_pages(book.document_id):
                if effective_page_from and page.page_number < effective_page_from:
                    continue
                if effective_page_to and page.page_number > effective_page_to:
                    continue

                score = _score_match(
                    query,
                    [page.content],
                    [book.title, book.author, book.summary],
                )
                if score <= 0:
                    continue

                works_for_page = _works_for_page(book, page.page_number)
                works_str = (
                    f" | Шығармалар: {', '.join(works_for_page[:2])}"
                    if works_for_page
                    else ""
                )
                excerpt = _format_page_excerpt(page.content, query)
                results.append(
                    (
                        score,
                        f'Кітап #{book.document_id}: "{book.title}" | '
                        f"Бет {page.page_number}{works_str}\n{excerpt}",
                    )
                )

        if not results:
            return f'Сұраныс бойынша беттерден сәйкестік табылмады: "{query}".'

        lines = [f'Бет іздеуі: "{query}"', "", "Үздік бет сәйкестіктері:"]
        for rank, (_, line) in enumerate(
            sorted(results, key=lambda item: (-item[0], item[1]))[:limit],
            start=1,
        ):
            lines.append(f"{rank}. {line}")

        return "\n".join(lines)

    @tool
    async def get_page_window(
        book_number: int,
        page_number: int,
        window: int = 0,
    ) -> str:
        """Read one raw page or a small page window around it.

        Args:
            book_number: The book/document number.
            page_number: Raw page number to inspect.
            window: Number of pages before/after to include.
        """
        book = index.books.get(book_number)
        if book is None:
            return f"Кітап #{book_number} табылмады."

        pages = _load_raw_pages(book_number)
        if not pages:
            return f'Кітап #{book_number}: "{book.title}" үшін шикі беттер табылмады.'

        window = max(0, min(window, 3))
        start_page = page_number - window
        end_page = page_number + window

        selected = [
            page for page in pages if start_page <= page.page_number <= end_page
        ]
        if not selected:
            return f"Кітап #{book_number}: бет {page_number} табылмады."

        lines = [f'Кітап #{book.document_id}: "{book.title}" — {book.author}']
        for page in selected:
            works_for_page = _works_for_page(book, page.page_number)
            works_str = (
                f" | Шығармалар: {', '.join(works_for_page[:2])}"
                if works_for_page
                else ""
            )
            lines.append(f"\n--- Бет {page.page_number}{works_str} ---")
            lines.append(page.content)

        return "\n".join(lines)

    return [
        search_catalog,
        get_authors_and_books,
        get_book_details,
        get_author_works,
        get_work_content,
        search_pages,
        get_page_window,
    ]
