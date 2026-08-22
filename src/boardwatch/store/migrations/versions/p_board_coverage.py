"""D-271: per-board coverage numbers the scan already computes and threw away.

Four additive nullable columns. NULL is meaningful and is not zero: it means the board stated
no total (lever/ashby/workable have no count field at all), or the row predates this migration.
A zero default would make every historic row read as a board with nothing on it.

ALTER TABLE ADD COLUMN with no table rebuild; downgrade uses native DROP COLUMN (SQLite >= 3.35),
the path p_seniority_band takes.

These do NOT enter the run manifest hash — they are observations about a scan, not inputs to a
verdict. Contrast detail_fetch_budget, which is currently classified "throughput" in
reports/manifest.py and arguably should not be; that is a separate decision.
"""

from alembic import op

revision = "p_board_coverage"
down_revision = "p_seniority_band"
branch_labels = None
depends_on = None

# board_total_censored is 0/1, or NULL when the provider states no total. It is a TYPED flag
# because the alternative — grepping the error string — would classify behaviour by parsing a
# message, which this repo forbids.
_COLUMNS = (
    "board_reported_total", "board_enumerated", "detail_deferred", "board_total_censored",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.execute(f"ALTER TABLE board_scans ADD COLUMN {name} INTEGER")


def downgrade() -> None:
    for name in _COLUMNS:
        op.execute(f"ALTER TABLE board_scans DROP COLUMN {name}")
