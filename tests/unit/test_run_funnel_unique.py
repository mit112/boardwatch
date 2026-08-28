"""`unique` becomes a measured number; `assisted` stays not-instrumented (design §6)."""

from boardwatch.store.run_funnel_queries import (
    SourceOutcome,
    count_by_source,
    sweep_duplicates,
)

# The scoping arguments count_by_source already requires. Values copied from the existing
# call site in tests/unit/test_run_funnel_queries.py (`_by_source`), not invented: the
# identity pair and engine kind/version only key the eligibility sweep, and `posting_ids=[]`
# only empties the leads sweep — neither touches open_postings or the new unique sweep.
KIND, VERSION = "deterministic", "v1"
PROFILE, RULES = "ph", "rh"


def _by_source(seed) -> tuple[SourceOutcome, ...]:
    with seed.engine.connect() as conn:
        return count_by_source(
            conn,
            identity=(PROFILE, RULES),
            engine_kind=KIND,
            engine_version=VERSION,
            run_id=seed.run_id,
            posting_ids=[],
            # The real sweep on the same connection, not a stub: `unique` is derived from it,
            # so a hand-built DedupSweep here would test the arithmetic and nothing else.
            dedup=sweep_duplicates(conn),
        )


def test_without_identities_unique_stays_none(seed_dedup):
    """D-022/D-023 survives: reporting 0 would assert 'no source ever arrived second'.

    No backfill_identities call, deliberately.
    """
    outcomes = _by_source(seed_dedup(count=2))
    assert all(o.unique is None for o in outcomes)


def test_unique_counts_survivors_not_rows(seed_dedup, backfill_identities):
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    (outcome,) = _by_source(seed)
    assert outcome.open_postings == 2
    assert outcome.unique == 1


def test_a_partial_backfill_leaves_unique_none(seed_dedup, backfill_identities):
    """The completeness gate. `if identities:` passes here and reports a number.

    That number would be computed over two of three postings and printed in the same
    column as a real measurement.
    """
    seed = seed_dedup(count=3)
    backfill_identities(seed, seed.posting_ids[:2])
    outcomes = _by_source(seed)
    assert all(o.unique is None for o in outcomes)


def test_assisted_stays_none_even_with_a_complete_corpus_and_a_live_suppression(
    seed_dedup, backfill_identities
):
    """The corpus here is complete AND has a real suppression, so `unique` is a number.

    `assisted` must still be None. This is what separates "no mechanism could have counted
    one" from "we counted and got zero" — an implementation that emits a number as soon as
    identities exist goes red here, which is the point. See the module docstring on
    SourceOutcome for why no suppression in this slice can cross a source boundary.
    """
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    (outcome,) = _by_source(seed)
    assert outcome.unique == 1  # the corpus is complete; the gate is open
    assert outcome.assisted is None


def test_unique_never_exceeds_open_postings(seed_dedup, backfill_identities):
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    for outcome in _by_source(seed):
        assert outcome.unique is not None
        assert outcome.unique <= outcome.open_postings
