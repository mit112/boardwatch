"""Keep verified application destinations separate from source observations."""

import sqlalchemy as sa
from alembic import op

revision = "p_apply_destinations"
down_revision = "p_runs_incremental"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_destinations",
        sa.Column("posting_id", sa.Integer, sa.ForeignKey("postings.id"), primary_key=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("evidence_ref", sa.Text, nullable=False),
        sa.Column("verified_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("application_destinations")
