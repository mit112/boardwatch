"""Corpus-regression detector (unattended observability).

The failure this closes is the one the delivery-drought detector names as out of scope. If a
rules edit, a profile fact that stops resolving, or a taxonomy change makes the whole corpus
ineligible, the standing eligible corpus empties — and drought abstains by construction,
because its honest guard is "did this run judge any candidate?" and the answer is no. Intake
death stays quiet too: postings are still arriving. The run reaches a clean outcome, the
heartbeat pings green, and an unattended machine ships nothing for two weeks while every
signal reads healthy.

**The metric is a RATE — `corpus_candidates / corpus_evaluated` — over the population the
metric itself defines, and the obvious alternatives are actively wrong here.** The eligibility
identity re-keys constantly (`engine_version` took five distinct values across runs 115-131),
and `count_corpus` is scoped by it, so the run after a re-key finds most of the corpus in
`no_current_evaluation` and reports a small `evaluated`. Run 131's predecessor is the proof:
`open = 83,855` against `evaluated = 4,127`, 4.9% coverage, on a completely clean run. A raw
COUNT threshold reads that as −96%; `candidates / corpus_open` reads it as −97%. Both would
page in the middle of the night on a run where nothing was wrong. A rate over `evaluated`
reads it as a normal day, and the coverage guard below skips it anyway.

Validated against the recorded history before shipping: across 66 clean runs the run-over-run
ratio of this rate sits in [0.989, 1.133], with exactly one excursion below 0.9 — 0.603 at run
119, a deliberate rules rewrite. A trigger at 0.5 costs zero false fires at windows 3, 5 and
7; 0.65 costs three. Injected total and half collapses both fire on the FIRST collapsed run.

**Known limitation, stated rather than discovered later: this is a STEP detector.** On a
sustained collapse it fires roughly three times, then the median migrates into the collapsed
regime and it goes quiet. That is acceptable and complementary — the alerts are durable in
`runs.errors_json`, and a permanently collapsed corpus stops being a *regression* and starts
being a state that the delivery and abstain reports describe better than a step alarm can.

Like the other cross-run detectors this raises a SOFT, non-fatal alert and NEVER sets
`summary.fatal`: the run itself succeeded, so the heartbeat must still fire.
"""

from __future__ import annotations

from statistics import median

from sqlalchemy import select
from sqlalchemy.engine import Engine

from boardwatch.store.queries import RUN_OK
from boardwatch.store.tables import runs

# Qualifying runs whose rate forms the baseline, not counting the subject. Five rather than
# three: the baseline is a median, and a median over five survives two poisoned points where a
# median over three survives one. Cheap to widen — these are three integers on a row that is
# already being read.
CORPUS_REGRESSION_WINDOW = 5

# Fire when the subject's rate has fallen to half the baseline or below. The measured clean
# floor is 0.603 (run 119, a deliberate rules rewrite that the owner made and knew about), so
# 0.5 sits below every clean excursion in the recorded history with room to spare, while a
# real collapse — the failure mode is "nothing clears any more", not "slightly fewer clear" —
# lands at or near 0.
CORPUS_REGRESSION_TRIGGER = 0.5

# A run must have judged at least half its open corpus to carry a rate worth comparing. This
# is the guard that makes an identity re-key a non-event rather than a page: the run after a
# re-key judges only what it re-judged, and a rate measured over 4.9% of the corpus is a rate
# over whichever postings happened to be re-judged first, not over the corpus.
CORPUS_COVERAGE_FLOOR = 0.5


def check_corpus_regression(
    engine: Engine, *, window: int = CORPUS_REGRESSION_WINDOW
) -> str | None:
    """Return a soft-alert string when the newest qualifying run's candidate rate has
    collapsed against the median of the `window` qualifying runs before it, else ``None``.

    A run QUALIFIES when it finished clean, when all three corpus columns are non-NULL, when
    it evaluated something, and when it evaluated at least `CORPUS_COVERAGE_FLOOR` of its own
    open corpus. The same filter applies to the subject and to every baseline point — a
    baseline assembled from a different population than the subject is a comparison between
    two things, not a measurement of one.

    NULL is never read as zero. `corpus_evaluated IS NULL` means the run predates these
    columns or never reached the corpus count, and coalescing it to 0 would turn every historic
    run into a measured empty corpus — which is the alarm itself. Such runs are skipped, and a
    skipped run is skipped, not counted: the window reaches further back for a real one.
    """
    with engine.connect() as conn:
        rows = [
            (int(run_id), int(evaluated), int(candidates))
            for run_id, evaluated, candidates in conn.execute(
                select(runs.c.id, runs.c.corpus_evaluated, runs.c.corpus_candidates)
                .where(
                    runs.c.status == RUN_OK,
                    # All three explicitly, including `corpus_open`, which this select does
                    # not read: it is the coverage guard's denominator, and a row missing it
                    # cannot be coverage-checked. Half-written is not measured.
                    runs.c.corpus_open.is_not(None),
                    runs.c.corpus_evaluated.is_not(None),
                    runs.c.corpus_candidates.is_not(None),
                    # The rate's denominator. Also the no-profile run's honest state
                    # (`funnel_writer._corpus_without_profile` writes `evaluated = 0`), which
                    # has no rate at all rather than a rate of zero.
                    runs.c.corpus_evaluated > 0,
                    # Multiplied rather than divided: SQLite returns NULL for division by zero
                    # instead of raising, so a `evaluated / open >= floor` form would silently
                    # drop rows on a fact about the engine rather than about the run.
                    runs.c.corpus_evaluated >= runs.c.corpus_open * CORPUS_COVERAGE_FLOOR,
                )
                .order_by(runs.c.id.desc())
                # The subject plus its baseline, filtered in SQL so the limit counts
                # QUALIFYING runs. Filtering in Python after a `LIMIT window + 1` would let one
                # skipped run shorten the window and silence the detector for a day.
                .limit(window + 1)
            ).all()
        ]

    if len(rows) < window + 1:
        return None

    subject_id, subject_evaluated, subject_candidates = rows[0]
    rate = subject_candidates / subject_evaluated
    baseline = median(candidates / evaluated for _, evaluated, candidates in rows[1:])

    # A zero baseline is reachable, not theoretical: a sustained collapse pushes 0.0 rates into
    # the window one run at a time until the median is 0.0 itself. Dividing by it raises, and
    # comparing against it would make every subsequent run "not below half of zero" anyway.
    # There is no regression to report against a baseline that already collapsed.
    if baseline <= 0:
        return None

    if rate > CORPUS_REGRESSION_TRIGGER * baseline:
        return None

    prior_ids = ", ".join(str(run_id) for run_id, _, _ in rows[1:])
    return (
        f"corpus: eligible/uncertain rate collapsed to {rate:.2%} on run {subject_id} "
        f"({subject_candidates} of {subject_evaluated} evaluated) against a {baseline:.2%} "
        f"median across the prior {window} runs ({prior_ids}) — an eligibility rule, a profile "
        f"fact or the taxonomy may have stopped clearing anything"
    )
