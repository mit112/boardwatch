"""The lane-body quarantine: bodies that are an aggregator's page text, not the employer's.

D-406 measured job-apps' jobright records storing jobright's rendered PAGE — the page title,
the site nav, and jobright's OWN derived label `H1B Sponsor Likely` — inside what boardwatch
then freezes as the JD. `work_auth` is a blocker family and `INELIGIBLE` must carry a quoted
span from the frozen JD, so an `ineligible(work_auth)` quoting that label would present a third
party's guess as the employer's stated requirement.

One row per QUARANTINED posting version. Nothing sweeps this table and nothing deletes from it,
including the drain, which sets `reopened_at` — the same shape `p6_job_dispositions` chose, for
the same reason: draining a bucket must not erase the record that it ever held anything.

Creates the table only. It deliberately does not backfill: the detector is Python and a
migration is a historical record that must not import a live catalog.

**How the bucket fills, stated correctly.** An earlier draft of this docstring claimed the first
`run_eligibility` would fill it. That was false for the nine live rows and measurably so — all
nine already carry a current-identity evaluation, so `_pending` excludes them and a
pending-scoped check would have filled the bucket with ZERO. The filling is done instead by the
sweep over every current version of an open posting that has no `body_precondition_checks` row
at the detector's current fingerprint (`p_body_precondition_checks`), which does reach them.
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
