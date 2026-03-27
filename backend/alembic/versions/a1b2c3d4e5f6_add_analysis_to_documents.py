"""add_analysis_to_documents

Revision ID: a1b2c3d4e5f6
Revises: 3580c0dcd005
Create Date: 2026-03-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "3580c0dcd005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("analysis", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "analysis")
