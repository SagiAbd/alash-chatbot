"""Create or update the initial admin user."""

import argparse

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.user import User


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for admin bootstrap."""
    parser = argparse.ArgumentParser(
        description="Create or update an admin user for the Alash chatbot."
    )
    parser.add_argument("--username", required=True, help="Admin username")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Admin password")
    return parser.parse_args()


def main() -> None:
    """Create or update the requested admin user."""
    args = parse_args()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            user = User(
                username=args.username,
                email=args.email,
                hashed_password=get_password_hash(args.password),
                is_active=True,
                is_superuser=True,
            )
            db.add(user)
            action = "created"
        else:
            user.email = args.email
            user.hashed_password = get_password_hash(args.password)
            user.is_active = True
            user.is_superuser = True
            db.add(user)
            action = "updated"

        db.commit()
        print(f"Admin user {action}: {user.username}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
