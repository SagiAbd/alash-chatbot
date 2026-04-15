"""add guest token to chats

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-04-15 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("guest_token", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_chats_guest_token"), "chats", ["guest_token"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chats_guest_token"), table_name="chats")
    op.drop_column("chats", "guest_token")
