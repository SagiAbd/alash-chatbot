from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class MessageBase(BaseModel):
    content: str
    role: str


class MessageCreate(MessageBase):
    chat_id: int


class MessageResponse(MessageBase):
    id: int
    chat_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatBase(BaseModel):
    title: str


class ChatCreate(ChatBase):
    knowledge_base_ids: List[int]


class ChatUpdate(ChatBase):
    knowledge_base_ids: Optional[List[int]] = None


class ChatResponse(ChatBase):
    id: int
    user_id: Optional[int] = None
    is_public: bool = False
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []
    knowledge_base_ids: List[int] = []

    class Config:
        from_attributes = True
