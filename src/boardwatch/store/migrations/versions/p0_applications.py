"""P0 spine: application / decision funnel state (net-new; workflow is P5).

applications is mutable state — attempt_no allows reapplications per canonical job
(UNIQUE(job_id, attempt_no)); posting_version_id records which version was applied to.
application_events is the append-only, immutable decision ledger.
"""
import sqlalchemy as sa
from alembic import op

revision = "p0_applications"
down_revision = "p0_eligibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("posting_version_id", sa.Integer(), nullable=True),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('interested', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn')",
            name=op.f("ck_applications_status_enum")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_applications_job_id_jobs")),
        sa.ForeignKeyConstraint(["posting_version_id"], ["posting_versions.id"],
                                name=op.f("fk_applications_posting_version_id_posting_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint("job_id", "attempt_no", name=op.f("uq_applications_job_id_attempt_no")),
    )
    op.create_table(
        "application_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("detail_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"],
                                name=op.f("fk_application_events_application_id_applications")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_application_events_application_id", "application_events",
                    ["application_id", "id"])
    op.execute("CREATE TRIGGER application_events_no_update BEFORE UPDATE ON application_events "
               "BEGIN SELECT RAISE(ABORT, 'application_events is append-only'); END")
    op.execute("CREATE TRIGGER application_events_no_delete BEFORE DELETE ON application_events "
               "BEGIN SELECT RAISE(ABORT, 'application_events is append-only'); END")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS application_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS application_events_no_update")
    op.drop_index("ix_application_events_application_id", table_name="application_events")
    op.drop_table("application_events")
    op.drop_table("applications")
