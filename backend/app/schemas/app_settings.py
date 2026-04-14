from pydantic import BaseModel


class AppSettingsResponse(BaseModel):
    public_kb_id: int | None
    chat_provider: str
    chat_model: str | None
    welcome_title: str
    welcome_text: str


class AppSettingsUpdate(BaseModel):
    public_kb_id: int | None = None
    chat_provider: str
    chat_model: str | None = None
    welcome_title: str
    welcome_text: str


class PublicConfigResponse(BaseModel):
    welcome_title: str
    welcome_text: str
    chat_available: bool
