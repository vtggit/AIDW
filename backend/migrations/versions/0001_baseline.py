"""Baseline schema for AIDW — audit_log only (a clean warehouse-infra skeleton).

The warehouse domain (sources, datasets, pipelines, runs) is grown by CodeAgent from here.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_sub", sa.String(200), nullable=False),
        sa.Column("actor_username", sa.String(200), nullable=True),
        sa.Column("actor_email", sa.String(300), nullable=True),
        sa.Column("actor_roles", sa.Text(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("details_json", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
