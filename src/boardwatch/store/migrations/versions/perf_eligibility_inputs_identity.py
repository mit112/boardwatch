"""Index eligibility_inputs by (posting_version_id, profile_hash, rules_hash).

Pure performance; no schema semantics change and no backfill. `eligibility/preflight.py`'s
`_pending` anti-join correlates on `eligibility_inputs.posting_version_id` and filters on the
two identity hashes, but the table carried only its primary key and the `input_fingerprint`
unique index. With no index on the correlated column SQLite has to satisfy the EXISTS from the
other side: it re-scans `uq_eligibility_deterministic` and rowid-probes into this table once
per candidate row.

Measured on a copy of a live 24,073-posting store, timing the real `_pending`: **141.54 s before,
0.14 s after**, with 4,655 rows pending on both sides — so the index changes speed and not results.
The per-posting cost that explains it is ~5.8 ms. The measurement was taken with a NON-empty pending
queue; that an empty queue pays a similar floor is an inference from the query plan, not something
measured here.

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
