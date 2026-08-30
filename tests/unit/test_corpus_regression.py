"""Corpus-regression detector. Each test names the wrong-version it rejects.

A real schema on `tmp_path`. Runs are seeded directly onto the `runs` row — the detector reads
nothing else, which is the whole point of lifting the counts out of the funnel artifact.

The load-bearing test in this file is `test_a_shrinking_corpus_at_a_constant_rate_is_quiet`.
It is the one that rejects every count-based form of this detector, and the reason the metric
is a rate rather than the obvious threshold on `corpus_candidates`.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.notify.corpus_regression import (
    CORPUS_REGRESSION_TRIGGER,
    CORPUS_REGRESSION_WINDOW,
    check_corpus_regression,
)
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import RUN_OK

# The real (open, evaluated, candidates) triples recorded by runs 119-131, oldest first. Read
# out of the live store once and pinned here: this detector's whole claim is that it is silent
# across the history it was designed against, and a fixture that paraphrases that history
# cannot support the claim.
RECORDED_HISTORY: tuple[tuple[int, int, int], ...] = (
    (62118, 61955, 34822),
    (64521, 64362, 36440),
    (66824, 66672, 37978),
    (68999, 68852, 39437),
    (71070, 70938, 40771),
    (80895, 80779, 46638),
    (82532, 82429, 47704),
    (83855, 83718, 47577),
    (84964, 84845, 54768),
    (93169, 93059, 60824),
    (96918, 96816, 63497),
    (101128, 101105, 65148),
    (105935, 105935, 68248),
)


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _run(
    engine: Engine,
    *,
    open_postings: int | None,
    evaluated: int | None,
    candidates: int | None,
    status: str = RUN_OK,
) -> int:
    """One run row carrying a corpus measurement. `None` writes NULL — unmeasured."""
    now = utcnow()
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.runs).values(
                    started_at=now,
                    finished_at=now,
                    status=status,
                    corpus_open=open_postings,
                    corpus_evaluated=evaluated,
                    corpus_candidates=candidates,
                )
            ).inserted_primary_key[0]
        )


def _baseline(engine: Engine, *, evaluated: int, candidates: int, count: int = 5) -> None:
    """`count` identical qualifying runs — a flat baseline, so any verdict is about the subject."""
    for _ in range(count):
        _run(engine, open_postings=evaluated, evaluated=evaluated, candidates=candidates)


def _without_ids(alert: str) -> str:
    """The alert with its run numbers blanked, so two stores that differ only in how many rows
    they hold can be compared on the VERDICT rather than on autoincrement."""
    return re.sub(r"runs \([\d, ]+\)", "runs (ids)", re.sub(r"run \d+", "run N", alert))


def test_a_shrinking_corpus_at_a_constant_rate_is_quiet(engine: Engine) -> None:
    """THE load-bearing test. A corpus that shrank by 70% while clearing the same 64% is fine.

    This is not hypothetical: the eligibility identity re-keys constantly — `engine_version`
    took five distinct values across runs 115-131 — and `count_corpus` is scoped by it, so the
    run after a re-key finds most of the corpus in `no_current_evaluation` and evaluates a
    fraction of it. Nothing is wrong with such a run.

    Rejects every count-based form. A threshold on `corpus_candidates` sees 19,200 against a
    64,000 baseline — a 70% drop, far past any sane trigger — and pages at 04:00 on a healthy
    run. Only a rate over the population the metric itself defines survives this. It does NOT
    reach the `corpus_open` denominator, because a corpus that shrank has `open == evaluated`
    and the two forms coincide here; the test below is the one that separates them.
    """
    _baseline(engine, evaluated=100_000, candidates=64_000)
    _run(engine, open_postings=30_000, evaluated=30_000, candidates=19_200)  # same 64%
    assert check_corpus_regression(engine) is None


def test_the_rate_is_denominated_on_evaluated_not_on_the_open_corpus(engine: Engine) -> None:
    """The other wrong denominator, which the test above cannot reach.

    `candidates / corpus_open` looks equivalent — and in the test above it IS, because a corpus
    that shrank has `open == evaluated`. It stops being equivalent exactly where it matters: on
    a run that judged part of its corpus. This subject judged half of an unchanged 60k corpus
    and cleared 60% of what it judged, which is a normal run at the coverage floor. Denominated
    on `open` it reads 30% against a 64% baseline and fires.

    Deliberately at 60%, not the 64% used elsewhere: at 64% the `open`-denominated reading
    lands exactly ON the trigger, and a test that turns on a float equality is not a test.
    """
    _baseline(engine, evaluated=100_000, candidates=64_000)
    _run(engine, open_postings=60_000, evaluated=30_000, candidates=18_000)
    assert check_corpus_regression(engine) is None


def test_fires_when_the_rate_collapses_on_an_unchanged_corpus(engine: Engine) -> None:
    """The other half of the pair. Without this, the test above is satisfied by a detector
    that never fires at all — the cheapest wrong version there is. Same corpus, same
    `evaluated`, and nothing clears: the collapse this exists to catch."""
    _baseline(engine, evaluated=100_000, candidates=64_000)
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=0)

    alert = check_corpus_regression(engine)
    assert alert is not None
    assert "0.00%" in alert
    assert "64.00%" in alert


def test_a_barely_judged_run_is_skipped(engine: Engine, tmp_path: Path) -> None:
    """Run 118's real shape: 83,855 open, 4,127 evaluated — 4.9% coverage, a clean run.

    A rate measured over 4.9% of the corpus is a rate over whichever postings happened to be
    re-judged first, not over the corpus, so the run does not qualify.

    Clause (b) is what makes this non-vacuous: the FOLLOWING full-coverage run must reach the
    identical verdict whether or not the barely-judged run exists. A "skip" that merely
    shortens the window — filtering in Python after a `LIMIT window + 1` — would silence the
    detector for a day, and the (a)-only assertion cannot tell those apart.
    """
    # (a1) Run 118's real numbers. Its rate is 52.2%, so it happens to be silent either way —
    # this pins the SHAPE the guard exists for, and (a2) is the discriminating case.
    _baseline(engine, evaluated=100_000, candidates=64_000, count=6)
    _run(engine, open_postings=83_855, evaluated=4_127, candidates=2_156)
    assert check_corpus_regression(engine) is None

    # (a2) The same 4.9% coverage over a SKEWED slice — 4.8% of what it judged cleared. Nothing
    # says the 4,127 postings a re-key happens to re-judge first are representative of 83,855;
    # they are whatever the sweep reached, and a rate over them is not a rate over the corpus.
    # Without the coverage guard this pages at 04:00 on a healthy run. Rejects dropping it.
    _run(engine, open_postings=83_855, evaluated=4_127, candidates=200)
    assert check_corpus_regression(engine) is None

    # (b) The next real run's verdict is unmoved by its presence. Built twice from the same
    # sequence, once with the barely-judged run interposed and once without.
    def _verdict(*, with_barely_judged: bool) -> str | None:
        eng = get_engine(tmp_path / f"clause-b-{with_barely_judged}")
        ensure_schema(eng)
        _baseline(eng, evaluated=100_000, candidates=64_000)
        if with_barely_judged:
            _run(eng, open_postings=83_855, evaluated=4_127, candidates=2_156)
        _run(eng, open_postings=100_000, evaluated=100_000, candidates=0)
        return check_corpus_regression(eng)

    with_it = _verdict(with_barely_judged=True)
    without_it = _verdict(with_barely_judged=False)
    assert with_it is not None, "the collapse must still fire with a skipped run interposed"
    # Run IDs shift by one when an extra row is seeded, which says nothing about the verdict.
    # Everything else in the message — the subject's rate, its two counts, the baseline median
    # and the window — is exactly what a skipped run must not move, so it is compared verbatim.
    assert _without_ids(with_it) == _without_ids(without_it), (
        "a skipped run changed the verdict instead of being skipped"
    )


def test_a_null_corpus_column_is_not_a_zero(engine: Engine) -> None:
    """Rejects `coalesce(corpus_candidates, 0)` — the wrong version that ships by accident,
    because it makes the SQL simpler and every run in the store is NULL on the day this lands.

    Six healthy runs, then a run that recorded `evaluated` but no `candidates` — half-written,
    which is what a crash between the two would leave. Under the guard it is not measured, so
    the newest MEASURED run is the healthy one and the detector is silent. Coalesced to zero it
    becomes a 0% subject against a 64% median and fires on a run that measured nothing.
    """
    _baseline(engine, evaluated=100_000, candidates=64_000, count=6)
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=None)
    assert check_corpus_regression(engine) is None

    # `corpus_open` likewise. This one also happens to be excluded by the coverage comparison
    # — SQLite yields NULL for `x >= NULL * 0.5`, so the row drops out either way — so the
    # assertion pins the contract rather than catching a live mutant. It does reject a version
    # that computes coverage in Python with `(open or 0)`, which reads a half-written row as a
    # corpus of zero and therefore as fully covered.
    _run(engine, open_postings=None, evaluated=100_000, candidates=0)
    assert check_corpus_regression(engine) is None


def test_only_clean_runs_count(engine: Engine) -> None:
    """A crashed or in-flight run carries no corpus signal — its counts are whatever it got to
    before it stopped. It must neither trigger the alert nor rescue the window. Rejects
    dropping the `status = 'ok'` filter, in both directions."""
    # It cannot TRIGGER: the newest clean run is healthy, and a failed run's collapsed corpus
    # sitting on top of it is not a subject.
    _baseline(engine, evaluated=100_000, candidates=64_000, count=6)
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=0, status="failed")
    assert check_corpus_regression(engine) is None

    # It cannot RESCUE: a real collapse on a clean run still fires with a healthy `running` run
    # newer than it. Without the status filter that in-flight row becomes the subject and the
    # collapse below it goes unreported. Mirrors the delivery-drought detector's own test.
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=0)
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=64_000, status="running")
    assert check_corpus_regression(engine) is not None


def test_a_healthy_run_in_the_window_cannot_be_out_voted_by_the_median(engine: Engine) -> None:
    """The median is the point of the baseline: one poisoned prior must not move it.

    Rejects a mean. With four healthy priors at 64% and one absurd 400% prior, a mean baseline
    reads 131% and the healthy subject at 64% lands below half of it — a false fire. The median
    reads 64% and stays quiet.
    """
    _baseline(engine, evaluated=100_000, candidates=64_000, count=4)
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=400_000)  # absurd
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=64_000)  # healthy
    assert check_corpus_regression(engine) is None


def test_abstains_below_the_window(engine: Engine) -> None:
    """The state that exists the DAY this ships: every run NULL, then one measured run. Firing
    there would page on the deployment itself. Fewer than `window` qualifying priors is not
    enough history to judge."""
    for _ in range(CORPUS_REGRESSION_WINDOW - 1):
        _run(engine, open_postings=100_000, evaluated=100_000, candidates=64_000)
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=0)
    assert check_corpus_regression(engine) is None

    # One more qualifying prior and the same collapse is judgeable — so the abstention above
    # is about the window, not about the detector being inert.
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=0)
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=0)
    assert check_corpus_regression(engine) is not None


def test_a_zero_baseline_abstains(engine: Engine) -> None:
    """A sustained collapse eventually pushes 0.0 rates into the baseline window one run at a
    time, until the median is 0.0 itself. Dividing by it raises `ZeroDivisionError` inside a
    `finally` block — which the runner catches, but at the cost of the alert. There is no
    regression to report against a baseline that has already collapsed."""
    _baseline(engine, evaluated=100_000, candidates=0)
    _run(engine, open_postings=100_000, evaluated=100_000, candidates=0)
    assert check_corpus_regression(engine) is None


def test_the_window_and_trigger_are_pinned_as_literals() -> None:
    """Spelled as literals, never against the imported constant: an assertion of the form
    `check(window=CORPUS_REGRESSION_WINDOW)` moves WITH a mutant that changes the constant and
    proves nothing. These two numbers were chosen against 66 clean runs of measured history —
    a trigger of 0.65 costs three false alarms — so changing either is a decision, and this
    line is where that decision has to be acknowledged."""
    assert CORPUS_REGRESSION_WINDOW == 5
    assert CORPUS_REGRESSION_TRIGGER == 0.5


def test_silent_across_the_recorded_history(engine: Engine) -> None:
    """Replayed against the real numbers runs 119-131 recorded, one run at a time.

    This is the false-positive budget, measured rather than argued. Every one of these runs was
    clean, and the corpus grew from 62k to 106k open postings across them while the identity
    re-keyed repeatedly. Silence on all thirteen is the claim, and it is the regression fixture
    for the whole configuration: window, trigger, coverage floor and metric together.

    **What it discriminates, measured rather than assumed.** Across this slice the run-over-run
    ratio of the rate spans [0.9888, 1.1333] — the tightest margin is run 126's 0.9888 — so the
    replay rejects any trigger at or above ~0.99 and nothing weaker. It does NOT reject 0.65: no
    run in these thirteen falls that far. The finding that 0.65 costs three false alarms was
    measured over the wider 66-run history, and what defends the constant against a mutant is
    the literal pin above, not this replay. Saying so is the point — a fixture credited with
    catching something it cannot is worse than no fixture.
    """
    for open_postings, evaluated, candidates in RECORDED_HISTORY:
        _run(engine, open_postings=open_postings, evaluated=evaluated, candidates=candidates)
        alert = check_corpus_regression(engine)
        assert alert is None, f"false fire on the recorded history: {alert}"

    # Non-vacuous: the replay above really did build a judgeable window, so the silence is a
    # verdict rather than an abstention. One collapsed run on top of that same history fires.
    with engine.connect() as conn:
        judged = conn.execute(select(tables.runs.c.id)).all()
    assert len(judged) == len(RECORDED_HISTORY)
    _run(engine, open_postings=105_935, evaluated=105_935, candidates=0)
    assert check_corpus_regression(engine) is not None
