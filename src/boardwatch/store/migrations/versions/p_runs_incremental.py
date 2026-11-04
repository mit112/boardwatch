"""D-670: keep scoped scans and fresh delivery out of nightly history windows."""

import sqlalchemy as sa
from alembic import op

revision = "p_runs_incremental"
down_revision = "p_dead_boards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("incremental", sa.Boolean, nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("runs", "incremental")
