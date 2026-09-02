"""Durable record of every lane-body precondition check, so the detector's catalog is executable.

The quarantine shipped in `p_quarantined_bodies` records only FAILURES. That leaves the
catalog unable to reach a body that already carries a current-identity evaluation:
`eligibility/preflight.py::_pending` keys on profile, rules and engine version, none of which
move when a marker is added, so a body the old catalog passed stays passed forever and the
catalog version is decorative.

One row per checked posting version, keyed on the detector's FINGERPRINT — a digest of the
markers and the threshold — rather than on the hand-maintained version integer, so an edit that
forgets to bump the version still invalidates every check.

Creates the table only, and does not backfill: the sweep in `run_eligibility` fills it on the
first invocation after this ships, which is the same pass that decides what the rules may read.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_body_precondition_checks"
down_revision = "p_quarantined_bodies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "body_precondition_checks",
        sa.Column("posting_version_id", sa.Integer(), nullable=False),
        sa.Column("catalog_fingerprint", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("posting_version_id", name=op.f("pk_body_precondition_checks")),
        sa.ForeignKeyConstraint(
            ["posting_version_id"],
            ["posting_versions.id"],
            name=op.f("fk_body_precondition_checks_posting_version_id_posting_versions"),
        ),
    )
    op.create_index(
        "ix_body_precondition_checks_fingerprint",
        "body_precondition_checks",
        ["catalog_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_body_precondition_checks_fingerprint", table_name="body_precondition_checks"
    )
    op.drop_table("body_precondition_checks")
