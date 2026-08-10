"""Duplicate suppression in the lead list, and its drain (design §1.4, §5.2)."""

from pathlib import Path

from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.cli.top_cmd import rank_open_postings
from boardwatch.core.settings import Settings

# The only body that makes the degree rule fire. Same string as
# tests/unit/test_top_accounting.py::DEGREE_BODY, which pins the same recipe; declared here
# rather than imported because a conftest is not importable as a module.
DEGREE_BODY = "We are hiring a backend engineer. A Bachelor's degree is required."

# Seeding shapes, all from the `seed_dedup` factory in tests/conftest.py:
#   seed_dedup(count=2)                  -> the exact_quad pair (identical but provider id)
#   seed_dedup(count=2, identical=False) -> two postings that must never group
#   seed_dedup(count=3)                  -> three-way group, for the partial-backfill gate
#   backfill_identities(seed)            -> full coverage
#   backfill_identities(seed, ids[:2])   -> deliberate partial coverage


def _settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, config_dir=data_dir)


def _make_everything_ineligible(data_dir: Path) -> None:
    """Drive the real eligibility engine, the same recipe as test_top_accounting.py.

    Only works because `dedup_env` points BOARDWATCH_CONFIG_DIR at the data dir; split, these
    writes land where the ranker never looks and the test silently passes for no reason.
    """
    for args in (
        ["eligibility", "facts", "set", "highest_degree", "none"],
        ["eligibility", "policy", "set", "degree", "blocker"],
        ["eligibility", "run"],
    ):
        result = CliRunner().invoke(app, ["--data-dir", str(data_dir), *args])
        assert result.exit_code == 0, f"{args} failed: {result.stdout}"


def test_duplicates_are_hidden_and_counted(seed_dedup, backfill_identities):
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    results = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert results.hidden_duplicate == 1
    assert len(results.visible) == 1


def test_the_drain_shows_every_suppressed_row(seed_dedup, backfill_identities):
    """A suppression that cannot be listed is a leak, not a filter.

    `limit=1` with a three-way group is the whole point: the limit MUST bind. An earlier
    version of this test used count=2 with limit=10, so the limit was never reached and the
    assertion held for any limit handling at all — including the one that ran drained
    duplicates through `if len(visible) < limit`, where the drain surfaces only the
    suppressed rows that also beat the rank cutoff and the bucket stays unlistable.

    With the limit binding, that implementation reads `1 == 1 + 2` and goes red. Drained rows
    do not consume limit slots, so the drain deliberately returns more than `limit` rows.
    """
    seed = seed_dedup(count=3)
    backfill_identities(seed)
    settings = _settings(seed.data_dir)
    shown = rank_open_postings(seed.engine, settings, limit=1, include_duplicates=True)
    hidden = rank_open_postings(seed.engine, settings, limit=1)
    assert hidden.hidden_duplicate == 2, "the group must actually be suppressed"
    assert len(shown.visible) == len(hidden.visible) + hidden.hidden_duplicate
    assert len(shown.visible) > 1, "the drain must be able to exceed the rank limit"
    assert shown.hidden_duplicate == 0
    surfaced = [p for p in shown.visible if p.duplicate_of is not None]
    assert len(surfaced) == 2
    assert {p.duplicate_of for p in surfaced} == {p.posting_id for p in hidden.visible}


def test_the_drain_does_not_evict_survivors_to_make_room(seed_dedup, backfill_identities):
    """The survivor a drained row names must itself still be in the output.

    Otherwise `duplicate of 41` points at a posting the reader cannot see, which is a worse
    failure than hiding the duplicate: it looks like an answer and is not one.
    """
    seed = seed_dedup(count=3)
    backfill_identities(seed)
    shown = rank_open_postings(
        seed.engine, _settings(seed.data_dir), limit=1, include_duplicates=True
    )
    shown_ids = {p.posting_id for p in shown.visible}
    for p in shown.visible:
        if p.duplicate_of is not None:
            assert p.duplicate_of in shown_ids


def test_the_reconciliation_identity_holds_with_the_drain_open(seed_dedup, backfill_identities):
    """The identity must survive the drain, at a limit that binds.

    Drained rows land in `visible` instead of `hidden_duplicate`; the sum is unchanged.
    """
    seed = seed_dedup(count=3)
    backfill_identities(seed)
    r = rank_open_postings(
        seed.engine, _settings(seed.data_dir), limit=1, include_duplicates=True
    )
    assert r.considered == (
        len(r.visible)
        + r.skipped_not_new
        + r.hidden_hard_filter
        + r.hidden_non_swe
        + r.hidden_ineligible
        + r.hidden_below_cutoff
        + r.hidden_duplicate
    )


def test_incomplete_identities_are_reported_not_silently_zero(seed_dedup, backfill_identities):
    """`hidden_duplicate == 0` is ambiguous; this flag is what disambiguates it.

    Nothing in the automated path writes identities, so "dedup never ran" is the common
    state, not the corner. A caller that cannot tell it from "no duplicates found" will read
    an uninstrumented run as a clean one.
    """
    seed = seed_dedup(count=2)
    before = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert before.identities_are_complete is False
    assert before.hidden_duplicate == 0

    backfill_identities(seed)
    after = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert after.identities_are_complete is True
    assert after.hidden_duplicate == 1


def test_a_partial_backfill_reports_incomplete(seed_dedup, backfill_identities):
    """Partial coverage must read as incomplete, not as complete-with-nothing-found."""
    seed = seed_dedup(count=3)
    backfill_identities(seed, seed.posting_ids[:2])
    r = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert r.identities_are_complete is False


def test_the_survivor_is_the_earliest_seen_posting(seed_dedup, backfill_identities):
    """Survivor election reads first_seen_at, with posting_id only as the tiebreak (§5.1).

    `seed_dedup` deliberately inverts the two orderings: posting_ids[-1] is the earliest-seen
    row while posting_ids[0] has the lowest id. So this asserts the LAST seeded posting wins.
    An election that sorted by posting_id — or that just took whichever row the group
    iteration reached first — would return posting_ids[0] and go red here. With the two
    orderings agreeing, no test could tell those implementations apart.
    """
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    r = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert [p.posting_id for p in r.visible] == [seed.posting_ids[-1]]


def test_the_reconciliation_identity_still_holds_with_duplicates(seed_dedup, backfill_identities):
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    r = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert r.considered == (
        len(r.visible)
        + r.skipped_not_new
        + r.hidden_hard_filter
        + r.hidden_non_swe
        + r.hidden_ineligible
        + r.hidden_below_cutoff
        + r.hidden_duplicate
    )


def test_an_ineligible_posting_is_not_also_counted_as_a_duplicate(seed_dedup, backfill_identities):
    """Dedup runs last, over the post-eligibility population (design §1.4).

    Both postings are identical AND both are ineligible — identical means identical, so a
    fixture where only one carried the degree body would have to give the pair the same
    content_hash over different bodies, a state production can never reach.

    So the assertion is `hidden_ineligible == 2, hidden_duplicate == 0`. If dedup ran BEFORE
    the eligibility filter, one row would be suppressed first and the counts would read 1 and
    1 — which is exactly the double-count this pins, and it breaks the identity above.
    """
    seed = seed_dedup(count=2, body=DEGREE_BODY)
    backfill_identities(seed)
    _make_everything_ineligible(seed.data_dir)
    r = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert r.hidden_ineligible == 2
    assert r.hidden_duplicate == 0
    assert len(r.visible) == 0


def test_no_duplicates_means_no_behaviour_change(seed_dedup, backfill_identities):
    seed = seed_dedup(count=2, identical=False)
    backfill_identities(seed)
    r = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert r.hidden_duplicate == 0
    assert len(r.visible) == 2


def test_postings_without_identity_rows_are_never_suppressed(seed_dedup):
    """Before `identities backfill` runs, the ranker must behave exactly as it did before.

    No backfill_identities call here, deliberately.
    """
    seed = seed_dedup(count=2)
    r = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert r.hidden_duplicate == 0
    assert len(r.visible) == 2


def test_a_partial_backfill_suppresses_nothing_at_all(seed_dedup, backfill_identities):
    """The completeness gate. Two of three postings carry identities; the pair would group.

    Suppressing that pair is *safe* — the third is untouched — but which of the two is
    elected depends on backfill order, so the suppression cannot be re-derived from the
    data during the Gate P6 audit. See the task preamble; this asserts reproducibility,
    not safety.
    """
    seed = seed_dedup(count=3)
    backfill_identities(seed, seed.posting_ids[:2])
    r = rank_open_postings(seed.engine, _settings(seed.data_dir), limit=10)
    assert r.hidden_duplicate == 0
    assert len(r.visible) == 3
