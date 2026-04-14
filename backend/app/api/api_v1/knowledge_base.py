import asyncio
import base64
import binascii
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import JSONResponse
from minio.error import MinioException
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.minio import get_minio_client
from app.core.security import get_current_admin
from app.db.session import get_db
from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentUpload,
    KnowledgeBase,
    ProcessingTask,
)
from app.models.user import User
from app.schemas.knowledge import (
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseExportChunk,
    KnowledgeBaseExportDocument,
    KnowledgeBaseExportMetadata,
    KnowledgeBaseExportPayload,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.services.app_settings import get_or_create_app_settings
from app.services.document_processor import process_document_background

router = APIRouter()

logger = logging.getLogger(__name__)


def _build_upload_result(
    *,
    file_name: str,
    status: str,
    skip_processing: bool,
    message: str | None = None,
    upload_id: int | None = None,
    document_id: int | None = None,
    temp_path: str | None = None,
) -> dict[str, Any]:
    """Build a consistent upload response payload for one file."""
    return {
        "upload_id": upload_id,
        "document_id": document_id,
        "file_name": file_name,
        "status": status,
        "message": message,
        "skip_processing": skip_processing,
        "temp_path": temp_path,
    }


def _cleanup_minio_object(object_name: str) -> None:
    """Delete a MinIO object best-effort."""
    try:
        minio_client = get_minio_client()
        minio_client.remove_object(settings.MINIO_BUCKET_NAME, object_name)
    except Exception:
        logger.warning("Failed to clean up MinIO object %s", object_name)


def _get_knowledge_base_for_user(
    db: Session, kb_id: int, user_id: int
) -> KnowledgeBase | None:
    """Return a knowledge base by ID for admin access."""
    del user_id
    return db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()


def _read_minio_object_bytes(object_name: str) -> bytes:
    """Read a MinIO object fully into memory."""
    response = None
    try:
        minio_client = get_minio_client()
        response = minio_client.get_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_name,
        )
        return response.read()
    finally:
        if response is not None:
            response.close()
            response.release_conn()


def _build_imported_chunk_metadata(
    metadata: dict[str, Any], kb_id: int, document_id: int, chunk_id: str
) -> dict[str, Any]:
    """Repoint imported chunk metadata to the new KB/document IDs."""
    updated_metadata = dict(metadata)
    updated_metadata["kb_id"] = kb_id
    updated_metadata["document_id"] = document_id
    updated_metadata["chunk_id"] = chunk_id
    return updated_metadata


def _build_imported_chunk_id(kb_id: int, document_id: int, original_id: str) -> str:
    """Create a deterministic chunk ID for an imported chunk."""
    return hashlib.sha256(
        f"import:{kb_id}:{document_id}:{original_id}".encode("utf-8")
    ).hexdigest()


def _build_chunk_hash(metadata: dict[str, Any]) -> str:
    """Build the stored hash for a chunk from its content and metadata."""
    page_content = str(metadata.get("page_content") or "")
    serialized_metadata = json.dumps(
        metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(
        f"{page_content}{serialized_metadata}".encode("utf-8")
    ).hexdigest()


def _sanitize_export_file_name(name: str, kb_id: int) -> str:
    """Convert a KB name into a download-safe JSON filename."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("._")
    if not sanitized:
        sanitized = f"knowledge-base-{kb_id}"
    return f"{sanitized}.json"


def _cleanup_imported_objects(object_names: list[str]) -> None:
    """Delete MinIO objects created during a failed import."""
    for object_name in object_names:
        try:
            minio_client = get_minio_client()
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, object_name)
        except Exception:
            logger.warning("Failed to clean up imported object %s", object_name)


def _build_knowledge_base_export_payload(
    kb: KnowledgeBase,
) -> KnowledgeBaseExportPayload:
    """Build a portable JSON export payload for a knowledge base."""
    documents = sorted(
        kb.documents,
        key=lambda document: (document.created_at, document.id),
    )
    export_documents: list[KnowledgeBaseExportDocument] = []

    for document in documents:
        try:
            source_bytes = _read_minio_object_bytes(document.file_path)
        except Exception as exc:
            logger.error(
                "Failed to read source file for KB %s document %s: %s",
                kb.id,
                document.id,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed to read source file for document '{document.file_name}'"
                ),
            ) from exc

        chunks = sorted(
            document.chunks,
            key=lambda chunk: (
                chunk.start_page or 0,
                chunk.page_number or 0,
                chunk.created_at,
                chunk.id,
            ),
        )

        export_documents.append(
            KnowledgeBaseExportDocument(
                file_name=document.file_name,
                file_size=document.file_size,
                content_type=document.content_type,
                file_hash=document.file_hash,
                analysis=document.analysis,
                created_at=document.created_at,
                updated_at=document.updated_at,
                source_bytes_base64=base64.b64encode(source_bytes).decode("ascii"),
                chunks=[
                    KnowledgeBaseExportChunk(
                        id=chunk.id,
                        chunk_type=chunk.chunk_type,
                        chunk_label=chunk.chunk_label,
                        page_number=chunk.page_number,
                        start_page=chunk.start_page,
                        end_page=chunk.end_page,
                        chunk_metadata=chunk.chunk_metadata or {},
                        hash=chunk.hash,
                        created_at=chunk.created_at,
                        updated_at=chunk.updated_at,
                    )
                    for chunk in chunks
                ],
            )
        )

    return KnowledgeBaseExportPayload(
        export_version=1,
        exported_at=datetime.utcnow(),
        knowledge_base=KnowledgeBaseExportMetadata(
            name=kb.name,
            description=kb.description,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        ),
        documents=export_documents,
    )


@router.post("", response_model=KnowledgeBaseResponse)
def create_knowledge_base(
    *,
    db: Session = Depends(get_db),
    kb_in: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Create new knowledge base.
    """
    kb = KnowledgeBase(
        name=kb_in.name, description=kb_in.description, user_id=current_user.id
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    logger.info(f"Knowledge base created: {kb.name} for user {current_user.id}")
    return kb


@router.post("/import", response_model=KnowledgeBaseResponse)
async def import_knowledge_base(
    *,
    db: Session = Depends(get_db),
    file: UploadFile,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Import a knowledge base from a JSON export file.
    """
    try:
        payload = KnowledgeBaseExportPayload.model_validate_json(await file.read())
    except ValidationError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid knowledge base export: {exc.errors()}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="Import file is not valid JSON"
        ) from exc

    if payload.export_version != 1:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export version: {payload.export_version}",
        )

    kb = KnowledgeBase(
        name=payload.knowledge_base.name,
        description=payload.knowledge_base.description,
        user_id=current_user.id,
        created_at=payload.knowledge_base.created_at,
        updated_at=payload.knowledge_base.updated_at,
    )
    db.add(kb)
    db.flush()

    uploaded_objects: list[str] = []

    try:
        minio_client = get_minio_client()

        for exported_document in payload.documents:
            try:
                source_bytes = base64.b64decode(
                    exported_document.source_bytes_base64
                )
            except binascii.Error as exc:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Import file contains invalid source bytes for "
                        f"document '{exported_document.file_name}'"
                    ),
                ) from exc
            ext = (
                exported_document.file_name.rsplit(".", 1)[-1]
                if "." in exported_document.file_name
                else ""
            )
            unique_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
            object_path = f"kb_{kb.id}/{unique_name}"

            minio_client.put_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=object_path,
                data=BytesIO(source_bytes),
                length=len(source_bytes),
                content_type=exported_document.content_type,
            )
            uploaded_objects.append(object_path)

            document = Document(
                file_name=exported_document.file_name,
                file_path=object_path,
                file_hash=exported_document.file_hash
                or hashlib.sha256(source_bytes).hexdigest(),
                file_size=exported_document.file_size or len(source_bytes),
                content_type=exported_document.content_type,
                knowledge_base_id=kb.id,
                analysis=exported_document.analysis,
                created_at=exported_document.created_at,
                updated_at=exported_document.updated_at,
            )
            db.add(document)
            db.flush()

            for exported_chunk in exported_document.chunks:
                chunk_id = _build_imported_chunk_id(
                    kb.id, document.id, exported_chunk.id
                )
                chunk_metadata = _build_imported_chunk_metadata(
                    exported_chunk.chunk_metadata,
                    kb.id,
                    document.id,
                    chunk_id,
                )
                db.add(
                    DocumentChunk(
                        id=chunk_id,
                        kb_id=kb.id,
                        document_id=document.id,
                        file_name=document.file_name,
                        chunk_type=exported_chunk.chunk_type,
                        chunk_label=exported_chunk.chunk_label,
                        page_number=exported_chunk.page_number,
                        start_page=exported_chunk.start_page,
                        end_page=exported_chunk.end_page,
                        chunk_metadata=chunk_metadata,
                        hash=_build_chunk_hash(chunk_metadata),
                        created_at=exported_chunk.created_at,
                        updated_at=exported_chunk.updated_at,
                    )
                )

        db.commit()
        db.refresh(kb)
        logger.info(
            "Knowledge base imported: %s for user %s", kb.name, current_user.id
        )
        return kb
    except HTTPException:
        db.rollback()
        _cleanup_imported_objects(uploaded_objects)
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            "Failed to import knowledge base for user %s: %s",
            current_user.id,
            exc,
        )
        _cleanup_imported_objects(uploaded_objects)
        raise HTTPException(
            status_code=500, detail=f"Failed to import knowledge base: {exc}"
        ) from exc


@router.get("", response_model=List[KnowledgeBaseResponse])
def get_knowledge_bases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve knowledge bases.
    """
    del current_user
    knowledge_bases = db.query(KnowledgeBase).offset(skip).limit(limit).all()
    return knowledge_bases


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
def get_knowledge_base(
    *,
    db: Session = Depends(get_db),
    kb_id: int,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Get knowledge base by ID.
    """
    from sqlalchemy.orm import joinedload

    kb = (
        db.query(KnowledgeBase)
        .options(
            joinedload(KnowledgeBase.documents).joinedload(Document.processing_tasks)
        )
        .filter(KnowledgeBase.id == kb_id)
        .first()
    )

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    return kb


@router.get("/{kb_id}/export")
def export_knowledge_base(
    *,
    db: Session = Depends(get_db),
    kb_id: int,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Export a knowledge base to a portable JSON snapshot.
    """
    kb = (
        db.query(KnowledgeBase)
        .options(
            selectinload(KnowledgeBase.documents).selectinload(Document.chunks)
        )
        .filter(KnowledgeBase.id == kb_id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    payload = _build_knowledge_base_export_payload(kb)
    file_name = _sanitize_export_file_name(kb.name, kb.id)

    return JSONResponse(
        content=payload.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
def update_knowledge_base(
    *,
    db: Session = Depends(get_db),
    kb_id: int,
    kb_in: KnowledgeBaseUpdate,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Update knowledge base.
    """
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id)
        .first()
    )

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    for field, value in kb_in.dict(exclude_unset=True).items():
        setattr(kb, field, value)

    db.add(kb)
    db.commit()
    db.refresh(kb)
    logger.info(f"Knowledge base updated: {kb.name} for user {current_user.id}")
    return kb


@router.post("/{kb_id}/set-public-chatbot")
def set_public_chatbot_kb(
    *,
    db: Session = Depends(get_db),
    kb_id: int,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """Set the knowledge base used by the public chatbot."""
    kb = _get_knowledge_base_for_user(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    app_settings = get_or_create_app_settings(db)
    app_settings.public_kb_id = kb.id
    db.add(app_settings)
    db.commit()

    return {
        "message": f'"{kb.name}" is now the public chatbot knowledge base',
        "public_kb_id": kb.id,
    }


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    *,
    db: Session = Depends(get_db),
    kb_id: int,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Delete knowledge base and all associated resources.
    """
    logger = logging.getLogger(__name__)

    kb = _get_knowledge_base_for_user(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    try:
        minio_client = get_minio_client()
        cleanup_errors = []
        app_settings = get_or_create_app_settings(db)

        # 1. Clean up MinIO files
        try:
            # Delete all objects with prefix kb_{kb_id}/
            objects = minio_client.list_objects(
                settings.MINIO_BUCKET_NAME, prefix=f"kb_{kb_id}/"
            )
            for obj in objects:
                minio_client.remove_object(settings.MINIO_BUCKET_NAME, obj.object_name)
            logger.info(f"Cleaned up MinIO files for knowledge base {kb_id}")
        except MinioException as e:
            cleanup_errors.append(f"Failed to clean up MinIO files: {str(e)}")
            logger.error(f"MinIO cleanup error for kb {kb_id}: {str(e)}")

        if app_settings.public_kb_id == kb.id:
            app_settings.public_kb_id = None
            db.add(app_settings)

        # 2. Delete database records
        db.delete(kb)
        db.commit()

        # Report any cleanup errors in the response
        if cleanup_errors:
            return {
                "message": "Knowledge base deleted with cleanup warnings",
                "warnings": cleanup_errors,
            }

        return {
            "message": (
                "Knowledge base and all associated resources deleted successfully"
            )
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete knowledge base {kb_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete knowledge base: {str(e)}"
        )


# Batch upload documents
@router.post("/{kb_id}/documents/upload")
async def upload_kb_documents(
    kb_id: int,
    files: List[UploadFile],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Upload multiple documents to MinIO.
    """
    kb = _get_knowledge_base_for_user(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    results: list[dict[str, Any]] = []
    for file in files:
        file_name = file.filename or "upload"
        file_content = await file.read()
        if not file_content:
            results.append(
                _build_upload_result(
                    file_name=file_name,
                    status="error",
                    skip_processing=True,
                    message="File is empty.",
                )
            )
            continue

        file_hash = hashlib.sha256(file_content).hexdigest()

        existing_by_hash = (
            db.query(Document)
            .filter(
                Document.knowledge_base_id == kb_id,
                Document.file_hash == file_hash,
            )
            .first()
        )
        if existing_by_hash:
            message = (
                "An identical file is already available in this knowledge base."
                if existing_by_hash.file_name == file_name
                else (
                    "An identical file is already available as "
                    f"'{existing_by_hash.file_name}'."
                )
            )
            results.append(
                _build_upload_result(
                    file_name=file_name,
                    status="exists",
                    skip_processing=True,
                    document_id=existing_by_hash.id,
                    message=message,
                )
            )
            continue

        existing_by_name = (
            db.query(Document)
            .filter(
                Document.knowledge_base_id == kb_id,
                Document.file_name == file_name,
            )
            .first()
        )
        if existing_by_name:
            results.append(
                _build_upload_result(
                    file_name=file_name,
                    status="conflict",
                    skip_processing=True,
                    document_id=existing_by_name.id,
                    message=(
                        "A different document with the same file name already "
                        "exists. Rename the file before uploading."
                    ),
                )
            )
            continue

        active_upload = (
            db.query(DocumentUpload)
            .filter(
                DocumentUpload.knowledge_base_id == kb_id,
                DocumentUpload.status.in_(["pending", "processing"]),
                or_(
                    DocumentUpload.file_hash == file_hash,
                    DocumentUpload.file_name == file_name,
                ),
            )
            .order_by(DocumentUpload.id.desc())
            .first()
        )
        if active_upload:
            same_content = active_upload.file_hash == file_hash
            results.append(
                _build_upload_result(
                    file_name=file_name,
                    status="queued" if same_content else "conflict",
                    skip_processing=True,
                    upload_id=active_upload.id,
                    message=(
                        "An identical file is already queued for processing."
                        if same_content
                        else (
                            "A different file with the same name is already "
                            "queued for processing."
                        )
                    ),
                )
            )
            continue

        ext = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
        unique_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
        temp_path = f"kb_{kb_id}/temp/{unique_name}"
        try:
            minio_client = get_minio_client()
            minio_client.put_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=temp_path,
                data=BytesIO(file_content),
                length=len(file_content),
                content_type=file.content_type or "application/octet-stream",
            )
        except MinioException as e:
            logger.error(f"Failed to upload file to MinIO: {str(e)}")
            results.append(
                _build_upload_result(
                    file_name=file_name,
                    status="error",
                    skip_processing=True,
                    message="Failed to upload file to object storage.",
                )
            )
            continue

        upload = DocumentUpload(
            knowledge_base_id=kb_id,
            file_name=file_name,
            file_hash=file_hash,
            file_size=len(file_content),
            content_type=file.content_type or "application/octet-stream",
            temp_path=temp_path,
        )
        db.add(upload)
        try:
            db.commit()
            db.refresh(upload)
        except Exception as exc:
            db.rollback()
            logger.error("Failed to create upload record for %s: %s", file_name, exc)
            _cleanup_minio_object(temp_path)
            results.append(
                _build_upload_result(
                    file_name=file_name,
                    status="error",
                    skip_processing=True,
                    message="Failed to persist the upload record.",
                )
            )
            continue

        results.append(
            _build_upload_result(
                file_name=file_name,
                status="pending",
                skip_processing=False,
                upload_id=upload.id,
                temp_path=temp_path,
                message="File uploaded and ready for processing.",
            )
        )

    return results


@router.post("/{kb_id}/documents/process")
async def process_kb_documents(
    kb_id: int,
    upload_results: List[dict],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Process multiple documents asynchronously.
    """
    kb = _get_knowledge_base_for_user(db, kb_id, current_user.id)

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    task_info: list[dict[str, int]] = []
    upload_ids: list[int] = []
    seen_upload_ids: set[int] = set()

    for result in upload_results:
        if result.get("skip_processing"):
            continue
        upload_id = result.get("upload_id")
        if not upload_id or upload_id in seen_upload_ids:
            continue
        seen_upload_ids.add(upload_id)
        upload_ids.append(upload_id)

    if not upload_ids:
        return {"tasks": []}

    uploads = (
        db.query(DocumentUpload)
        .filter(
            DocumentUpload.id.in_(upload_ids),
            DocumentUpload.knowledge_base_id == kb_id,
        )
        .all()
    )
    uploads_dict = {upload.id: upload for upload in uploads}

    all_tasks = []
    for upload_id in upload_ids:
        upload = uploads_dict.get(upload_id)
        if not upload:
            continue

        existing_task = (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.document_upload_id == upload_id,
                ProcessingTask.status.in_(["pending", "processing"]),
            )
            .order_by(ProcessingTask.id.desc())
            .first()
        )
        if existing_task:
            task_info.append({"upload_id": upload_id, "task_id": existing_task.id})
            continue

        if upload.status != "pending":
            continue

        task = ProcessingTask(
            document_upload_id=upload_id, knowledge_base_id=kb_id, status="pending"
        )
        all_tasks.append(task)

    db.add_all(all_tasks)
    db.commit()

    for task in all_tasks:
        db.refresh(task)

    created_tasks_by_upload_id = {
        task.document_upload_id: task for task in all_tasks if task.document_upload_id
    }
    task_data = []
    for upload_id, task in created_tasks_by_upload_id.items():
        upload = uploads_dict.get(upload_id)
        task_info.append({"upload_id": upload_id, "task_id": task.id})

        if upload:
            task_data.append(
                {
                    "task_id": task.id,
                    "upload_id": upload_id,
                    "temp_path": upload.temp_path,
                    "file_name": upload.file_name,
                }
            )

    background_tasks.add_task(add_processing_tasks_to_queue, task_data, kb_id)

    return {"tasks": task_info}


async def add_processing_tasks_to_queue(task_data, kb_id):
    """Add document processing tasks to the queue without blocking the response."""
    for data in task_data:
        asyncio.create_task(
            asyncio.to_thread(
                process_document_background,
                data["temp_path"],
                data["file_name"],
                kb_id,
                data["task_id"],
            )
        )
    logger.info(f"Added {len(task_data)} document processing tasks to queue")


@router.post("/cleanup")
async def cleanup_temp_files(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)
):
    """
    Clean up expired temporary files.
    """
    expired_time = datetime.utcnow() - timedelta(hours=24)
    expired_uploads = (
        db.query(DocumentUpload).filter(DocumentUpload.created_at < expired_time).all()
    )

    minio_client = get_minio_client()
    for upload in expired_uploads:
        try:
            minio_client.remove_object(
                bucket_name=settings.MINIO_BUCKET_NAME, object_name=upload.temp_path
            )
        except MinioException as e:
            logger.error(f"Failed to delete temp file {upload.temp_path}: {str(e)}")

        db.delete(upload)

    db.commit()

    return {"message": f"Cleaned up {len(expired_uploads)} expired uploads"}


@router.get("/{kb_id}/tasks")
async def get_kb_tasks(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Get all non-completed and failed processing tasks for a knowledge base.

    Returns pending/processing/failed tasks so the UI can show unfinished uploads
    and keep failures visible after a page reload without relying on in-memory
    state.
    """
    kb = _get_knowledge_base_for_user(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    tasks = (
        db.query(ProcessingTask)
        .options(selectinload(ProcessingTask.document_upload))
        .filter(
            ProcessingTask.knowledge_base_id == kb_id,
            ProcessingTask.status.in_(["pending", "processing", "failed"]),
        )
        .all()
    )

    return [
        {
            "task_id": t.id,
            "document_id": t.document_id,
            "file_name": t.document_upload.file_name if t.document_upload else None,
            "file_size": t.document_upload.file_size if t.document_upload else None,
            "status": t.status,
            "error_message": t.error_message,
        }
        for t in tasks
    ]


@router.delete("/{kb_id}/tasks/{task_id}")
async def cancel_processing_task(
    *,
    db: Session = Depends(get_db),
    kb_id: int,
    task_id: int,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Cancel a pending or processing task.

    Removes the task and its associated upload record, and deletes the
    temporary file from MinIO. The background worker may still complete
    if it is already mid-flight, but the task record will be gone.
    """
    task = (
        db.query(ProcessingTask)
        .options(selectinload(ProcessingTask.document_upload))
        .join(KnowledgeBase)
        .filter(
            ProcessingTask.id == task_id,
            ProcessingTask.knowledge_base_id == kb_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Delete temp MinIO file
    upload = task.document_upload
    if upload and upload.temp_path:
        try:
            minio_client = get_minio_client()
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, upload.temp_path)
        except Exception as exc:
            logger.warning(f"Could not delete temp file for task {task_id}: {exc}")

    if upload:
        db.delete(upload)
    db.delete(task)
    db.commit()
    return {"message": "Task cancelled"}


@router.get("/{kb_id}/documents/tasks")
async def get_processing_tasks(
    kb_id: int,
    task_ids: str = Query(
        ..., description="Comma-separated list of task IDs to check status for"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Get status of multiple processing tasks.
    """
    task_id_list = [int(id.strip()) for id in task_ids.split(",")]

    kb = _get_knowledge_base_for_user(db, kb_id, current_user.id)

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    tasks = (
        db.query(ProcessingTask)
        .options(selectinload(ProcessingTask.document_upload))
        .filter(
            ProcessingTask.id.in_(task_id_list),
            ProcessingTask.knowledge_base_id == kb_id,
        )
        .all()
    )

    return {
        task.id: {
            "document_id": task.document_id,
            "status": task.status,
            "error_message": task.error_message,
            "upload_id": task.document_upload_id,
            "file_name": task.document_upload.file_name
            if task.document_upload
            else None,
        }
        for task in tasks
    }


@router.get("/{kb_id}/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    *,
    db: Session = Depends(get_db),
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Get document details by ID.
    """
    document = (
        db.query(Document)
        .join(KnowledgeBase)
        .filter(
            Document.id == doc_id,
            Document.knowledge_base_id == kb_id,
        )
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return document


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    *,
    db: Session = Depends(get_db),
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Delete a single document and all associated resources.

    Removes the file from MinIO, its chunks from the vector store and database,
    and all processing task records before deleting the document itself.
    """
    document = (
        db.query(Document)
        .join(KnowledgeBase)
        .filter(
            Document.id == doc_id,
            Document.knowledge_base_id == kb_id,
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    cleanup_errors = []

    # 1. Delete from MinIO
    try:
        minio_client = get_minio_client()
        minio_client.remove_object(settings.MINIO_BUCKET_NAME, document.file_path)
    except MinioException as e:
        cleanup_errors.append(f"MinIO cleanup failed: {str(e)}")
        logger.error(f"MinIO cleanup error for document {doc_id}: {str(e)}")

    # 2. Delete DB records (chunks, tasks, document)
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
    db.query(ProcessingTask).filter(ProcessingTask.document_id == doc_id).delete()
    db.delete(document)
    db.commit()

    if cleanup_errors:
        return {
            "message": "Document deleted with cleanup warnings",
            "warnings": cleanup_errors,
        }
    return {"message": "Document deleted successfully"}


@router.get("/{kb_id}/documents/{doc_id}/chunks")
async def get_document_chunks(
    *,
    db: Session = Depends(get_db),
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Get stored chunks for a document.

    Returns chunk content from the DocumentChunk table. The page_content
    is stored inside the chunk_metadata JSON field.
    """
    document = (
        db.query(Document)
        .join(KnowledgeBase)
        .filter(
            Document.id == doc_id,
            Document.knowledge_base_id == kb_id,
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
