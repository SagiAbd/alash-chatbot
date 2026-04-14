from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.chat import Chat
from app.models.knowledge import KnowledgeBase
from app.schemas.app_settings import PublicConfigResponse
from app.services.app_settings import (
    get_or_create_app_settings,
    get_public_welcome_content,
)
from app.services.chat_service import generate_response

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


@router.post("/chat")
def create_public_chat(db: Session = Depends(get_db)) -> Any:
    kb = _get_public_kb(db)
    chat = Chat(
        title="Public Chat",
        user_id=None,
        is_public=True,
    )
    chat.knowledge_bases = [kb]
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return {"id": chat.id}


@router.post("/chat/{chat_id}/messages")
async def create_public_message(
    *,
    db: Session = Depends(get_db),
    chat_id: int,
    messages: dict,
) -> StreamingResponse:
    chat = (
        db.query(Chat)
        .options(joinedload(Chat.knowledge_bases))
        .filter(Chat.id == chat_id, Chat.is_public.is_(True))
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    last_message = messages["messages"][-1]
    if last_message["role"] != "user":
        raise HTTPException(status_code=400, detail="Last message must be from user")

    knowledge_base_ids = [kb.id for kb in chat.knowledge_bases]

    async def response_stream():
        async for chunk in generate_response(
            query=last_message["content"],
            messages=messages,
            knowledge_base_ids=knowledge_base_ids,
            chat_id=chat_id,
            db=db,
        ):
            yield chunk

    return StreamingResponse(
        response_stream(),
        media_type="text/event-stream",
        headers={"x-vercel-ai-data-stream": "v1"},
    )
