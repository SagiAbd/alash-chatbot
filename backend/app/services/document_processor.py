"""
Document processor service.

Handles uploading JSON OCR files to MinIO and processing them
through the book indexer to produce work-level and page-level retrieval records.
"""

import hashlib
import json
import logging
import os
import time
import traceback
from io import BytesIO
from typing import List, Optional

from fastapi import UploadFile
from langchain_core.documents import Document as LangchainDocument
from minio.commonconfig import CopySource
from minio.error import MinioException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.minio import get_minio_client
from app.db.session import SessionLocal
from app.models.knowledge import Document, DocumentChunk, KnowledgeBase, ProcessingTask
from app.services.book_indexer import (
    AnalysisMode,
    BookIndex,
    BookIndexingError,
    build_analysis_input,
    build_metadata_input,
    clean_page_text,
    extract_book_metadata,
    extract_pages,
    extract_works,
    index_book,
    load_pages_from_json,
)
from app.services.ingestion.docx_loader import extract_pages_from_docx
from app.services.ingestion.pdf_ocr import extract_pages_from_pdf
from app.services.xlsx_processor import parse_glossary_xlsx

# Upload extensions permitted for end users uploading to their personal library.
PERSONAL_UPLOAD_EXTENSIONS: tuple[str, ...] = (".docx", ".pdf")

_CONTENT_TYPE_BY_EXT: dict[str, str] = {
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}

logger = logging.getLogger(__name__)

BOOK_ANALYSIS_STRATEGIES: tuple[tuple[AnalysisMode, str], ...] = (
    ("candidate_toc", "candidate TOC pages"),
    ("last_pages", "last 15 pages"),
    ("first_pages", "first 15 pages"),
)


# ─── Public models ────────────────────────────────────────────────────────────


class UploadResult(BaseModel):
    file_path: str
    file_name: str
    file_size: int
    content_type: str
    file_hash: str


def _allow_duplicate_file_name(file_name: str) -> bool:
    """Return True when same-name uploads should bypass name conflicts."""

    return file_name.strip().lower() == "ocr.json"


def _find_document_conflict(
    db: Session,
    kb_id: int,
    file_hash: str,
    file_name: str,
) -> Document | None:
    """Return an identical document or raise on conflicting file-name reuse."""
    existing_by_hash = (
        db.query(Document)
        .filter(
            Document.knowledge_base_id == kb_id,
            Document.file_hash == file_hash,
        )
        .first()
    )
    if existing_by_hash:
        return existing_by_hash

    if _allow_duplicate_file_name(file_name):
        return None

    existing_by_name = (
        db.query(Document)
        .filter(
            Document.knowledge_base_id == kb_id,
            Document.file_name == file_name,
        )
        .first()
    )
    if existing_by_name:
        raise BookIndexingError(
            "A different document with the same file name already exists. "
            "Rename the file before uploading."
        )

    return None


def _mark_task_completed_with_existing_document(
    db: Session,
    task_id: int,
    document_id: int,
) -> None:
    """Attach an upload task to an existing identical document."""
    task = db.query(ProcessingTask).get(task_id)
    if not task:
        return

    task.status = "completed"
    task.document_id = document_id
    upload = task.document_upload
    if upload:
        upload.status = "completed"
        upload.error_message = None
    db.commit()


def _mark_task_failed(db: Session, task_id: int, error_message: str) -> None:
    """Persist a failed processing status after rollback/cleanup."""
    task = db.query(ProcessingTask).get(task_id)
    if not task:
        return

    task.status = "failed"
    task.error_message = error_message
    upload = task.document_upload
    if upload:
        upload.status = "failed"
        upload.error_message = error_message
    db.commit()


def _cleanup_failed_processing(
    db: Session,
    *,
    document_id: int | None,
    temp_path: str,
    permanent_path: str | None,
) -> None:
    """Remove partial DB rows and uploaded objects after a failed processing run."""
    if document_id is not None:
        try:
            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).delete()
            db.query(Document).filter(Document.id == document_id).delete()
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Failed to clean up partial document %s after processing error: %s",
                document_id,
                exc,
            )

    minio_client = get_minio_client()
    for object_name in {temp_path, permanent_path}:
        if not object_name:
            continue
        try:
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, object_name)
        except Exception:
            logger.warning("Failed to clean up MinIO object %s", object_name)


def _load_pages_from_records(records: List[dict]) -> List[LangchainDocument]:
    """Convert OCR-style page dicts into cleaned LangChain page documents."""
    def _page_number(record: dict, fallback: int) -> int:
        try:
            return int(record.get("page", fallback))
        except (TypeError, ValueError):
            return fallback

    pages = sorted(
        records,
        key=lambda item: _page_number(item, 0),
    )
    documents: List[LangchainDocument] = []
    for index, item in enumerate(pages):
        text = clean_page_text(str(item.get("text", "")))
        if not text:
            continue
        page_number = _page_number(item, index + 1)
        documents.append(
            LangchainDocument(
                page_content=text,
                metadata={"page": page_number},
            )
        )
    return documents


def _collect_known_authors(db: Session, kb_id: int, task_id: int) -> List[str]:
    """Return existing author spellings from this knowledge base."""
    known_authors: List[str] = []
    try:
        rows = (
            db.query(Document.analysis)
            .filter(Document.knowledge_base_id == kb_id, Document.analysis.isnot(None))
            .all()
        )
        seen: set[str] = set()
        for (analysis,) in rows:
            if isinstance(analysis, dict):
                author = (analysis.get("metadata") or {}).get("main_author", "")
                if author and author not in seen:
                    known_authors.append(author)
                    seen.add(author)
    except Exception as exc:
        logger.warning("Task %d: Could not fetch known authors: %s", task_id, exc)
    return known_authors


def _analyze_book_pages(
    db: Session,
    kb_id: int,
    task_id: int,
    file_name: str,
    pages: List[LangchainDocument],
    display_suffix: str,
) -> tuple[dict, List[LangchainDocument], List[LangchainDocument], str]:
    """Run the shared LLM indexing flow over cleaned OCR-style pages."""
    logger.info("Task %d: Loaded %d pages", task_id, len(pages))

    known_authors = _collect_known_authors(db, kb_id, task_id)
    logger.info("Task %d: Running LLM metadata analysis", task_id)
    metadata_input = build_metadata_input(pages)
    t0 = time.monotonic()
    metadata_result = extract_book_metadata(
        metadata_input,
        known_authors=known_authors or None,
    )
    logger.info(
        "Task %d: Metadata analysis complete in %.1fs — author: %s",
        task_id,
        time.monotonic() - t0,
        metadata_result.metadata.main_author,
    )

    toc_result = None
    final_reason = (
        "LLM could not verify a table of contents from candidate TOC pages, "
        "the last 15 pages, or the first 15 pages."
    )

    for mode, label in BOOK_ANALYSIS_STRATEGIES:
        logger.info("Task %d: Running LLM TOC analysis using %s", task_id, label)
        analysis_input = build_analysis_input(pages, mode=mode)
        t0 = time.monotonic()
        candidate_toc = index_book(analysis_input)
        logger.info(
            "Task %d: TOC analysis complete in %.1fs using %s — %d works found",
            task_id,
            time.monotonic() - t0,
            label,
            len(candidate_toc.works),
        )

        if not candidate_toc.toc_find_failed and candidate_toc.toc is not None:
            toc_result = candidate_toc
            break

        reason = candidate_toc.toc_failure_reason.strip()
        if reason:
            final_reason = reason
        logger.info(
            "Task %d: No TOC confirmed using %s%s",
            task_id,
            label,
            f": {reason}" if reason else "",
        )

    if toc_result is None:
        raise BookIndexingError(f"TOC find failed: {final_reason}")

    book_index = BookIndex(
        summary=metadata_result.summary,
        metadata=metadata_result.metadata,
        works=toc_result.works,
        toc=toc_result.toc,
        toc_find_failed=toc_result.toc_find_failed,
        toc_failure_reason=toc_result.toc_failure_reason,
    )

    if not book_index.works:
        raise BookIndexingError(
            "LLM found no works in the table of contents. "
            "Ensure the document contains a readable мазмұны/содержание page."
        )

    work_docs = extract_works(pages, book_index, file_name)
    if not work_docs:
        raise BookIndexingError(
            "All works produced empty text after extraction. "
            "Check that page numbers in the table of contents are correct."
        )
    page_docs = extract_pages(pages, book_index, file_name)
    logger.info("Task %d: Extracted %d work segments", task_id, len(work_docs))

    main_author = book_index.metadata.main_author.strip()
    book_title = book_index.metadata.book_title.strip()
    if main_author and book_title:
        final_file_name = f"{main_author} - {book_title}{display_suffix}"
    else:
        final_file_name = file_name

    return book_index.model_dump(), work_docs, page_docs, final_file_name


def _build_document_chunk_id(
    document_id: int,
    chunk_type: str,
    metadata: dict[str, object],
    page_content: str,
) -> str:
    """Create a deterministic chunk ID scoped to one stored document."""

    identity = {
        "document_id": document_id,
        "chunk_type": chunk_type,
        "work_title": metadata.get("work_title"),
        "start_page": metadata.get("start_page"),
        "end_page": metadata.get("end_page"),
        "page_number": metadata.get("page_number"),
        "content_hash": hashlib.sha256(page_content.encode("utf-8")).hexdigest(),
    }
    serialized_identity = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized_identity.encode("utf-8")).hexdigest()


def _build_stored_chunk_hash(metadata: dict[str, object]) -> str:
    """Build the persisted chunk hash from content plus canonical metadata."""

    page_content = str(metadata.get("page_content") or "")
    serialized_metadata = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(
        f"{page_content}{serialized_metadata}".encode("utf-8")
    ).hexdigest()


def _persist_book_document(
    task: "ProcessingTask",
    db: Session,
    temp_path: str,
    file_name: str,
    kb_id: int,
    minio_client: object,
    analysis: dict,
    work_docs: List[LangchainDocument],
    page_docs: List[LangchainDocument],
    final_file_name: str,
) -> tuple[int, str]:
    """Store a processed book document and all of its chunks."""
    task_id = task.id
    existing_document = _find_document_conflict(
        db,
        kb_id,
        task.document_upload.file_hash,
        final_file_name,
    )
    if existing_document:
        minio_client.remove_object(settings.MINIO_BUCKET_NAME, temp_path)
        _mark_task_completed_with_existing_document(db, task_id, existing_document.id)
        logger.info(
            "Task %d: Reused existing processed document %d",
            task_id,
            existing_document.id,
        )
        return existing_document.id, existing_document.file_path

    temp_object_name = temp_path.split("/")[-1]
    permanent_path = f"kb_{kb_id}/{temp_object_name}"

    t0 = time.monotonic()
    try:
        minio_client.copy_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=permanent_path,
            source=CopySource(settings.MINIO_BUCKET_NAME, temp_path),
        )
        minio_client.remove_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=temp_path,
        )
    except MinioException as exc:
        raise BookIndexingError(
            f"Failed to move file to permanent storage: {exc}"
        ) from exc
    logger.info("Task %d: MinIO move in %.1fs", task_id, time.monotonic() - t0)

    document = Document(
        file_name=final_file_name,
        file_path=permanent_path,
        file_hash=task.document_upload.file_hash,
        file_size=task.document_upload.file_size,
        content_type=task.document_upload.content_type,
        knowledge_base_id=kb_id,
        analysis=analysis,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    task.document_id = document.id
    db.commit()
    logger.info("Task %d: Document record created (id=%d)", task_id, document.id)

    t0 = time.monotonic()
    seen_chunk_ids: set[str] = set()

    for i, doc in enumerate(work_docs):
        base_metadata: dict[str, object] = {
            **doc.metadata,
            "kb_id": kb_id,
            "document_id": document.id,
            "chunk_type": "work",
        }
        chunk_id = _build_document_chunk_id(
            document.id,
            "work",
            base_metadata,
            doc.page_content,
        )
        if chunk_id in seen_chunk_ids:
            logger.warning(
                "Task %d: Skipping duplicate work chunk for document %d (%s)",
                task_id,
                document.id,
                doc.metadata.get("work_title") or f"work #{i + 1}",
            )
            continue
        seen_chunk_ids.add(chunk_id)

        chunk_metadata = {
            "page_content": doc.page_content,
            **base_metadata,
            "chunk_id": chunk_id,
        }
        doc.metadata.update(base_metadata)
        doc.metadata["chunk_id"] = chunk_id

        db.add(
            DocumentChunk(
                id=chunk_id,
                document_id=document.id,
                kb_id=kb_id,
                file_name=file_name,
                chunk_type="work",
                chunk_label=doc.metadata.get("work_title"),
                start_page=doc.metadata.get("start_page"),
                end_page=doc.metadata.get("end_page"),
                chunk_metadata=chunk_metadata,
                hash=_build_stored_chunk_hash(chunk_metadata),
            )
        )

        if i > 0 and i % 50 == 0:
            db.commit()

    for i, doc in enumerate(page_docs):
        page_number = int(doc.metadata.get("page_number", 0))
        base_metadata = {
            **doc.metadata,
            "kb_id": kb_id,
            "document_id": document.id,
            "chunk_type": "page",
        }
        chunk_id = _build_document_chunk_id(
            document.id,
            "page",
            base_metadata,
            doc.page_content,
        )
        if chunk_id in seen_chunk_ids:
            logger.warning(
                "Task %d: Skipping duplicate page chunk for document %d (page %d)",
                task_id,
                document.id,
                page_number,
            )
            continue
        seen_chunk_ids.add(chunk_id)

        chunk_metadata = {
            "page_content": doc.page_content,
            **base_metadata,
            "chunk_id": chunk_id,
        }
        doc.metadata.update(base_metadata)
        doc.metadata["chunk_id"] = chunk_id

        db.add(
            DocumentChunk(
                id=chunk_id,
                document_id=document.id,
                kb_id=kb_id,
                file_name=file_name,
                chunk_type="page",
                chunk_label=f"Page {page_number}",
                page_number=page_number,
                start_page=page_number,
                end_page=page_number,
                chunk_metadata=chunk_metadata,
                hash=_build_stored_chunk_hash(chunk_metadata),
            )
        )

        if i > 0 and i % 100 == 0:
            db.commit()

    db.commit()
    logger.info(
        "Task %d: Stored %d chunk records in %.1fs",
        task_id,
        len(work_docs) + len(page_docs),
        time.monotonic() - t0,
    )
    return document.id, permanent_path


# ─── Upload ───────────────────────────────────────────────────────────────────


async def upload_document(file: UploadFile, kb_id: int) -> UploadResult:
    """Upload a JSON OCR document to MinIO.

    Args:
        file: Uploaded file object.
        kb_id: Knowledge base ID.

    Returns:
        UploadResult with path, size, hash, and content type.
    """
    content = await file.read()
    file_size = len(content)
    file_hash = hashlib.sha256(content).hexdigest()

    file_name = "".join(
        c for c in (file.filename or "upload") if c.isalnum() or c in ("-", "_", ".")
    ).strip()
    object_path = f"kb_{kb_id}/{file_name}"

    _, ext = os.path.splitext(file_name)
    content_type = _CONTENT_TYPE_BY_EXT.get(ext.lower(), "application/octet-stream")

    minio_client = get_minio_client()
    try:
        minio_client.put_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_path,
            data=BytesIO(content),
            length=file_size,
            content_type=content_type,
        )
    except Exception as exc:
        logger.error(f"Failed to upload file to MinIO: {exc}")
        raise

    return UploadResult(
        file_path=object_path,
        file_name=file_name,
        file_size=file_size,
        content_type=content_type,
        file_hash=file_hash,
    )


# ─── Background processing ────────────────────────────────────────────────────


def _process_xlsx_document(
    task: "ProcessingTask",
    db: Session,
    temp_path: str,
    file_name: str,
    kb_id: int,
    minio_client: object,
    local_temp_path: str,
) -> None:
    """Parse a glossary xlsx and store one DocumentChunk per term row.

    Called by process_document_background when the file is a .xlsx.
    Raises BookIndexingError on any failure so the caller can mark the task
    as failed and clean up MinIO.
    """
    task_id = task.id
    permanent_path: str | None = None
    document_id: int | None = None

    try:
        # 1. Download from MinIO
        try:
            minio_client.fget_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=temp_path,
                file_path=local_temp_path,
            )
        except MinioException as exc:
            raise BookIndexingError(
                f"Failed to download xlsx from MinIO: {exc}"
            ) from exc

        # 2. Parse terms
        try:
            terms, glossary_metadata = parse_glossary_xlsx(local_temp_path)
        except ValueError as exc:
            raise BookIndexingError(str(exc)) from exc
        if not terms:
            raise BookIndexingError(
                "No terms found in the xlsx file. "
                "Ensure it contains a header row with recognised Kazakh column names."
            )

        # 3. Move temp → permanent (UUID-based key already set)
        temp_object_name = temp_path.split("/")[-1]
        permanent_path = f"kb_{kb_id}/{temp_object_name}"
        existing_document = _find_document_conflict(
            db,
            kb_id,
            task.document_upload.file_hash,
            file_name,
        )
        if existing_document:
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, temp_path)
            _mark_task_completed_with_existing_document(
                db, task_id, existing_document.id
            )
            logger.info(
                "Task %d: Reused existing glossary document %d",
                task_id,
                existing_document.id,
            )
            return

        try:
            from minio.commonconfig import CopySource

            minio_client.copy_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=permanent_path,
                source=CopySource(settings.MINIO_BUCKET_NAME, temp_path),
            )
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, temp_path)
        except MinioException as exc:
            raise BookIndexingError(
                f"Failed to move xlsx to permanent storage: {exc}"
            ) from exc

        # 4. Collect metadata summary for Document.analysis
        authors = sorted({t.get("author", "") for t in terms if t.get("author")})
        fields = sorted({t.get("field", "") for t in terms if t.get("field")})
        analysis = {
            "type": "glossary",
            "term_count": len(terms),
            "authors": authors,
            "fields": fields,
            "title": (glossary_metadata.get("title") or "").strip() or None,
            "source_author": (
                (glossary_metadata.get("author") or "").strip() or None
            ),
        }

        # 5. Create Document record
        document = Document(
            file_name=file_name,
            file_path=permanent_path,
            file_hash=task.document_upload.file_hash,
            file_size=task.document_upload.file_size,
            content_type=task.document_upload.content_type,
            knowledge_base_id=kb_id,
            analysis=analysis,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        document_id = document.id
        task.document_id = document.id
        db.commit()
        logger.info(
            "Task %d: Glossary document created (id=%d, %d terms)",
            task_id,
            document.id,
            len(terms),
        )

        # 6. Store DocumentChunk records (one per term)
        t0 = time.monotonic()
        for i, term in enumerate(terms):
            alash_term = term.get("alash_term", "")
            chunk_id = hashlib.sha256(
                f"term:{kb_id}:{document.id}:{alash_term}:{i}".encode()
            ).hexdigest()

            metadata = {
                "kb_id": kb_id,
                "document_id": document.id,
                "chunk_id": chunk_id,
                "chunk_type": "term",
                **term,
            }

            db.add(
                DocumentChunk(
                    id=chunk_id,
                    document_id=document.id,
                    kb_id=kb_id,
                    file_name=file_name,
                    chunk_type="term",
                    chunk_label=alash_term,
                    chunk_metadata=metadata,
                    hash=hashlib.sha256(
                        term.get("page_content", "").encode()
                    ).hexdigest(),
                )
            )

            if i > 0 and i % 200 == 0:
                db.commit()

        db.commit()
        logger.info(
            "Task %d: Stored %d term chunks in %.1fs",
            task_id,
            len(terms),
            time.monotonic() - t0,
        )

        # 7. Mark completed
        task.status = "completed"
        task.document_id = document.id
        upload = task.document_upload
        if upload:
            upload.status = "completed"
        db.commit()
        logger.info("Task %d: Glossary processing completed", task_id)
    except Exception:
        db.rollback()
        _cleanup_failed_processing(
            db,
            document_id=document_id,
            temp_path=temp_path,
            permanent_path=permanent_path,
        )
        raise


def _process_personal_document(
    task: "ProcessingTask",
    db: Session,
    temp_path: str,
    file_name: str,
    kb_id: int,
    minio_client: object,
    local_temp_path: str,
) -> None:
    """Process a personal upload through OCR/page extraction and book indexing."""
    task_id = task.id
    permanent_path: str | None = None
    document_id: int | None = None
    ext = os.path.splitext(file_name)[1].lower()

    try:
        try:
            minio_client.fget_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=temp_path,
                file_path=local_temp_path,
            )
        except MinioException as exc:
            raise BookIndexingError(
                f"Failed to download personal upload from MinIO: {exc}"
            ) from exc

        logger.info("Task %d: Extracting pages from %s", task_id, ext)
        t0 = time.monotonic()
        if ext == ".docx":
            pages = extract_pages_from_docx(local_temp_path)
        elif ext == ".pdf":
            pages = extract_pages_from_pdf(local_temp_path)
        else:
            raise BookIndexingError(
                f"Unsupported personal upload extension: {ext}. "
                f"Allowed: {', '.join(PERSONAL_UPLOAD_EXTENSIONS)}"
            )

        cleaned_pages = _load_pages_from_records(pages)
        if not cleaned_pages:
            raise BookIndexingError(
                "No readable text was extracted from the uploaded file."
            )
        logger.info(
            "Task %d: Extracted %d pages in %.1fs",
            task_id,
            len(cleaned_pages),
            time.monotonic() - t0,
        )

        analysis, work_docs, page_docs, final_file_name = _analyze_book_pages(
            db=db,
            kb_id=kb_id,
            task_id=task_id,
            file_name=file_name,
            pages=cleaned_pages,
            display_suffix=ext,
        )
        document_id, permanent_path = _persist_book_document(
            task=task,
            db=db,
            temp_path=temp_path,
            file_name=file_name,
            kb_id=kb_id,
            minio_client=minio_client,
            analysis=analysis,
            work_docs=work_docs,
            page_docs=page_docs,
            final_file_name=final_file_name,
        )

        task.status = "completed"
        task.document_id = document_id
        upload = task.document_upload
        if upload:
            upload.status = "completed"
        db.commit()
        logger.info("Task %d: Personal document processing completed", task_id)
    except Exception:
        db.rollback()
        _cleanup_failed_processing(
            db,
            document_id=document_id,
            temp_path=temp_path,
            permanent_path=permanent_path,
        )
        raise


def process_document_background(
    temp_path: str,
    file_name: str,
    kb_id: int,
    task_id: int,
    db: Optional[Session] = None,
) -> None:
    """Process a JSON OCR document in a background thread.

    Downloads the file from MinIO, runs book indexing via the LLM,
    extracts work-level text segments plus raw pages, and stores them in MySQL.

    Must be called via ``asyncio.to_thread`` to avoid blocking the event loop.

    Args:
        temp_path: MinIO object path of the temporary upload.
        file_name: Original file name.
        kb_id: Knowledge base ID.
        task_id: ProcessingTask ID to update.
        db: Optional SQLAlchemy session (created if not provided).
    """
    if db is None:
        db = SessionLocal()
        should_close_db = True
    else:
        should_close_db = False

    task = db.query(ProcessingTask).get(task_id)
    if not task:
        logger.error(f"Task {task_id} not found")
        return

    local_temp_path = f"/tmp/proc_{task_id}_{file_name}"

    document_id: int | None = None
    permanent_path: str | None = None

    try:
        task.status = "processing"
        db.commit()

        minio_client = get_minio_client()

        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        is_personal_kb = bool(kb and kb.is_personal)

        # Route xlsx files to the glossary processor
        if file_name.lower().endswith(".xlsx"):
            _process_xlsx_document(
                task, db, temp_path, file_name, kb_id, minio_client, local_temp_path
            )
            return

        # Route personal-KB uploads (.docx, .pdf) through the page-chunk processor
        if is_personal_kb:
            ext = os.path.splitext(file_name)[1].lower()
            if ext not in PERSONAL_UPLOAD_EXTENSIONS:
                raise BookIndexingError(
                    f"Personal uploads support {', '.join(PERSONAL_UPLOAD_EXTENSIONS)} "
                    f"only; got {ext}"
                )
            _process_personal_document(
                task, db, temp_path, file_name, kb_id, minio_client, local_temp_path
            )
            return

        # 1. Download from MinIO
        try:
            minio_client.fget_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=temp_path,
                file_path=local_temp_path,
            )
        except MinioException as exc:
            raise BookIndexingError(
                f"Failed to download file from MinIO: {exc}"
            ) from exc

        # 2. Load and clean pages from JSON
        logger.info(f"Task {task_id}: Loading pages from JSON")
        pages = load_pages_from_json(local_temp_path)
        analysis, work_docs, page_docs, final_file_name = _analyze_book_pages(
            db=db,
            kb_id=kb_id,
            task_id=task_id,
            file_name=file_name,
            pages=pages,
            display_suffix=".json",
        )
        document_id, permanent_path = _persist_book_document(
            task=task,
            db=db,
            temp_path=temp_path,
            file_name=file_name,
            kb_id=kb_id,
            minio_client=minio_client,
            analysis=analysis,
            work_docs=work_docs,
            page_docs=page_docs,
            final_file_name=final_file_name,
        )

        # 11. Mark completed
        task.status = "completed"
        task.document_id = document_id
        upload = task.document_upload
        if upload:
            upload.status = "completed"
        db.commit()
        logger.info(f"Task {task_id}: Processing completed successfully")

    except BookIndexingError as exc:
        logger.error(f"Task {task_id}: Book indexing failed: {exc}")
        db.rollback()
        _cleanup_failed_processing(
            db,
            document_id=document_id,
            temp_path=temp_path,
            permanent_path=permanent_path,
        )
        _mark_task_failed(db, task_id, str(exc))

    except Exception as exc:
        logger.error(f"Task {task_id}: Unexpected error: {exc}")
        logger.error(traceback.format_exc())
        db.rollback()
        _cleanup_failed_processing(
            db,
            document_id=document_id,
            temp_path=temp_path,
            permanent_path=permanent_path,
        )
        _mark_task_failed(db, task_id, f"Unexpected error: {exc}")

    finally:
        if os.path.exists(local_temp_path):
            try:
                os.remove(local_temp_path)
            except Exception:
                pass
        if should_close_db and db:
            db.close()
