"""`scan_manifests`: what each scan was asked to do, and whether it reached its counts (T353).

One row per scan run, written beside `insert_run`: the boards to dispatch, the filters, the
listing gate's key, the scan settings and a digest of the scan code. `finalize_run` stamps
`scan_finalized_at`. `run --continue-scan` resumes only a run whose manifest matches the retry's
own and whose scan was never finalized.

Additive: one CREATE TABLE with one FK to `runs`, nothing referencing it, no backfill. A run from
before this table has no manifest and so can never be resumed, which is the safe direction.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_scan_manifests"
down_revision = "p_head_shadow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_manifests",
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("scan_finalized_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_scan_manifests")),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_scan_manifests_run_id_runs")
        ),
    )


def downgrade() -> None:
    op.drop_table("scan_manifests")
