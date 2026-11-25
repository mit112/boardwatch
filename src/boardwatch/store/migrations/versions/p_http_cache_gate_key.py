"""`http_cache` gains `gate_key`: the listing gate a stored validator was learned under (T355).

A provider that gates listings discards the rows its gate rejects unstored, then persists the
board's ETag. A later scan under another gate would send that ETag, get a 304 and never show the
new gate the rows the old one rejected. The key binds the validator to its gate.

Additive: one nullable column, no default, no rebuild, no backfill. NULL means the row predates
the column, and a gating provider never reuses it: one full read, after which it is rewritten with
its key. ALTER TABLE ADD COLUMN is not idempotent in SQLite, so a retry checks the table first.
Downgrade uses native DROP COLUMN (SQLite >= 3.35), the p_head_shadow precedent.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_http_cache_gate_key"
down_revision = "p_scan_manifests"
branch_labels = None
depends_on = None


def _present() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("http_cache")}


def upgrade() -> None:
    if "gate_key" not in _present():
        op.execute("ALTER TABLE http_cache ADD COLUMN gate_key TEXT")


def downgrade() -> None:
    if "gate_key" in _present():
        op.execute("ALTER TABLE http_cache DROP COLUMN gate_key")
