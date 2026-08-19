"""D-246: the operator's target seniority band on the profile singleton.

One additive column with a server default of `any`, which makes the seniority gate INERT for
every existing install — the gate reports itself inert rather than changing any behaviour until
the operator narrows the band. ALTER TABLE ADD COLUMN with no table rebuild; downgrade uses
native DROP COLUMN (SQLite >= 3.35), the path p1_resume_max_pages takes.

Unlike resume_max_pages this DOES enter the ranker's profile_row_hash: it drives a funnel drop
bucket, so a run manifest that omitted it would claim two runs identical when the setting
driving the drop changed.
"""

from alembic import op

revision = "p_seniority_band"
down_revision = "runs_status_backfill_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE profile ADD COLUMN target_seniority_band TEXT NOT NULL DEFAULT 'any'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE profile DROP COLUMN target_seniority_band")
