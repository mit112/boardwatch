"""T199: a lane's `board_scans` row names the lane that wrote it.

`count_lane_captures` attributed the store's captured companies to lanes by ADMISSION alone,
because `board_scans` recorded no lane name — so a company two lanes admitted and only one
landed was credited to both (run 475, `ashby:evenup`: hiring.cafe read 10 against a true 9).
One additive nullable column. NULL is meaningful and is not a lane: every `scan_kind='board'`
row, and every lane row written before this migration, for which the recount falls back to
admission-only attribution and says so. ALTER TABLE ADD COLUMN with no table rebuild: the
column is nullable and carries no CHECK, so nothing needs one. Downgrade uses native DROP
COLUMN (SQLite >= 3.35), the path p_runs_corpus_counts takes.
"""

from alembic import op

revision = "p_board_scans_lane"
down_revision = "p_target_countries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE board_scans ADD COLUMN lane TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE board_scans DROP COLUMN lane")
