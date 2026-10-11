"""briefings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09 14:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "briefings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=300), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_action", sa.Text(), nullable=True),
        sa.Column("current_url", sa.Text(), nullable=True),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("shots", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_briefings_org_id"), "briefings", ["org_id"], unique=False)
    op.create_index(op.f("ix_briefings_created_by"), "briefings", ["created_by"], unique=False)
    op.create_index(op.f("ix_briefings_status"), "briefings", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_briefings_status"), table_name="briefings")
    op.drop_index(op.f("ix_briefings_created_by"), table_name="briefings")
    op.drop_index(op.f("ix_briefings_org_id"), table_name="briefings")
    op.drop_table("briefings")
