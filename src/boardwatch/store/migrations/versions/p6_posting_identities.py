"""P6 slice 1: stored posting identities (design §1.2, §7).

Deliberately does NOT backfill. Recomputing identities for a 23k-row corpus is an explicit
`boardwatch identities backfill`, not a side effect of `alembic upgrade`, so it can also be
re-run after an IDENTITY_ALGORITHM_VERSION bump. Until it is run the funnel honestly reports
`not instrumented` rather than a partial number.

Does not touch postings.job_id: slice 1 annotates, slice 2 projects (design §1.3).
"""

import sqlalchemy as sa
from alembic import op

from boardwatch.core.identity_kinds import IDENTITY_KIND_NAMES

revision = "p6_posting_identities"
down_revision = "p1_resume_max_pages"
branch_labels = None
depends_on = None

_KIND_LIST = ", ".join(f"'{name}'" for name in IDENTITY_KIND_NAMES)


def upgrade() -> None:
    op.create_table(
        "posting_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("posting_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("identity_key", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posting_identities")),
        sa.ForeignKeyConstraint(
            ["posting_id"], ["postings.id"], name=op.f("fk_posting_identities_posting_id_postings")
        ),
        # Both names are the FULL convention-rendered form, matching the repo's other
        # migrations (p0_applications.py, 8df3b3809bba_schema_v1.py). tables.py declares these
        # constraints unnamed and lets metadata's naming_convention render them, so anything
        # else here makes `test_migrations_match_metadata` see permanent drift between the
        # migrated DB and the metadata.
        sa.UniqueConstraint(
            "posting_id",
            "kind",
            "algorithm_version",
            name=op.f("uq_posting_identities_posting_id_kind_algorithm_version"),
        ),
        sa.CheckConstraint(
            f"kind IN ({_KIND_LIST})", name=op.f("ck_posting_identities_identity_kind_enum")
        ),
    )
    op.create_index(
        "ix_posting_identities_key", "posting_identities", ["kind", "identity_key"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_posting_identities_key", table_name="posting_identities")
    op.drop_table("posting_identities")
