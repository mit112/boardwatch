"""Index eligibility_inputs by (posting_version_id, profile_hash, rules_hash).

Pure performance; no schema semantics change and no backfill. `eligibility/preflight.py`'s
`_pending` anti-join correlates on `eligibility_inputs.posting_version_id` and filters on the
two identity hashes, but the table carried only its primary key and the `input_fingerprint`
unique index. With no index on the correlated column SQLite has to satisfy the EXISTS from the
other side: it re-scans `uq_eligibility_deterministic` and rowid-probes into this table once
per candidate row. Measured against a live 24,073-posting store that is ~5.8 ms per open
posting, so `boardwatch top` paid a ~134 s floor on EVERY invocation before printing a lead,
even when no posting was pending.

Creating an index is safe to re-run against any store: it derives entirely from existing rows.
"""

from alembic import op

revision = "perf_eligibility_inputs_identity"
down_revision = "p6_job_dispositions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_eligibility_inputs_version_identity",
        "eligibility_inputs",
        ["posting_version_id", "profile_hash", "rules_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_eligibility_inputs_version_identity", table_name="eligibility_inputs")
