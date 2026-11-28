"""Index the final gate's rows: `eligibility_evaluations(input_id, id) WHERE engine_kind = 'llm'`.

Pure performance; no schema semantics change and no backfill. The reads keyed on the judge's
inputs (`eligibility.read._latest_gate_rows`, behind the ranker, the delivery queue and the run's
lane split) join every eligibility input of the asked-about versions to its evaluations under
`engine_kind = 'llm'`. The table's indexes lead on `input_id`, and its one partial index covers
`deterministic` rows, so each probe landed in the index over all 6.5M evaluations. The gate rows
are about 19.5k of them. Measured on a clone of the live store (2026-11-27), the ranker's call over
748,661 open versions: **66.2 s before, 3.6 s after**, the same 9,885 verdicts (digest equal), and
the index built in 1.9 s with the table warm.

Creating an index is safe to re-run against any store: it derives entirely from existing rows. It
reads the whole table once to build.
"""

import sqlalchemy as sa
from alembic import op

revision = "perf_eligibility_evaluations_llm"
down_revision = "p_posting_blobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_eligibility_evaluations_llm",
        "eligibility_evaluations",
        ["input_id", "id"],
        sqlite_where=sa.text("engine_kind = 'llm'"),
    )


def downgrade() -> None:
    op.drop_index("ix_eligibility_evaluations_llm", table_name="eligibility_evaluations")
