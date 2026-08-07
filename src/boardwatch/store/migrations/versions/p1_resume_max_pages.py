"""P1a: résumé page-count limit on the profile singleton.

One additive nullable-safe column with a server default of 1 (new-grad), ALTER TABLE ADD COLUMN
with no table rebuild. Downgrade uses native DROP COLUMN (SQLite >= 3.35), the path
p2_profile_eligibility takes. Kept OUT of the ranker's profile_row_hash — a render knob, not a
ranking input.
"""
from alembic import op

revision = "p1_resume_max_pages"
down_revision = "p0_run_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE profile ADD COLUMN resume_max_pages INTEGER NOT NULL DEFAULT 1")


def downgrade() -> None:
    op.execute("ALTER TABLE profile DROP COLUMN resume_max_pages")
