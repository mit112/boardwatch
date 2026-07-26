"""P0 spine: artifact projections + derivation lineage (P5/P7 populate).

artifacts is a mutable projection carrying the lineage P7 needs to validate what P5
produced (job/version/application links, generator, media_type). kind is free text
(kinds grow). artifact_derivations records immutable derivation edges (tailored resume
<- base resume).
"""
import sqlalchemy as sa
from alembic import op

revision = "p0_artifacts"
down_revision = "p0_applications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("posting_version_id", sa.Integer(), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("generator", sa.Text(), nullable=True),
        sa.Column("generator_version", sa.Text(), nullable=True),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_artifacts_job_id_jobs")),
        sa.ForeignKeyConstraint(["posting_version_id"], ["posting_versions.id"],
                                name=op.f("fk_artifacts_posting_version_id_posting_versions")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"],
                                name=op.f("fk_artifacts_application_id_applications")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifacts")),
    )
    op.create_index("ix_artifacts_job_id", "artifacts", ["job_id"])
    op.create_table(
        "artifact_derivations",
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("parent_artifact_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"],
                                name=op.f("fk_artifact_derivations_artifact_id_artifacts")),
        sa.ForeignKeyConstraint(["parent_artifact_id"], ["artifacts.id"],
                                name=op.f("fk_artifact_derivations_parent_artifact_id_artifacts")),
        sa.PrimaryKeyConstraint("artifact_id", "parent_artifact_id", "relation",
                                name=op.f("pk_artifact_derivations")),
    )
    op.execute("CREATE TRIGGER artifact_derivations_no_update BEFORE UPDATE ON artifact_derivations "
               "BEGIN SELECT RAISE(ABORT, 'artifact_derivations is append-only'); END")
    op.execute("CREATE TRIGGER artifact_derivations_no_delete BEFORE DELETE ON artifact_derivations "
               "BEGIN SELECT RAISE(ABORT, 'artifact_derivations is append-only'); END")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS artifact_derivations_no_delete")
    op.execute("DROP TRIGGER IF EXISTS artifact_derivations_no_update")
    op.drop_table("artifact_derivations")
    op.drop_index("ix_artifacts_job_id", table_name="artifacts")
    op.drop_table("artifacts")
