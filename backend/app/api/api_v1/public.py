from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.knowledge import Document, DocumentChunk, KnowledgeBase
from app.schemas.app_settings import PublicConfigResponse
from app.schemas.knowledge import DocumentResponse, KnowledgeBaseResponse
from app.services.app_settings import (
    get_or_create_app_settings,
    get_public_welcome_content,
)

router = APIRouter()


def _get_public_kb(db: Session) -> KnowledgeBase:
    app_settings = get_or_create_app_settings(db)
    if app_settings.public_kb_id is None:
        raise HTTPException(
            status_code=409,
            detail="Public chatbot knowledge base is not configured",
        )

    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == app_settings.public_kb_id)
        .first()
    )
    if not kb:
        app_settings.public_kb_id = None
        db.add(app_settings)
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="Configured public chatbot knowledge base was not found",
        )
    return kb


@router.get("/config", response_model=PublicConfigResponse)
def get_public_config(db: Session = Depends(get_db)) -> Any:
    title, text = get_public_welcome_content(db)
    app_settings = get_or_create_app_settings(db)
    chat_available = False
    if app_settings.public_kb_id is not None:
        chat_available = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.id == app_settings.public_kb_id)
            .first()
            is not None
        )
    return PublicConfigResponse(
        welcome_title=title,
        welcome_text=text,
        chat_available=chat_available,
    )


@router.get("/knowledge-base", response_model=KnowledgeBaseResponse)
def get_public_knowledge_base(db: Session = Depends(get_db)) -> Any:
    """Return the main (public) knowledge base with its documents."""
    kb = (
        db.query(KnowledgeBase)
        .options(
            joinedload(KnowledgeBase.documents).joinedload(Document.processing_tasks)
        )
        .filter(KnowledgeBase.id == _get_public_kb(db).id)
        .first()
    )
    return kb


@router.get(
    "/knowledge-base/documents",
    response_model=List[DocumentResponse],
)
def list_public_documents(db: Session = Depends(get_db)) -> Any:
    """List the documents belonging to the main (public) knowledge base."""
    kb = _get_public_kb(db)
    documents = (
        db.query(Document)
        .filter(Document.knowledge_base_id == kb.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return documents


@router.get(
    "/knowledge-base/documents/{document_id}",
    response_model=DocumentResponse,
)
def get_public_document(
    *,
    db: Session = Depends(get_db),
    document_id: int,
) -> Any:
    """Fetch a single document from the main (public) knowledge base."""
    kb = _get_public_kb(db)
    document = (
        db.query(Document)
        .filter(
            Document.knowledge_base_id == kb.id,
            Document.id == document_id,
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/knowledge-base/documents/{document_id}/chunks")
def get_public_document_chunks(
    *,
    db: Session = Depends(get_db),
    document_id: int,
) -> Any:
    """Return read-only chunks for a document in the main public knowledge base."""
    kb = _get_public_kb(db)
    document = (
        db.query(Document)
        .filter(
            Document.knowledge_base_id == kb.id,
            Document.id == document_id,
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
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_type == "term",
            )
            .all()
        )
    else:
        chunks = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_type == "work",
            )
            .all()
        )
        if not chunks:
            chunks = (
                db.query(DocumentChunk)
                .filter(
                    DocumentChunk.document_id == document_id,
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
