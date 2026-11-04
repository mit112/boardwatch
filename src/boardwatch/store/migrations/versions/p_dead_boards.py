"""D-669: typed dead-board evidence and pipeline scan provenance.

Old rows remain unclassified. Never backfill evidence from an error message or doctor health.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_dead_boards"
down_revision = "p_listing_gated"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("board_scans", recreate="never") as batch:
        batch.add_column(sa.Column("dead", sa.Boolean, nullable=False, server_default="0"))
        batch.add_column(sa.Column("pipeline_scan", sa.Boolean, nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("board_scans", recreate="never") as batch:
        batch.drop_column("pipeline_scan")
        batch.drop_column("dead")
