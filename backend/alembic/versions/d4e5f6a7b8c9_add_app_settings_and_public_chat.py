"""add app settings and public chat

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-04-14 23:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create app settings and public chat support."""
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_kb_id", sa.Integer(), nullable=True),
        sa.Column("chat_provider", sa.String(length=50), nullable=True),
        sa.Column("chat_model", sa.String(length=255), nullable=True),
        sa.Column("welcome_title", sa.String(length=255), nullable=True),
        sa.Column("welcome_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["public_kb_id"],
            ["knowledge_bases.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_app_settings_id"), "app_settings", ["id"], unique=False)

    op.add_column(
        "chats",
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("chats", "user_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("chats", "is_public", server_default=None)


def downgrade() -> None:
    """Remove app settings and public chat support."""
    op.alter_column("chats", "user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("chats", "is_public")

    op.drop_index(op.f("ix_app_settings_id"), table_name="app_settings")
    op.drop_table("app_settings")
