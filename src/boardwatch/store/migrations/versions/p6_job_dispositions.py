"""P6 slice 2: the durable decision ledger (design §2, §9).

One row per job, upserted monotonically. `built`/`skipped` are permanent and carry a
policy-version stamp; `seen` is TTL'd and expires lazily at read time — nothing sweeps this
table and nothing deletes from it, including the drain, which sets `reopened_at` instead.

Creates the table only. It does not backfill and it cannot: a disposition is a record of a
decision this program made, so inventing rows for the existing corpus would fabricate decisions
that were never taken.
"""

import sqlalchemy as sa
from alembic import op

revision = "p6_job_dispositions"
down_revision = "p6_posting_identities"
branch_labels = None
depends_on = None

# FROZEN as of this revision. Do NOT import DISPOSITIONS / REASON_NAMES from core.ledger here: a
# migration is a historical record, and importing the live catalog makes these CHECK constraints
# change retroactively — a fresh database replays this revision with the NEW enum while an
# already-migrated one keeps the OLD, so identical code succeeds on one install and raises
# IntegrityError on the other. Widening a catalog is a new migration, not an edit to these
# literals. tables.py may import the catalog; it is metadata, not history, and
# `test_migrations_match_metadata` is what holds the two in agreement.
_FROZEN_DISPOSITIONS = ("seen", "skipped", "built")
_FROZEN_PERMANENT = ("built", "skipped")
_FROZEN_REASONS = ("lead_built", "surfaced", "unshippable_artifact")

_DISPOSITION_LIST = ", ".join(f"'{name}'" for name in _FROZEN_DISPOSITIONS)
_PERMANENT_LIST = ", ".join(f"'{name}'" for name in _FROZEN_PERMANENT)
_REASON_LIST = ", ".join(f"'{name}'" for name in _FROZEN_REASONS)


def upgrade() -> None:
    op.create_table(
        "job_dispositions",
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("disposition", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("reopened_at", sa.DateTime(), nullable=True),
        sa.Column("first_decided_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_job_dispositions")),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_job_dispositions_job_id_jobs")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_job_dispositions_run_id_runs")
        ),
        # Every name below is the FULL convention-rendered form. tables.py declares these
        # constraints with a bare `name=` and lets metadata's naming_convention prefix it, so
        # anything else here makes `test_migrations_match_metadata` see permanent drift — the one
        # defect in slice 1 that only the full `make check` could see (D-094).
        sa.CheckConstraint(
            f"disposition IN ({_DISPOSITION_LIST})",
            name=op.f("ck_job_dispositions_disposition_enum"),
        ),
        sa.CheckConstraint(
            f"reason IN ({_REASON_LIST})", name=op.f("ck_job_dispositions_disposition_reason_enum")
        ),
        # The permanence contract, both tiers stated explicitly. A single biconditional
        # `(disposition IN permanent) = (policy_version IS NOT NULL AND expires_at IS NULL)`
        # looks equivalent and is not: it constrains only the permanent side, so a `seen` row
        # carrying a policy stamp AND no TTL satisfies it (0 = 0).
        sa.CheckConstraint(
            f"(disposition IN ({_PERMANENT_LIST})"
            " AND policy_version IS NOT NULL AND expires_at IS NULL)"
            f" OR (disposition NOT IN ({_PERMANENT_LIST})"
            " AND policy_version IS NULL AND expires_at IS NOT NULL)",
            name=op.f("ck_job_dispositions_permanence_wellformed"),
        ),
    )
    op.create_index(
        "ix_job_dispositions_expires_at", "job_dispositions", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_job_dispositions_expires_at", table_name="job_dispositions")
    op.drop_table("job_dispositions")
