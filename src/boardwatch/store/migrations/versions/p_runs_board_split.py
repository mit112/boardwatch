"""D-341's other half: the runs row keeps ScanSummary's full four-way board split.

The funnel artifact publishes complete/partial/unchanged/failed, but the `runs` table stored
only `boards_attempted` and `boards_complete`, so `/api/runs` and the web run list inherited the
same fold — run 127 read "346 attempted / 145 complete" with the other 200 boards unaccounted.

Three additive nullable columns. NULL is meaningful and is not zero: it means the row predates
this migration, or a run whose scan never populated a ScanSummary. A zero default would make
every historic run read as a scan that found zero partial, unchanged and failed boards.

ALTER TABLE ADD COLUMN with no table rebuild — never batch_alter_table on `runs`, which six
tables reference by FK (the caveat p0_run_status records). Downgrade uses native DROP COLUMN
(SQLite >= 3.35), the path p_death_probe and p_board_coverage take.

These do NOT enter the run manifest hash — they are observations about a scan, not inputs to a
verdict (the precedent p_board_coverage states for the same reason).
"""

from alembic import op

revision = "p_runs_board_split"
down_revision = "p_death_probe"
branch_labels = None
depends_on = None

_COLUMNS = ("boards_partial", "boards_unchanged", "boards_failed")


def upgrade() -> None:
    for name in _COLUMNS:
        op.execute(f"ALTER TABLE runs ADD COLUMN {name} INTEGER")


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE runs DROP COLUMN {name}")
