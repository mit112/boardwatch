"""`board_scans` gains T340's shadow: `listing_pages`, `head_pages`, `head_missed`.

A paged newest-first provider records, on every full listing, how many pages it requested, how
many a head scan would have read, and how many rows it detail-fetched from the pages a head scan
would have skipped. A week of these rows is T340's acceptance before the head scan is armed.

Additive: three nullable columns, no default, no rebuild, no backfill. NULL means the provider
does not compute it or the row predates the column. ALTER TABLE ADD COLUMN is not idempotent in
SQLite, so a retry after a half-applied run checks the table first. Downgrade uses native
DROP COLUMN (SQLite >= 3.35), the p_empty_guarded precedent.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_head_shadow"
down_revision = "p_empty_guarded"
branch_labels = None
depends_on = None

_COLUMNS = ("listing_pages", "head_pages", "head_missed")


def _present() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("board_scans")}


def upgrade() -> None:
    present = _present()
    for name in _COLUMNS:
        if name not in present:
            op.execute(f"ALTER TABLE board_scans ADD COLUMN {name} INTEGER")


def downgrade() -> None:
    present = _present()
    for name in _COLUMNS:
        if name in present:
            op.execute(f"ALTER TABLE board_scans DROP COLUMN {name}")
