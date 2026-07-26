"""P0 spine: content-versioned posting history (D29, supersedes D25's no-history).

postings.body_text/content_hash remain the mutable current head; posting_versions is
the immutable append-only content log for change-detection/freshness. Honest backfill:
the current body's captured_at is the latest `revised` event when one exists (that is
when this body appeared), else first_seen_at; capture_reason records which. No invented
timestamps (this is an anti-fabrication product). Append-only (immutability triggers).
"""
import sqlalchemy as sa
from alembic import op

revision = "p0_posting_versions"
down_revision = "p0_job_grouping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posting_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("posting_id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("capture_reason", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "capture_reason IN ('new', 'revised', 'backfill_original', 'backfill_from_revised_event')",
            name=op.f("ck_posting_versions_capture_reason_enum")),
        sa.ForeignKeyConstraint(["posting_id"], ["postings.id"],
                                name=op.f("fk_posting_versions_posting_id_postings")),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"],
                                name=op.f("fk_posting_versions_run_id_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posting_versions")),
    )
    op.create_index("ix_posting_versions_posting_captured", "posting_versions",
                    ["posting_id", "captured_at", "id"])
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, content_hash, body_text, first_seen_at FROM postings ORDER BY id"
    )).fetchall()
    for posting_id, content_hash, body_text, first_seen_at in rows:
        rev = conn.execute(sa.text(
            "SELECT created_at FROM posting_events WHERE posting_id = :p AND kind = 'revised' "
            "ORDER BY id DESC LIMIT 1"), {"p": posting_id}).fetchone()
        if rev is not None:
            captured_at, reason = rev[0], "backfill_from_revised_event"
        else:
            captured_at, reason = first_seen_at, "backfill_original"
        conn.execute(sa.text(
            "INSERT INTO posting_versions (posting_id, content_hash, body_text, captured_at, "
            "run_id, capture_reason) VALUES (:p, :h, :b, :c, NULL, :r)"),
            {"p": posting_id, "h": content_hash, "b": body_text, "c": captured_at, "r": reason})
    op.execute("CREATE TRIGGER posting_versions_no_update BEFORE UPDATE ON posting_versions "
               "BEGIN SELECT RAISE(ABORT, 'posting_versions is append-only'); END")
    op.execute("CREATE TRIGGER posting_versions_no_delete BEFORE DELETE ON posting_versions "
               "BEGIN SELECT RAISE(ABORT, 'posting_versions is append-only'); END")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS posting_versions_no_delete")
    op.execute("DROP TRIGGER IF EXISTS posting_versions_no_update")
    op.drop_index("ix_posting_versions_posting_captured", table_name="posting_versions")
    op.drop_table("posting_versions")
