"""Index board_scans by (status, company_id), so "ever completed a scan" reads an index.

`delivery_queries._board_ever_complete` is `SELECT company_id FROM board_scans WHERE
status = 'complete' GROUP BY company_id`. The queue refresh runs it once per lead. With no index on
`status` it scans the whole table into a temporary B-tree: 91.8 s of the 94 s of SQL in one
refresh of a store with 476,261 scan rows. As a covering index search the refresh took 49 s
instead of 114 s, with the same result.

Additive: one index, no table rebuild, no backfill. Idempotent, because the build takes seconds
and a run killed part-way must be able to retry rather than fail on "already exists".
"""

from alembic import op

revision = "p_board_scans_status_index"
down_revision = "p_apply_destinations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_board_scans_status_company "
        "ON board_scans (status, company_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_board_scans_status_company")
