"""`board_scans` gains the typed `empty_guarded`, so a guarded scan is a recorded fact (T334).

The empty-complete guard refuses a `complete` snapshot with no postings and no `listed_ids` as
evidence of closure, and until now left no trace of having fired on the scan row: the only
record was the run log and the funnel artifact. `postings_listed = 0` cannot stand in for it, it
matches 1,224 watched boards fleet-wide against the 73 the guard fired on, because a
multi-request provider writes 0 whenever every id is already known. The death-probe drain
(D-705) needs "how many consecutive pipeline scans were guarded" for one board, so the guard's
own site now writes it.

Additive: one nullable column, no default, no rebuild, no backfill. NULL means "written before
this column existed", which is true of every existing row and is deliberately NOT evidence of a
guarded scan; nothing is inferred from the old rows, so a board's guarded streak starts with its
first guarded scan after this migration. ALTER TABLE ADD COLUMN is not idempotent in SQLite, so
a retry after a half-applied run is guarded by checking the table first. Downgrade uses native
DROP COLUMN (SQLite >= 3.35), the p_quarantine_last_drained precedent.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_empty_guarded"
down_revision = "p_quarantine_last_drained"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    cols = sa.inspect(op.get_bind()).get_columns("board_scans")
    return any(c["name"] == "empty_guarded" for c in cols)


def upgrade() -> None:
    if not _has_column():
        op.execute("ALTER TABLE board_scans ADD COLUMN empty_guarded BOOLEAN")


def downgrade() -> None:
    if _has_column():
        op.execute("ALTER TABLE board_scans DROP COLUMN empty_guarded")
