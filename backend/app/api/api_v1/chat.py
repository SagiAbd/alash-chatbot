"""Unified chat API — serves guests, regular users, and admins."""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user, get_current_user_optional
from app.db.session import get_db
from app.models.chat import Chat
from app.models.knowledge import KnowledgeBase
from app.models.user import User
from app.schemas.chat import ChatResponse
from app.services.app_settings import get_or_create_app_settings
from app.services.chat_service import generate_response
from app.services.personal_library import get_personal_kb

router = APIRouter()


def _resolve_public_kb(db: Session) -> KnowledgeBase:
    """Return the configured main knowledge base or raise 409."""
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
    if kb is None:
        raise HTTPException(
            status_code=409,
            detail="Configured public chatbot knowledge base was not found",
        )
    return kb


def _knowledge_bases_for_user(
    db: Session, user: Optional[User]
) -> List[KnowledgeBase]:
    """Return the KB mix that should back a new chat for the given caller.

    Guests and regular users chat against the main KB plus (if logged in) their
    own personal library. Admins get the same default; they can still manage
    KBs through the admin endpoints.
    """
    public_kb = _resolve_public_kb(db)
    knowledge_bases: List[KnowledgeBase] = [public_kb]
    if user is not None:
        personal_kb = get_personal_kb(db, user)
        if personal_kb is not None and personal_kb.id != public_kb.id:
            knowledge_bases.append(personal_kb)
    return knowledge_bases


def _load_owned_chat(db: Session, chat_id: int, user: Optional[User]) -> Chat:
    """Fetch a chat record the caller is allowed to read/write."""
    chat = (
        db.query(Chat)
        .options(joinedload(Chat.knowledge_bases))
        .filter(Chat.id == chat_id)
        .first()
    )
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    if user is None:
        if not chat.is_public or chat.user_id is not None:
            raise HTTPException(status_code=404, detail="Chat not found")
        return chat

    if chat.user_id is None:
        if chat.is_public:
            return chat
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


def _to_chat_response(chat: Chat) -> dict[str, Any]:
    """Serialise a Chat row into the shape expected by the frontend."""
    return {
        "id": chat.id,
        "title": chat.title,
        "user_id": chat.user_id,
        "is_public": chat.is_public,
        "created_at": chat.created_at,
        "updated_at": chat.updated_at,
        "messages": chat.messages,
        "knowledge_base_ids": [kb.id for kb in chat.knowledge_bases],
    }


@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
def create_chat(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> Any:
    """Create a new chat for the caller (guest or authenticated)."""
    knowledge_bases = _knowledge_bases_for_user(db, current_user)
    chat = Chat(
        title="Жаңа сұхбат",
        user_id=current_user.id if current_user else None,
        is_public=current_user is None,
    )
    chat.knowledge_bases = knowledge_bases
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return _to_chat_response(chat)


@router.get("", response_model=List[ChatResponse])
@router.get("/", response_model=List[ChatResponse])
def list_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """List the authenticated user's chat history (sidebar)."""
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == current_user.id)
        .order_by(Chat.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_chat_response(chat) for chat in chats]


@router.get("/{chat_id}", response_model=ChatResponse)
def get_chat(
    *,
    db: Session = Depends(get_db),
    chat_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> Any:
    chat = _load_owned_chat(db, chat_id, current_user)
    return _to_chat_response(chat)


@router.post("/{chat_id}/messages")
async def create_message(
    *,
    db: Session = Depends(get_db),
    chat_id: int,
    messages: dict,
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> StreamingResponse:
    chat = _load_owned_chat(db, chat_id, current_user)

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


@router.delete("/{chat_id}")
def delete_chat(
    *,
    db: Session = Depends(get_db),
    chat_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """Delete a chat owned by the authenticated caller."""
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.user_id == current_user.id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    db.delete(chat)
    db.commit()
    return {"status": "success"}
