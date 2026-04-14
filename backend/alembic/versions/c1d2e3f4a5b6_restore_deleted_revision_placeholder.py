"""restore deleted revision placeholder

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-04-14 22:45:00.000000

"""

from typing import Sequence, Union

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Restore the deleted revision reference without applying schema changes."""


def downgrade() -> None:
    """No-op downgrade for the restored placeholder revision."""
