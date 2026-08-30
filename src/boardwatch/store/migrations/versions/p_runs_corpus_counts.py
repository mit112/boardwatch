"""The runs row keeps the standing eligible corpus, so a collapse is visible across runs.

The delivery-drought detector abstains on an eligibility collapse by construction: it asks
whether a run judged any candidate, and a run that judged NONE carries no delivery signal.
So the one failure that empties the corpus — a rules edit, a profile fact that stopped
resolving, a taxonomy change that makes every posting ineligible — is exactly the failure no
cross-run detector could see, because the numbers it would need lived only in the funnel
artifact on disk and never in the store. Three additive nullable columns put them where a
cross-run query can reach them.

`corpus_candidates` is `eligible + uncertain` — the deliverable verdicts, folded here on
purpose: this column exists to be a RATE numerator across runs, not to replace the funnel's
verdict split, which stays unfolded in the artifact (`ABSTAIN` is never folded into either
neighbour in any REPORT; this is a monitoring counter, not a report).

NULL is meaningful and is not zero: it means the row predates this migration, or a run whose
funnel never got as far as counting the corpus. A `NOT NULL DEFAULT 0` would make all 132
existing runs read as a MEASURED empty corpus — precisely the alarm state the detector is
built to catch — and the detector would fire on the day it shipped.

ALTER TABLE ADD COLUMN with no table rebuild — never batch_alter_table on `runs`, which six
tables reference by FK (the caveat p0_run_status records, and alembic runs with
`foreign_keys` OFF, so a rebuild would orphan the children silently). Downgrade uses native
DROP COLUMN (SQLite >= 3.35), the path p_death_probe, p_board_coverage and p_runs_board_split
take.

These do NOT enter the run manifest hash — they are observations about a corpus, not inputs
to a verdict (the precedent p_board_coverage and p_runs_board_split state for the same reason).
"""

from alembic import op

revision = "p_runs_corpus_counts"
down_revision = "p_runs_board_split"
branch_labels = None
depends_on = None

_COLUMNS = ("corpus_open", "corpus_evaluated", "corpus_candidates")


def upgrade() -> None:
    for name in _COLUMNS:
        op.execute(f"ALTER TABLE runs ADD COLUMN {name} INTEGER")


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE runs DROP COLUMN {name}")
