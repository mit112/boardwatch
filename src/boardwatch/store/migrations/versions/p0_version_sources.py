"""P0 spine: authoritative, FK-enforced source lineage per posting version.

One row per scan-captured version: board URL, provider record id, run, payload hash.
Replaces a generic polymorphic provenance table (which cannot enforce its subject
exists) for the freshness/trust spine. Immutable. No backfill — pre-migration
versions have no tracked source and none is invented.
"""
import sqlalchemy as sa
from alembic import op

revision = "p0_version_sources"
down_revision = "p0_posting_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posting_version_sources",
        sa.Column("posting_version_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["posting_version_id"], ["posting_versions.id"],
                                name=op.f("fk_posting_version_sources_posting_version_id_posting_versions")),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"],
                                name=op.f("fk_posting_version_sources_run_id_runs")),
        sa.PrimaryKeyConstraint("posting_version_id", name=op.f("pk_posting_version_sources")),
    )
    op.execute("CREATE TRIGGER posting_version_sources_no_update BEFORE UPDATE ON "
               "posting_version_sources BEGIN SELECT RAISE(ABORT, 'posting_version_sources is append-only'); END")
    op.execute("CREATE TRIGGER posting_version_sources_no_delete BEFORE DELETE ON "
               "posting_version_sources BEGIN SELECT RAISE(ABORT, 'posting_version_sources is append-only'); END")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS posting_version_sources_no_delete")
    op.execute("DROP TRIGGER IF EXISTS posting_version_sources_no_update")
    op.drop_table("posting_version_sources")
