"""D-325: a per-posting strike counter and probe clock for the measured-death close.

Two additive columns on `postings`, no table rebuild:

1. `death_strikes INTEGER NOT NULL DEFAULT 0` — consecutive `refetch_gone` probes against this
   posting's own URL. A NEW column and deliberately not `consecutive_missing`: that one counts
   complete-board absences and is reset by `_apply_listed` on every positive listing (D23).
   Fusing two different signals into one column would make `>= CLOSE_AFTER_MISSES` fire on a
   mixture of one absence and one 404, and no report could then say which evidence closed a
   posting. Separate columns, separate evidence.

2. `last_death_probe_at DATETIME NULL` — when this row was last asked. Drives the TTL that
   bounds the sweep; NULL means never asked, which sorts first in the least-recently-probed
   order so a fresh corpus is worked front to back rather than re-probing the same head.

Both defaults state a fact about every pre-existing row rather than guessing one: nothing in
the store has ever been probed by this mechanism, so zero strikes and no probe time are true.
A `last_death_probe_at` defaulted to the migration time would have been the dangerous
alternative — it would have hidden the entire legacy corpus from the first sweep for a full
TTL while the funnel honestly reported an empty due set.

The downgrade drops both with native `DROP COLUMN` (SQLite >= 3.35), the path
`p1_resume_max_pages` and `p_seniority_band` take. The strike history is lost, which the
pre-migration schema cannot express; no posting is.
"""

from alembic import op

revision = "p_death_probe"
down_revision = "p_lane_companies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE postings ADD COLUMN death_strikes INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE postings ADD COLUMN last_death_probe_at DATETIME")


def downgrade() -> None:
    op.execute("ALTER TABLE postings DROP COLUMN last_death_probe_at")
    op.execute("ALTER TABLE postings DROP COLUMN death_strikes")
