"""Per-user personal knowledge base helpers."""

from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeBase
from app.models.user import User


def ensure_personal_kb(db: Session, user: User) -> KnowledgeBase:
    """Return the user's personal knowledge base, creating it if missing."""
    kb = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == user.id,
            KnowledgeBase.is_personal.is_(True),
        )
        .first()
    )
    if kb is not None:
        return kb

    kb = KnowledgeBase(
        name=f"{user.username}'s library",
        description="Personal uploaded documents.",
        user_id=user.id,
        is_personal=True,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


def get_personal_kb(db: Session, user: User) -> KnowledgeBase | None:
    """Return the user's personal knowledge base without creating it."""
    return (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == user.id,
            KnowledgeBase.is_personal.is_(True),
        )
        .first()
    )
