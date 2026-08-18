"""Close the `runs` rows the P0 status backfill left `running` after they had already finished.

`p0_run_status` added `status` with `DEFAULT 'running'`. That default is right for a row still in
flight, but it also backfilled every row that already existed — including rows the pre-status
`finish_run` had already closed by stamping `finished_at` and nothing else. Those rows read
`running` with `finished_at` set, and no drain can reach them: `reap_stale_runs` requires
`finished_at IS NULL`, and `tests/unit/test_queries.py` pins that exclusion as intentional.

**Matched on the combination, never on row ids.** `status='running' AND finished_at IS NOT NULL` is
unreachable through every current write path: `record_scan_run(finished=True)`, `finish_run` and
`reap_stale_runs` each stamp `finished_at` and `status` in the SAME UPDATE, so no writer can produce
one without the other. The combination is therefore a backfill artifact by construction rather than
a fact about this repo's database, which is what makes the predicate correct against any operator's
store — including one whose affected ids are not 1-4. `doctor` asserts the same invariant from now
on, so a recurrence is loud instead of inert.

**`ok`, decided by the owner (D-229).** `p0_run_status`'s own docstring argued against exactly this,
on the premise that such rows are "indistinguishable from a killed run". That premise is false, and
the store disproves it: a killed run never reaches the closer, so it keeps `finished_at` NULL. Every
affected row carries a `finished_at`, so every one of them was closed by a writer that ran. What
stays genuinely unrecorded is the narrower question of whether that close was a success or a
failure — the pre-status closer wrote no terminal status either way — and `ok` is the owner's ruling
on rows whose pipeline demonstrably reached its closer.
"""

from alembic import op

revision = "runs_status_backfill_repair"
down_revision = "perf_eligibility_inputs_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE runs SET status = 'ok' WHERE status = 'running' AND finished_at IS NOT NULL")


def downgrade() -> None:
    """Deliberately a no-op.

    After the upgrade these rows are byte-identical to runs that genuinely finished `ok`, so no
    predicate can pick them back out; running the upgrade's predicate in reverse would relabel every
    successful run `running` and manufacture the exact defect this migration exists to remove. A
    downgrade that cannot restore the prior state truthfully does nothing rather than guess.
    """
