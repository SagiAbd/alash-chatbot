from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.db.session import get_db
from app.models.knowledge import KnowledgeBase
from app.models.user import User
from app.schemas.app_settings import AppSettingsResponse, AppSettingsUpdate
from app.services.app_settings import (
    SUPPORTED_CHAT_PROVIDERS,
    default_welcome_text,
    default_welcome_title,
    get_or_create_app_settings,
)
from app.services.llm.llm_factory import LLMFactory

router = APIRouter()


def _serialize_settings(db: Session) -> AppSettingsResponse:
    app_settings = get_or_create_app_settings(db)
    provider = (app_settings.chat_provider or "openai").lower()
    model = app_settings.chat_model or LLMFactory.default_model_for_provider(provider)
    return AppSettingsResponse(
        public_kb_id=app_settings.public_kb_id,
        chat_provider=provider,
        chat_model=model,
        welcome_title=app_settings.welcome_title or default_welcome_title(),
        welcome_text=app_settings.welcome_text or default_welcome_text(),
    )


@router.get("", response_model=AppSettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> Any:
    del current_user
    return _serialize_settings(db)


@router.put("", response_model=AppSettingsResponse)
def update_settings(
    *,
    db: Session = Depends(get_db),
    settings_in: AppSettingsUpdate,
    current_user: User = Depends(get_current_admin),
) -> Any:
    del current_user
    provider = settings_in.chat_provider.lower()
    if provider not in SUPPORTED_CHAT_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported chat provider")

    if settings_in.public_kb_id is not None:
        kb = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.id == settings_in.public_kb_id)
            .first()
        )
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

    app_settings = get_or_create_app_settings(db)
    app_settings.public_kb_id = settings_in.public_kb_id
    app_settings.chat_provider = provider
    app_settings.chat_model = settings_in.chat_model or None
    app_settings.welcome_title = settings_in.welcome_title.strip()
    app_settings.welcome_text = settings_in.welcome_text.strip()
    db.add(app_settings)
    db.commit()
    db.refresh(app_settings)
    return _serialize_settings(db)
