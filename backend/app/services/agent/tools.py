"""Deterministic document-retrieval tools for the Alash agent.

Tools navigate the document hierarchy (authors -> books -> works -> content)
via direct MySQL queries — no vector store involved.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.models.knowledge import Document, DocumentChunk

logger = logging.getLogger(__name__)

# ─── Characters per "page" for pagination ────────────────────────────────────
_CHARS_PER_PAGE = 15_000


# ─── Index data classes ──────────────────────────────────────────────────────


@dataclass
class WorkInfo:
    """A single work inside a book."""

    work_num: int
    title: str
    document_id: int
    chunk_id: str
    start_page: int
    end_page: int
    content_length: int


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
class KBIndex:
    """In-memory index of all authors/books/works across selected KBs."""

    authors: Dict[int, AuthorInfo] = field(default_factory=dict)
    books: Dict[int, BookInfo] = field(default_factory=dict)
    works: Dict[int, WorkInfo] = field(default_factory=dict)
    author_by_name: Dict[str, int] = field(default_factory=dict)


# ─── Index builder ───────────────────────────────────────────────────────────


def build_kb_index(
    db: Session,
    knowledge_base_ids: List[int],
) -> KBIndex:
    """Query the DB and build a numbered index of authors, books, and works.

    Args:
        db: SQLAlchemy session.
        knowledge_base_ids: IDs of the knowledge bases attached to this chat.

    Returns:
        Populated KBIndex with stable numbering for the session.
    """
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

        # Register author if new
        if author_name not in index.author_by_name:
            author_num = len(index.authors) + 1
            author = AuthorInfo(
                author_num=author_num,
                name=author_name,
            )
            index.authors[author_num] = author
            index.author_by_name[author_name] = author_num

        author_num = index.author_by_name[author_name]
        index.authors[author_num].book_ids.append(doc.id)

        # Register book
        book = BookInfo(
            document_id=doc.id,
            title=book_title,
            author=author_name,
            summary=summary,
            publisher=publisher,
            year=year,
        )

        # Build works from chunks
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.id)
            .all()
        )

        works_meta = analysis.get("works", [])
        works_page_map = {w.get("title", ""): w for w in works_meta}

        for chunk in chunks:
            cm = chunk.chunk_metadata or {}
            work_title = cm.get("work_title", f"Бөлім {len(book.works) + 1}")
            content = cm.get("page_content", "")
            page_info = works_page_map.get(work_title, {})

            work_counter += 1
            work = WorkInfo(
                work_num=work_counter,
                title=work_title,
                document_id=doc.id,
                chunk_id=chunk.id,
                start_page=page_info.get("start_page", 0),
                end_page=page_info.get("end_page", 0),
                content_length=len(content),
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


# ─── Tool factory ────────────────────────────────────────────────────────────


def create_tools(db: Session, knowledge_base_ids: List[int]) -> list:
    """Create agent tools with a pre-built KB index bound via closure.

    Args:
        db: SQLAlchemy session (kept alive for work content retrieval).
        knowledge_base_ids: Knowledge base IDs for this chat.

    Returns:
        List of LangChain tool instances.
    """
    index = build_kb_index(db, knowledge_base_ids)

    @tool
    async def get_authors_and_books() -> str:
        """Get the full list of authors and their books in the knowledge base.

        Call this first to understand what documents are available.
        Returns numbered authors and books that you can reference in other tools.
        """
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
        """Get detailed information about a specific book.

        Returns the book's summary, author, and a numbered list of all works
        (poems, articles, chapters, etc.) contained in the book.
        Use this to locate the right work inside a book.
        Do not treat this output as enough for questions about what a specific
        work is about; for that, read the work text itself.

        Args:
            book_number: The book number from get_authors_and_books results.
        """
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
        """Get all books and works by a specific author.

        Returns summaries of each book and lists of works for the given author.
        Use this when the user names an author or when you need to identify
        which work by the author is relevant before reading the text.

        Args:
            author_number: The author number from get_authors_and_books results.
        """
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
        """Read the full text content of a specific work (poem, article, etc.).

        If the work is longer than ~20 pages, only a segment is returned.
        Call again with a higher page_offset to read the next segment.
        This is the required tool for questions like:
        "не туралы", "мазмұны қандай", "негізгі ойы қандай",
        "қысқаша айтып бер", "what is it about", or requests for evidence.
        If a user asks about a named work, you should normally call this tool
        after locating that work instead of answering from book metadata alone.

        Args:
            work_number: The work number from get_book_details results.
            page_offset: Segment index (0 = first segment, 1 = second, etc.).
        """
        work = index.works.get(work_number)
        if not work:
            return f"Шығарма #{work_number} табылмады."

        chunk = (
            db.query(DocumentChunk).filter(DocumentChunk.id == work.chunk_id).first()
        )
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

    return [get_authors_and_books, get_book_details, get_author_works, get_work_content]
