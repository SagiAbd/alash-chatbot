"""
Document processor service.

Handles uploading JSON OCR files to MinIO and processing them
through the book indexer to produce work-level vector store entries.
"""
import hashlib
import logging
import os
import re
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
from app.models.knowledge import Document, DocumentChunk, ProcessingTask
from app.services.book_indexer import (
    BookIndexingError,
    build_analysis_input,
    extract_works,
    index_book,
    load_pages_from_json,
)

logger = logging.getLogger(__name__)


# ─── Public models ────────────────────────────────────────────────────────────


class UploadResult(BaseModel):
    file_path: str
    file_name: str
    file_size: int
    content_type: str
    file_hash: str


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
    content_type = "application/json" if ext.lower() == ".json" else "application/octet-stream"

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


def process_document_background(
    temp_path: str,
    file_name: str,
    kb_id: int,
    task_id: int,
    db: Optional[Session] = None,
) -> None:
    """Process a JSON OCR document in a background thread.

    Downloads the file from MinIO, runs book indexing via the LLM,
    extracts work-level text segments, and stores them in the vector store.

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

    try:
        task.status = "processing"
        db.commit()

        # 1. Download from MinIO
        minio_client = get_minio_client()
        try:
            minio_client.fget_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=temp_path,
                file_path=local_temp_path,
            )
        except MinioException as exc:
            raise BookIndexingError(f"Failed to download file from MinIO: {exc}") from exc

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
            logger.warning(f"Task {task_id}: Could not fetch known authors: {exc}")

        # 5. LLM analysis — raises BookIndexingError on failure
        logger.info(f"Task {task_id}: Running LLM book analysis")
        t0 = time.monotonic()
        book_index = index_book(analysis_input, known_authors=known_authors or None)
        logger.info(
            f"Task {task_id}: Analysis complete in {time.monotonic() - t0:.1f}s — "
            f"{len(book_index.works)} works found, author: {book_index.metadata.main_author}"
        )

        if not book_index.works:
            raise BookIndexingError(
                "LLM found no works in the table of contents. "
                "Ensure the document contains a readable мазмұны/содержание page."
            )

        # 6. Extract work-level text segments
        work_docs = extract_works(pages, book_index, file_name)
        if not work_docs:
            raise BookIndexingError(
                "All works produced empty text after extraction. "
                "Check that page numbers in the table of contents are correct."
            )
        logger.info(f"Task {task_id}: Extracted {len(work_docs)} work segments")

        # 7. Determine final file name (rename to "Author - Title.json" if available)
        main_author = book_index.metadata.main_author.strip()
        book_title = book_index.metadata.book_title.strip()
        if main_author and book_title:
            safe = re.sub(r'[^\w\s\-]', '', f"{main_author} - {book_title}", flags=re.UNICODE)
            final_file_name = f"{safe.strip()}.json"
        else:
            final_file_name = file_name
        permanent_path = f"kb_{kb_id}/{final_file_name}"

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
            raise BookIndexingError(f"Failed to move file to permanent storage: {exc}") from exc
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
        logger.info(f"Task {task_id}: Document record created (id={document.id})")

        # 9. Store DocumentChunk records in DB
        t0 = time.monotonic()
        for i, doc in enumerate(work_docs):
            chunk_id = hashlib.sha256(
                f"{kb_id}:{final_file_name}:{i}:{doc.page_content[:200]}".encode()
            ).hexdigest()

            doc.metadata["kb_id"] = kb_id
            doc.metadata["document_id"] = document.id
            doc.metadata["chunk_id"] = chunk_id

            db_chunk = DocumentChunk(
                id=chunk_id,
                document_id=document.id,
                kb_id=kb_id,
                file_name=file_name,
                chunk_metadata={"page_content": doc.page_content, **doc.metadata},
                hash=hashlib.sha256(
                    (doc.page_content + str(doc.metadata)).encode()
                ).hexdigest(),
            )
            db.add(db_chunk)

            if i > 0 and i % 50 == 0:
                db.commit()

        db.commit()
        logger.info(
            f"Task {task_id}: Stored {len(work_docs)} chunk records "
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
        task.status = "failed"
        task.error_message = str(exc)
        db.commit()
        # Clean up temp MinIO file
        try:
            minio_client = get_minio_client()
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, temp_path)
        except Exception:
            pass

    except Exception as exc:
        logger.error(f"Task {task_id}: Unexpected error: {exc}")
        logger.error(traceback.format_exc())
        task.status = "failed"
        task.error_message = f"Unexpected error: {exc}"
        db.commit()
        try:
            minio_client = get_minio_client()
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, temp_path)
        except Exception:
            pass

    finally:
        if os.path.exists(local_temp_path):
            try:
                os.remove(local_temp_path)
            except Exception:
                pass
        if should_close_db and db:
            db.close()
