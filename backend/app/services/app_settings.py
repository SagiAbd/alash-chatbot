from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.app_settings import AppSettings

SUPPORTED_CHAT_PROVIDERS = {"openai", "deepseek", "openrouter"}


def default_welcome_title() -> str:
    """Return the default public welcome title."""
    return settings.PUBLIC_WELCOME_TITLE


def default_welcome_text() -> str:
    """Return the default public welcome text."""
    return settings.PUBLIC_WELCOME_TEXT


def get_or_create_app_settings(db: Session) -> AppSettings:
    """Return the singleton app settings row, creating it if missing."""
    app_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if app_settings:
        return app_settings

    app_settings = AppSettings(
        id=1,
        chat_provider=settings.CHAT_PROVIDER,
        welcome_title=default_welcome_title(),
        welcome_text=default_welcome_text(),
    )
    db.add(app_settings)
    db.commit()
    db.refresh(app_settings)
    return app_settings


def get_runtime_chat_provider_model(db: Session) -> tuple[str, str | None]:
    """Resolve provider/model from DB-backed settings with env fallback."""
    app_settings = get_or_create_app_settings(db)
    provider = (app_settings.chat_provider or settings.CHAT_PROVIDER).lower()
    model = app_settings.chat_model or None
    return provider, model


def get_public_welcome_content(db: Session) -> tuple[str, str]:
    """Return public welcome content with defaults when unset."""
    app_settings = get_or_create_app_settings(db)
    title = app_settings.welcome_title or default_welcome_title()
    text = app_settings.welcome_text or default_welcome_text()
    return title, text
