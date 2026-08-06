"""Run attribution for the eligibility and artifact ledgers.

Three of the seven funnel stages read from tables carrying no `run_id`, so they cannot be
attributed to a run at all: the eligible/ineligible/uncertain split, leads-with-a-PDF, and
marked-applied. This migration covers the first two. `applications` and `application_events`
are deliberately left alone — both hold 0 rows, so there is nothing to attribute yet and the
column would be speculative; it lands with the work that first writes them.

Nullable, no default. Every row written before this migration reads NULL, meaning "written
before run attribution existed". That is deliberately NOT the same as 0 and NOT the same as
"this run produced nothing": a NULL run_id is not evidence about any run, and the funnel
reports it as its own bucket rather than folding it into a real run's counts.

`eligibility_evaluations` is append-only (`eligibility_evaluations_no_update`), so its run_id
can only ever be set at INSERT and can never be backfilled. `artifacts` carries no such
trigger. Neither trigger names a column, so ADD/DROP COLUMN are unaffected by them.

ALTER TABLE ADD COLUMN with no table rebuild, the p2_profile_eligibility path. The inline
REFERENCES is unnamed because SQLite cannot add a *named* table-level constraint after the
fact; SQLite also requires an added column carrying a REFERENCES clause to default to NULL,
which nullable-no-default satisfies. Downgrade uses native DROP COLUMN (SQLite >= 3.35), the
p0_jobs_anchor precedent.
"""
from alembic import op

revision = "run_attribution"
down_revision = "p2_profile_eligibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE eligibility_evaluations ADD COLUMN run_id INTEGER REFERENCES runs (id)"
    )
    op.execute("ALTER TABLE artifacts ADD COLUMN run_id INTEGER REFERENCES runs (id)")


def downgrade() -> None:
    op.execute("ALTER TABLE artifacts DROP COLUMN run_id")
    op.execute("ALTER TABLE eligibility_evaluations DROP COLUMN run_id")
