"""`board_scans` gains `listing_runs`: how many newest-first date runs a full listing was (D-710).

T340's recommended option 1 (not yet ruled) lists a board in full when its last full listing had
2+ date runs, because the head scan stops in the first run's old tail and never reaches the next
run's fresh rows (R-063: 290 such rows on 15 Workday boards in run 2904's shadow).

Additive: one nullable column, no default, no rebuild, no backfill. NULL means the provider does
not compute it, the listing was split, or the row predates the column. Retry-safe and downgraded
with native DROP COLUMN, as `p_head_shadow`.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_listing_runs"
down_revision = "p_http_cache_gate_key"
branch_labels = None
depends_on = None


def _present() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("board_scans")}


def upgrade() -> None:
    if "listing_runs" not in _present():
        op.execute("ALTER TABLE board_scans ADD COLUMN listing_runs INTEGER")


def downgrade() -> None:
    if "listing_runs" in _present():
        op.execute("ALTER TABLE board_scans DROP COLUMN listing_runs")
