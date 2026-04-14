import logging

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)


def upsert_admin_user(username: str, email: str, password: str) -> str:
    """Create or update an admin user in the database."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            user = User(
                username=username,
                email=email,
                hashed_password=get_password_hash(password),
                is_active=True,
                is_superuser=True,
            )
            db.add(user)
            action = "created"
        else:
            user.email = email
            user.hashed_password = get_password_hash(password)
            user.is_active = True
            user.is_superuser = True
            db.add(user)
            action = "updated"

        db.commit()
        return action
    finally:
        db.close()


def bootstrap_admin_from_env() -> str | None:
    """Create or update the admin user from env vars when configured."""
    username = settings.ADMIN_USERNAME.strip()
    email = settings.ADMIN_EMAIL.strip()
    password = settings.ADMIN_PASSWORD

    if not username and not email and not password:
        return None

    if not username or not email or not password:
        logger.warning(
            "Admin bootstrap skipped because ADMIN_USERNAME, ADMIN_EMAIL, or "
            "ADMIN_PASSWORD is missing"
        )
        return "skipped"

    action = upsert_admin_user(username=username, email=email, password=password)
    logger.info("Admin bootstrap %s for username=%s", action, username)
    return action
