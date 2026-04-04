"""add chunk fields for page retrieval

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-04-04 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add first-class chunk fields for work/page retrieval."""
    op.add_column(
        "document_chunks", sa.Column("chunk_type", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "document_chunks",
        sa.Column("chunk_label", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "document_chunks", sa.Column("page_number", sa.Integer(), nullable=True)
    )
    op.add_column(
        "document_chunks", sa.Column("start_page", sa.Integer(), nullable=True)
    )
    op.add_column("document_chunks", sa.Column("end_page", sa.Integer(), nullable=True))

    op.create_index(
        op.f("ix_document_chunks_chunk_type"),
        "document_chunks",
        ["chunk_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_chunks_page_number"),
        "document_chunks",
        ["page_number"],
        unique=False,
    )
    op.create_index(
        "idx_document_chunk_type",
        "document_chunks",
        ["document_id", "chunk_type"],
        unique=False,
    )
    op.create_index(
        "idx_document_page_number",
        "document_chunks",
        ["document_id", "page_number"],
        unique=False,
    )

    op.execute(
        """
        UPDATE document_chunks
        SET
            chunk_type = 'work',
            chunk_label = JSON_UNQUOTE(JSON_EXTRACT(chunk_metadata, '$.work_title')),
            start_page = CAST(
                NULLIF(JSON_UNQUOTE(JSON_EXTRACT(chunk_metadata, '$.start_page')), '')
                AS SIGNED
            ),
            end_page = CAST(
                NULLIF(JSON_UNQUOTE(JSON_EXTRACT(chunk_metadata, '$.end_page')), '')
                AS SIGNED
            )
        WHERE chunk_type IS NULL
        """
    )


def downgrade() -> None:
    """Remove first-class chunk fields for work/page retrieval."""
    op.drop_index("idx_document_page_number", table_name="document_chunks")
    op.drop_index("idx_document_chunk_type", table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_page_number"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_chunk_type"), table_name="document_chunks")
    op.drop_column("document_chunks", "end_page")
    op.drop_column("document_chunks", "start_page")
    op.drop_column("document_chunks", "page_number")
    op.drop_column("document_chunks", "chunk_label")
    op.drop_column("document_chunks", "chunk_type")
