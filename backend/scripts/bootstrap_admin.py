"""Create or update the initial admin user."""

import argparse

from app.services.admin_bootstrap import upsert_admin_user


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
    action = upsert_admin_user(
        username=args.username,
        email=args.email,
        password=args.password,
    )
    print(f"Admin user {action}: {args.username}")


if __name__ == "__main__":
    main()
