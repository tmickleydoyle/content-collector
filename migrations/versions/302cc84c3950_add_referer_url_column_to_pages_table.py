"""Add referer_url column to pages table

Revision ID: 302cc84c3950
Revises:
Create Date: 2025-06-22 06:58:08.905120

"""

import sqlalchemy as sa
from alembic import op

revision = "302cc84c3950"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("referer_url", sa.String(), nullable=True))
    op.create_index(
        op.f("ix_pages_referer_url"), "pages", ["referer_url"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pages_referer_url"), table_name="pages")
    op.drop_column("pages", "referer_url")
