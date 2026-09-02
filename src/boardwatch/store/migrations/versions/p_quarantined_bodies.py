"""The lane-body quarantine: bodies that are an aggregator's page text, not the employer's.

D-406 measured job-apps' jobright records storing jobright's rendered PAGE — the page title,
the site nav, and jobright's OWN derived label `H1B Sponsor Likely` — inside what boardwatch
then freezes as the JD. `work_auth` is a blocker family and `INELIGIBLE` must carry a quoted
span from the frozen JD, so an `ineligible(work_auth)` quoting that label would present a third
party's guess as the employer's stated requirement.

One row per QUARANTINED posting version. Nothing sweeps this table and nothing deletes from it,
including the drain, which sets `reopened_at` — the same shape `p6_job_dispositions` chose, for
the same reason: draining a bucket must not erase the record that it ever held anything.

Creates the table only. It deliberately does not backfill: the detector is Python, a migration
is a historical record that must not import a live catalog, and the bucket fills itself on the
first `run_eligibility` after this ships — which is the same pass that would otherwise have fed
those bodies to the rules.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_quarantined_bodies"
down_revision = "p_lane_seeds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quarantined_bodies",
        sa.Column("posting_version_id", sa.Integer(), nullable=False),
        sa.Column("posting_id", sa.Integer(), nullable=False),
        sa.Column("markers_json", sa.JSON(), nullable=False),
        sa.Column("catalog_version", sa.Integer(), nullable=False),
        sa.Column("quarantined_at", sa.DateTime(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("reopened_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("posting_version_id", name=op.f("pk_quarantined_bodies")),
        sa.ForeignKeyConstraint(
            ["posting_version_id"],
            ["posting_versions.id"],
            name=op.f("fk_quarantined_bodies_posting_version_id_posting_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["posting_id"], ["postings.id"], name=op.f("fk_quarantined_bodies_posting_id_postings")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_quarantined_bodies_run_id_runs")
        ),
    )
    op.create_index(
        "ix_quarantined_bodies_reopened_at", "quarantined_bodies", ["reopened_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_quarantined_bodies_reopened_at", table_name="quarantined_bodies")
    op.drop_table("quarantined_bodies")
