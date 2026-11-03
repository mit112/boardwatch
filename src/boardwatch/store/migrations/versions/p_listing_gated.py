"""D-663: how many of a board's listed postings the listing gate ruled out in that scan.

Additive, so it costs nothing on a store of any size. NULL on every scan before this one and on a
failed board, the same way `detail_deferred` reads: not measured rather than none.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_listing_gated"
down_revision = "p_corpus_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("board_scans", recreate="never") as batch:
        batch.add_column(sa.Column("listing_gated", sa.Integer, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("board_scans", recreate="never") as batch:
        batch.drop_column("listing_gated")
