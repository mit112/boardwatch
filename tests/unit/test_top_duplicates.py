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
    """A suppression that cannot be listed is a leak, not a filter."""
    seed = seed_dedup(count=2)
    backfill_identities(seed)
    settings = _settings(seed.data_dir)
    shown = rank_open_postings(seed.engine, settings, limit=10, include_duplicates=True)
    hidden = rank_open_postings(seed.engine, settings, limit=10)
    assert len(shown.visible) == len(hidden.visible) + hidden.hidden_duplicate
    assert shown.hidden_duplicate == 0
    surfaced = [p for p in shown.visible if p.duplicate_of is not None]
    assert len(surfaced) == 1
    assert surfaced[0].duplicate_of in {p.posting_id for p in hidden.visible}


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
