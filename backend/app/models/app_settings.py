from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class AppSettings(Base, TimestampMixin):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True, default=1)
    public_kb_id = Column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
    )
    chat_provider = Column(String(50), nullable=True)
    chat_model = Column(String(255), nullable=True)
    welcome_title = Column(String(255), nullable=True)
    welcome_text = Column(Text, nullable=True)

    public_kb = relationship("KnowledgeBase", foreign_keys=[public_kb_id])
