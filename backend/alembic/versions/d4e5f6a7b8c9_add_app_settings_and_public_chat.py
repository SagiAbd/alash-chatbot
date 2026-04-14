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


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    """Return whether the given table already exists."""
    return table_name in inspector.get_table_names()


def _has_column(
    inspector: sa.Inspector, table_name: str, column_name: str
) -> bool:
    """Return whether the given column already exists on a table."""
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name)
    )


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    """Return whether the given index already exists on a table."""
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    """Create app settings and public chat support."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "app_settings"):
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
        inspector = sa.inspect(bind)

    if not _has_index(inspector, "app_settings", op.f("ix_app_settings_id")):
        op.create_index(
            op.f("ix_app_settings_id"),
            "app_settings",
            ["id"],
            unique=False,
        )
        inspector = sa.inspect(bind)

    if not _has_column(inspector, "chats", "is_public"):
        op.add_column(
            "chats",
            sa.Column(
                "is_public",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        inspector = sa.inspect(bind)

    op.alter_column("chats", "user_id", existing_type=sa.Integer(), nullable=True)
    if _has_column(inspector, "chats", "is_public"):
        op.alter_column("chats", "is_public", server_default=None)


def downgrade() -> None:
    """Remove app settings and public chat support."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "chats", "is_public"):
        op.drop_column("chats", "is_public")
        inspector = sa.inspect(bind)

    op.alter_column("chats", "user_id", existing_type=sa.Integer(), nullable=False)

    if _has_table(inspector, "app_settings"):
        if _has_index(inspector, "app_settings", op.f("ix_app_settings_id")):
            op.drop_index(op.f("ix_app_settings_id"), table_name="app_settings")
        op.drop_table("app_settings")
