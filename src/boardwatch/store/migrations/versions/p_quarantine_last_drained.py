"""`quarantined_bodies` gains `last_drained_at`, so a re-held body keeps its drain (T319).

`record_quarantine` clears `reopened_at` when a drained body is quarantined again, and every
reader treats `reopened_at IS NULL` as "held". The drain therefore vanished from the store, and
the store-hygiene panel could report a stalled drain that had in fact run. This column keeps the
most recent drain of such a body; `reopened_at` keeps its meaning.

Additive: one nullable column, no default, no rebuild, no backfill. NULL means "never re-held
after a drain", which is true of every existing row. ALTER TABLE ADD COLUMN is not idempotent in
SQLite, so a retry after a half-applied run is guarded by checking the table first. Downgrade
uses native DROP COLUMN (SQLite >= 3.35), the run_attribution precedent.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_quarantine_last_drained"
down_revision = "p_board_scans_status_index"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    cols = sa.inspect(op.get_bind()).get_columns("quarantined_bodies")
    return any(c["name"] == "last_drained_at" for c in cols)


def upgrade() -> None:
    if not _has_column():
        op.execute("ALTER TABLE quarantined_bodies ADD COLUMN last_drained_at DATETIME")


def downgrade() -> None:
    if _has_column():
        op.execute("ALTER TABLE quarantined_bodies DROP COLUMN last_drained_at")
