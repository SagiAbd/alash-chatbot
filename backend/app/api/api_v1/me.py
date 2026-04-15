"""Endpoints scoped to the authenticated user's personal library."""

import asyncio
import hashlib
import logging
import os
import uuid
from io import BytesIO
from typing import Any, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from minio.error import MinioException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.minio import get_minio_client
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentUpload,
    ProcessingTask,
)
from app.models.user import User
from app.schemas.knowledge import DocumentResponse
from app.services.document_processor import (
    PERSONAL_UPLOAD_EXTENSIONS,
    process_document_background,
)
from app.services.personal_library import ensure_personal_kb

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/library", response_model=List[DocumentResponse])
def list_personal_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """List the caller's personal-library documents."""
    kb = ensure_personal_kb(db, current_user)
    return (
        db.query(Document)
        .filter(Document.knowledge_base_id == kb.id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get("/library/documents/{doc_id}/chunks")
def get_personal_document_chunks(
    *,
    db: Session = Depends(get_db),
    doc_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return viewer chunks for a document in the caller's personal library."""
    kb = ensure_personal_kb(db, current_user)
    document = (
        db.query(Document)
        .filter(
            Document.id == doc_id,
            Document.knowledge_base_id == kb.id,
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    is_glossary = (
        isinstance(document.analysis, dict)
        and document.analysis.get("type") == "glossary"
    )

    if is_glossary:
        chunks = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == doc_id,
                DocumentChunk.chunk_type == "term",
            )
            .all()
        )
    else:
        chunks = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == doc_id,
                DocumentChunk.chunk_type == "work",
            )
            .all()
        )
        if not chunks:
            chunks = (
                db.query(DocumentChunk)
                .filter(
                    DocumentChunk.document_id == doc_id,
                    DocumentChunk.chunk_type.is_(None),
                )
                .all()
            )

    chunks.sort(
        key=lambda chunk: (
            chunk.start_page
            or (chunk.chunk_metadata or {}).get("start_page")
            or 0,
            chunk.id,
        )
    )
    return [{"id": c.id, "chunk_metadata": c.chunk_metadata} for c in chunks]


@router.get("/library/tasks")
def list_personal_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return in-flight or failed personal uploads so the UI can show progress."""
    kb = ensure_personal_kb(db, current_user)
    tasks = (
        db.query(ProcessingTask)
        .filter(
            ProcessingTask.knowledge_base_id == kb.id,
            ProcessingTask.status.in_(["pending", "processing", "failed"]),
        )
        .all()
    )
    return [
        {
            "task_id": t.id,
            "document_id": t.document_id,
            "file_name": t.document_upload.file_name if t.document_upload else None,
            "status": t.status,
            "error_message": t.error_message,
        }
        for t in tasks
    ]


@router.post("/library/upload")
async def upload_personal_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Upload a ``.docx`` or ``.pdf`` into the caller's personal library."""
    file_name = file.filename or "upload"
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in PERSONAL_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only "
                f"{', '.join(PERSONAL_UPLOAD_EXTENSIONS)} files can be uploaded "
                "to your personal library."
            ),
        )

    kb = ensure_personal_kb(db, current_user)
    kb_id = kb.id

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty.")

    file_hash = hashlib.sha256(content).hexdigest()

    existing_by_hash = (
        db.query(Document)
        .filter(
            Document.knowledge_base_id == kb_id,
            Document.file_hash == file_hash,
        )
        .first()
    )
    if existing_by_hash:
        return {
            "status": "exists",
            "document_id": existing_by_hash.id,
            "message": "An identical file is already in your library.",
        }

    existing_by_name = (
        db.query(Document)
        .filter(
            Document.knowledge_base_id == kb_id,
            Document.file_name == file_name,
        )
        .first()
    )
    if existing_by_name:
        raise HTTPException(
            status_code=409,
            detail=(
                "A different document with the same file name already exists. "
                "Rename the file before uploading."
            ),
        )

    unique_name = f"{uuid.uuid4().hex}{ext}"
    temp_path = f"kb_{kb_id}/temp/{unique_name}"
    minio_client = get_minio_client()
    try:
        minio_client.put_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=temp_path,
            data=BytesIO(content),
            length=len(content),
            content_type=file.content_type or "application/octet-stream",
        )
    except MinioException as exc:
        logger.error("Failed to upload personal file to MinIO: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to upload file to object storage."
        ) from exc

    upload = DocumentUpload(
        knowledge_base_id=kb_id,
        file_name=file_name,
        file_hash=file_hash,
        file_size=len(content),
        content_type=file.content_type or "application/octet-stream",
        temp_path=temp_path,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    task = ProcessingTask(
        document_upload_id=upload.id,
        knowledge_base_id=kb_id,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    background_tasks.add_task(
        _run_personal_processing,
        temp_path=temp_path,
        file_name=file_name,
        kb_id=kb_id,
        task_id=task.id,
    )

    return {
        "status": "pending",
        "upload_id": upload.id,
        "task_id": task.id,
        "file_name": file_name,
        "message": "File uploaded and queued for processing.",
    }


async def _run_personal_processing(
    temp_path: str, file_name: str, kb_id: int, task_id: int
) -> None:
    """Kick off the background document processor without blocking the request."""
    asyncio.create_task(
        asyncio.to_thread(
            process_document_background,
            temp_path,
            file_name,
            kb_id,
            task_id,
        )
    )


@router.delete("/library/documents/{doc_id}")
def delete_personal_document(
    *,
    db: Session = Depends(get_db),
    doc_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """Delete a document from the caller's personal library."""
    kb = ensure_personal_kb(db, current_user)
    document = (
        db.query(Document)
        .filter(
            Document.id == doc_id,
            Document.knowledge_base_id == kb.id,
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    minio_client = get_minio_client()
    try:
        minio_client.remove_object(settings.MINIO_BUCKET_NAME, document.file_path)
    except MinioException as exc:
        logger.warning(
            "Failed to remove personal document %s from MinIO: %s", doc_id, exc
        )

    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
    db.query(ProcessingTask).filter(ProcessingTask.document_id == doc_id).delete()
    db.delete(document)
    db.commit()

    return {"status": "deleted"}
