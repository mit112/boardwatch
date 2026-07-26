"""P0 spine: canonical job identity anchor (D28).

Adds `jobs` (the annotation layer above postings — postings keep their
(company_id, provider_posting_id) identity per D10 and gain a real job_id FK;
a job groups occurrences, never merges them — dedup is P4). Backfills one job
per existing posting (1:1), dated to first_seen_at. job_id is nullable at the
column level (SQLite ALTER cannot add NOT NULL without a rebuild) but required
by BEFORE INSERT/UPDATE triggers. SQLite permits ADD COLUMN ... REFERENCES for
a nullable column (verified on 3.50.4).
"""
import sqlalchemy as sa
from alembic import op

revision = "p0_jobs_anchor"
down_revision = "b7e41c0a9f23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    # op.add_column() with an attached ForeignKey renders as ALTER TABLE ADD COLUMN
    # + a separate ADD CONSTRAINT, which SQLite's Alembic dialect rejects outright
    # (NotImplementedError: no ALTER-constraint support; batch/rebuild only). Raw SQL
    # folds the REFERENCES clause into the single ADD COLUMN statement instead, which
    # SQLite executes natively (verified on 3.50.4) and reflects back as a real FK via
    # PRAGMA foreign_key_list — no rebuild needed.
    op.execute("ALTER TABLE postings ADD COLUMN job_id INTEGER REFERENCES jobs (id)")
    op.create_index("ix_postings_job_id", "postings", ["job_id"], unique=False)
    # Backfill 1:1 — a canonical job per existing posting, dated to first_seen_at.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, first_seen_at FROM postings ORDER BY id")).fetchall()
    for posting_id, first_seen_at in rows:
        result = conn.execute(
            sa.text("INSERT INTO jobs (created_at) VALUES (:c)"), {"c": first_seen_at}
        )
        conn.execute(
            sa.text("UPDATE postings SET job_id = :j WHERE id = :p"),
            {"j": result.lastrowid, "p": posting_id},
        )
    # NOT-NULL enforcement via triggers (no rebuild).
    op.execute(
        "CREATE TRIGGER postings_job_required_insert BEFORE INSERT ON postings "
        "WHEN NEW.job_id IS NULL BEGIN SELECT RAISE(ABORT, 'postings.job_id is required'); END"
    )
    op.execute(
        "CREATE TRIGGER postings_job_required_update BEFORE UPDATE OF job_id ON postings "
        "WHEN NEW.job_id IS NULL BEGIN SELECT RAISE(ABORT, 'postings.job_id is required'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS postings_job_required_update")
    op.execute("DROP TRIGGER IF EXISTS postings_job_required_insert")
    op.drop_index("ix_postings_job_id", table_name="postings")
    op.execute("ALTER TABLE postings DROP COLUMN job_id")  # native (SQLite >= 3.35)
    op.drop_table("jobs")
