"""P0 spine: annotate-only job-grouping ledger (D10/D28; P4 populates).

Preserves the history of how each occurrence (posting) was assigned/reassigned to
a canonical job, so P4 dedup can overwrite postings.job_id (the current projection)
without erasing the annotate-only decision trail. Append-only (immutability triggers).
"""
import sqlalchemy as sa
from alembic import op

revision = "p0_job_grouping"
down_revision = "p0_jobs_anchor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_grouping_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("posting_id", sa.Integer(), nullable=False),
        sa.Column("from_job_id", sa.Integer(), nullable=True),
        sa.Column("to_job_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["posting_id"], ["postings.id"],
                                name=op.f("fk_job_grouping_events_posting_id_postings")),
        sa.ForeignKeyConstraint(["from_job_id"], ["jobs.id"],
                                name=op.f("fk_job_grouping_events_from_job_id_jobs")),
        sa.ForeignKeyConstraint(["to_job_id"], ["jobs.id"],
                                name=op.f("fk_job_grouping_events_to_job_id_jobs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_grouping_events")),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_job_grouping_events_posting_id", "job_grouping_events",
                    ["posting_id", "id"])
    op.execute("CREATE TRIGGER job_grouping_events_no_update BEFORE UPDATE ON job_grouping_events "
               "BEGIN SELECT RAISE(ABORT, 'job_grouping_events is append-only'); END")
    op.execute("CREATE TRIGGER job_grouping_events_no_delete BEFORE DELETE ON job_grouping_events "
               "BEGIN SELECT RAISE(ABORT, 'job_grouping_events is append-only'); END")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS job_grouping_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS job_grouping_events_no_update")
    op.drop_index("ix_job_grouping_events_posting_id", table_name="job_grouping_events")
    op.drop_table("job_grouping_events")
