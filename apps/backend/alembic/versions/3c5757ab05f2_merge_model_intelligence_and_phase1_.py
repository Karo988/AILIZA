"""merge model_intelligence and phase1 customer branches

Revision ID: 3c5757ab05f2
Revises: b7e4d92c1a63, f3c9a1e7d2b4
Create Date: 2026-08-12 15:18:49.378258

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c5757ab05f2'
down_revision: Union[str, None] = ('b7e4d92c1a63', 'f3c9a1e7d2b4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
