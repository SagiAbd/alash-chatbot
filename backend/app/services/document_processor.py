"""
Document processor service.

Handles uploading JSON OCR files to MinIO and processing them
through the book indexer to produce work-level and page-level retrieval records.
"""

import hashlib
import logging
import os
import time
import traceback
from io import BytesIO
from typing import List, Optional

from fastapi import UploadFile
from minio.commonconfig import CopySource
from minio.error import MinioException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.minio import get_minio_client
from app.db.session import SessionLocal
from app.models.knowledge import Document, DocumentChunk, KnowledgeBase, ProcessingTask
from app.services.book_indexer import (
    BookIndexingError,
    build_analysis_input,
    clean_page_text,
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


# ─── Public models ────────────────────────────────────────────────────────────


class UploadResult(BaseModel):
    file_path: str
    file_name: str
    file_size: int
    content_type: str
    file_hash: str


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
    """Process a user-uploaded ``.docx`` or ``.pdf`` into page-level chunks.

    Personal uploads skip the LLM book-indexer path (which requires a table of
    contents) and land as raw page chunks. ``.pdf`` files are OCR'd via the
    configured vision LLM, one request per page, concurrently.
    """
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

        cleaned_pages = [
            {
                "page": int(p.get("page", idx + 1)),
                "text": clean_page_text(p.get("text", "")),
            }
            for idx, p in enumerate(pages)
        ]
        cleaned_pages = [p for p in cleaned_pages if p["text"]]
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
                "Task %d: Reused existing personal document %d",
                task_id,
                existing_document.id,
            )
            return

        temp_object_name = temp_path.split("/")[-1]
        permanent_path = f"kb_{kb_id}/{temp_object_name}"
        try:
            minio_client.copy_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=permanent_path,
                source=CopySource(settings.MINIO_BUCKET_NAME, temp_path),
            )
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, temp_path)
        except MinioException as exc:
            raise BookIndexingError(
                f"Failed to move personal upload to permanent storage: {exc}"
            ) from exc

        analysis = {
            "type": "personal_document",
            "source_format": ext.lstrip("."),
            "page_count": len(cleaned_pages),
        }
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
            "Task %d: Personal document created (id=%d)",
            task_id,
            document.id,
        )

        t0 = time.monotonic()
        for i, page in enumerate(cleaned_pages):
            page_number = int(page["page"])
            page_content = page["text"]
            chunk_id = hashlib.sha256(
                f"page:{kb_id}:{file_name}:{page_number}:{page_content[:200]}".encode()
            ).hexdigest()
            metadata = {
                "kb_id": kb_id,
                "document_id": document.id,
                "chunk_id": chunk_id,
                "chunk_type": "page",
                "page_number": page_number,
                "page_content": page_content,
                "file_name": file_name,
            }
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
                    chunk_metadata=metadata,
                    hash=hashlib.sha256(
                        (page_content + str(metadata)).encode()
                    ).hexdigest(),
                )
            )
            if i > 0 and i % 100 == 0:
                db.commit()

        db.commit()
        logger.info(
            "Task %d: Stored %d personal page chunks in %.1fs",
            task_id,
            len(cleaned_pages),
            time.monotonic() - t0,
        )

        task.status = "completed"
        task.document_id = document.id
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
        logger.info(f"Task {task_id}: Loaded {len(pages)} pages")

        # 3. Build LLM analysis input
        analysis_input = build_analysis_input(pages)

        # 4. Collect known authors from existing documents in this KB
        known_authors: List[str] = []
        try:
            rows = (
                db.query(Document.analysis)
                .filter(
                    Document.knowledge_base_id == kb_id, Document.analysis.isnot(None)
                )
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
            logger.warning(f"Task {task_id}: Could not fetch known authors: {exc}")

        # 5. LLM analysis — raises BookIndexingError on failure
        logger.info(f"Task {task_id}: Running LLM book analysis")
        t0 = time.monotonic()
        book_index = index_book(analysis_input, known_authors=known_authors or None)
        logger.info(
            f"Task {task_id}: Analysis complete in {time.monotonic() - t0:.1f}s — "
            f"{len(book_index.works)} works found, "
            f"author: {book_index.metadata.main_author}"
        )

        if book_index.toc_find_failed or book_index.toc is None:
            reason = book_index.toc_failure_reason.strip() or (
                "LLM could not verify that the extracted candidate TOC pages "
                "actually contain a table of contents."
            )
            raise BookIndexingError(f"TOC find failed: {reason}")

        if not book_index.works:
            raise BookIndexingError(
                "LLM found no works in the table of contents. "
                "Ensure the document contains a readable мазмұны/содержание page."
            )

        # 6. Extract work-level text segments and raw pages
        work_docs = extract_works(pages, book_index, file_name)
        if not work_docs:
            raise BookIndexingError(
                "All works produced empty text after extraction. "
                "Check that page numbers in the table of contents are correct."
            )
        page_docs = extract_pages(pages, book_index, file_name)
        logger.info(f"Task {task_id}: Extracted {len(work_docs)} work segments")

        # 7. Determine display file name (rename to "Author - Title.json" if available)
        main_author = book_index.metadata.main_author.strip()
        book_title = book_index.metadata.book_title.strip()
        if main_author and book_title:
            final_file_name = f"{main_author} - {book_title}.json"
        else:
            final_file_name = file_name
        # Use the UUID from the temp path as the permanent object name so MinIO
        # never sees non-ASCII characters in the object key.
        existing_document = _find_document_conflict(
            db,
            kb_id,
            task.document_upload.file_hash,
            final_file_name,
        )
        if existing_document:
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, temp_path)
            _mark_task_completed_with_existing_document(
                db, task_id, existing_document.id
            )
            logger.info(
                "Task %d: Reused existing processed document %d",
                task_id,
                existing_document.id,
            )
            return

        temp_object_name = temp_path.split("/")[-1]  # e.g. "d4156c80....json"
        permanent_path = f"kb_{kb_id}/{temp_object_name}"

        # Move temp → permanent (single copy, no intermediate step)
        t0 = time.monotonic()
        try:
            source = CopySource(settings.MINIO_BUCKET_NAME, temp_path)
            minio_client.copy_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=permanent_path,
                source=source,
            )
            minio_client.remove_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=temp_path,
            )
        except MinioException as exc:
            raise BookIndexingError(
                f"Failed to move file to permanent storage: {exc}"
            ) from exc
        logger.info(f"Task {task_id}: MinIO move in {time.monotonic() - t0:.1f}s")

        # 8. Create Document record
        document = Document(
            file_name=final_file_name,
            file_path=permanent_path,
            file_hash=task.document_upload.file_hash,
            file_size=task.document_upload.file_size,
            content_type=task.document_upload.content_type,
            knowledge_base_id=kb_id,
            analysis=book_index.model_dump(),
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        document_id = document.id
        task.document_id = document.id
        db.commit()
        logger.info(f"Task {task_id}: Document record created (id={document.id})")

        # 9. Store DocumentChunk records in DB
        t0 = time.monotonic()
        for i, doc in enumerate(work_docs):
            chunk_id = hashlib.sha256(
                (
                    f"work:{kb_id}:{final_file_name}:"
                    f"{doc.metadata.get('work_title', i)}:{doc.page_content[:200]}"
                ).encode()
            ).hexdigest()

            doc.metadata["kb_id"] = kb_id
            doc.metadata["document_id"] = document.id
            doc.metadata["chunk_id"] = chunk_id
            doc.metadata["chunk_type"] = "work"

            db_chunk = DocumentChunk(
                id=chunk_id,
                document_id=document.id,
                kb_id=kb_id,
                file_name=file_name,
                chunk_type="work",
                chunk_label=doc.metadata.get("work_title"),
                start_page=doc.metadata.get("start_page"),
                end_page=doc.metadata.get("end_page"),
                chunk_metadata={"page_content": doc.page_content, **doc.metadata},
                hash=hashlib.sha256(
                    (doc.page_content + str(doc.metadata)).encode()
                ).hexdigest(),
            )
            db.add(db_chunk)

            if i > 0 and i % 50 == 0:
                db.commit()

        for i, doc in enumerate(page_docs):
            page_number = int(doc.metadata.get("page_number", 0))
            chunk_id = hashlib.sha256(
                f"page:{kb_id}:{final_file_name}:{page_number}:{doc.page_content[:200]}".encode()
            ).hexdigest()

            doc.metadata["kb_id"] = kb_id
            doc.metadata["document_id"] = document.id
            doc.metadata["chunk_id"] = chunk_id
            doc.metadata["chunk_type"] = "page"

            db_chunk = DocumentChunk(
                id=chunk_id,
                document_id=document.id,
                kb_id=kb_id,
                file_name=file_name,
                chunk_type="page",
                chunk_label=f"Page {page_number}",
                page_number=page_number,
                start_page=page_number,
                end_page=page_number,
                chunk_metadata={"page_content": doc.page_content, **doc.metadata},
                hash=hashlib.sha256(
                    (doc.page_content + str(doc.metadata)).encode()
                ).hexdigest(),
            )
            db.add(db_chunk)

            if i > 0 and i % 100 == 0:
                db.commit()

        db.commit()
        logger.info(
            f"Task {task_id}: Stored "
            f"{len(work_docs) + len(page_docs)} chunk records "
            f"in {time.monotonic() - t0:.1f}s"
        )

        # 11. Mark completed
        task.status = "completed"
        task.document_id = document.id
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
