"""briefing sign-in

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09 22:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("briefings", sa.Column("login_url", sa.Text(), nullable=True))
    op.add_column("briefings", sa.Column("credential_ciphertext", sa.LargeBinary(), nullable=True))
    op.add_column("briefings", sa.Column("credential_hint", sa.String(length=160), nullable=True))
    op.add_column("briefings", sa.Column("auth_status", sa.String(length=32), server_default="not_requested", nullable=False))
    op.add_column("briefings", sa.Column("auth_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in ("auth_detail", "auth_status", "credential_hint", "credential_ciphertext", "login_url"):
        op.drop_column("briefings", col)
