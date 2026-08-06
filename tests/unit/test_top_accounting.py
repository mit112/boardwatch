"""The ranker accounts for every posting it considered (P0 item 3).

Gate P0 requires *why every non-lead was dropped* to be answerable from the funnel artifact
alone. Before this, `rank_open_postings` reported only two of its four exits: postings vetoed
by the hard filters and postings that ranked below the `--top` cutoff simply vanished, and on
a real run that was **14,873 postings in no bucket at all**.

The identity these tests pin is `considered == visible + every drop`. It is worth pinning
because it is the one arithmetic in the ranker that a future `continue` can silently break:
adding an early exit without a counter makes the funnel's shortlist stage stop reconciling,
which is exactly the signal Gate P0 is built on.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.cli.top_cmd import RankedResults, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = utcnow()

# Vetoed by the exclude-title substring rule, so it never reaches the role gate or the score.
EXCLUDED_TITLE = "Data Intern"
# The role gate reads this as non-software; it is counted, never a silent drop.
NON_SWE_TITLE = "Deal Strategist"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _seed(data_dir: Path, titles: list[str]) -> Engine:
    """One company, one open posting per title, distinct posted_at so ranking is total.

    `exclude_titles=["intern"]` is what makes EXCLUDED_TITLE a deterministic hard-filter
    rejection rather than a low score.
    """
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=["intern"],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
        )
        company_id = int(conn.execute(insert(companies).values(
            name="Acme", provider="greenhouse", slug="acme-acct", source="user", watched=True,
        )).inserted_primary_key[0])
        for offset, title in enumerate(titles):
            job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
            posting_id = int(conn.execute(insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{offset}",
                title=title, normalized_title=title.casefold(),
                locations_json=["Remote"], remote_policy="remote",
                # Descending recency, so `scored` has a strict order and "below the cutoff"
                # is a fact about a known posting rather than a tie broken arbitrarily.
                posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                status="open", consecutive_missing=0, content_hash=f"hh-{offset}", body_text="b",
            )).inserted_primary_key[0])
            conn.execute(insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"hh-{offset}", body_text="b",
                captured_at=NOW, capture_reason="new",
            ))
    return engine


def _settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, config_dir=data_dir)


def _rank(data_dir: Path, titles: list[str], *, limit: int) -> RankedResults:
    engine = _seed(data_dir, titles)
    return rank_open_postings(engine, _settings(data_dir), limit=limit)


def _accounted(results: RankedResults) -> int:
    """Everything the ranker says it did with the postings it looked at."""
    return (
        len(results.visible)
        + results.skipped_not_new
        + results.hidden_hard_filter
        + results.hidden_non_swe
        + results.hidden_ineligible
        + results.hidden_below_cutoff
    )


def test_every_considered_posting_lands_in_exactly_one_bucket(env: Path) -> None:
    """The whole point of item 3: no posting leaves the ranker uncounted."""
    results = _rank(
        env,
        ["Backend Engineer", "Platform Engineer", EXCLUDED_TITLE, NON_SWE_TITLE],
        limit=1,
    )
    assert results.considered == 4
    assert _accounted(results) == results.considered


def test_a_posting_below_the_top_cutoff_is_counted_rather_than_vanishing(env: Path) -> None:
    """The bucket that did not exist at all before item 3.

    Two software postings clear every filter and `limit=1`, so exactly one is shown and the
    other is below the cutoff. Asserted as its own number, not as a remainder: on run 6 this
    population was 14,873 and the artifact could not name it.
    """
    results = _rank(env, ["Backend Engineer", "Platform Engineer"], limit=1)
    assert len(results.visible) == 1
    assert results.hidden_below_cutoff == 1
    assert results.considered == 2


def test_a_title_vetoed_by_the_hard_filters_is_counted(env: Path) -> None:
    """A hard-filter veto used to `continue` with no counter, so it left no trace anywhere."""
    results = _rank(env, ["Backend Engineer", EXCLUDED_TITLE], limit=10)
    assert results.hidden_hard_filter == 1
    assert [posting.title for posting in results.visible] == ["Backend Engineer"]


def test_the_role_gate_and_the_cutoff_are_kept_apart(env: Path) -> None:
    """Two different reasons a posting is not a lead must not collapse into one number."""
    results = _rank(env, ["Backend Engineer", "Platform Engineer", NON_SWE_TITLE], limit=1)
    assert results.hidden_non_swe == 1
    assert results.hidden_below_cutoff == 1


def test_raising_the_limit_moves_postings_out_of_the_cutoff_bucket(env: Path) -> None:
    """Pins the cutoff counter to the limit rather than to a fixed shape of the data.

    Without this, `hidden_below_cutoff` could be hard-coded to `considered - 1` and the test
    above would still pass.
    """
    engine = _seed(env, ["Backend Engineer", "Platform Engineer", "Systems Engineer"])
    settings = _settings(env)
    # Same three postings both times, so only `limit` differs between the two counts.
    assert rank_open_postings(engine, settings, limit=1).hidden_below_cutoff == 2
    assert rank_open_postings(engine, settings, limit=3).hidden_below_cutoff == 0


def test_postings_narrowed_away_by_only_new_are_counted(env: Path) -> None:
    """`--new` narrows the candidate set; the postings it removes are still accounted for.

    No caller in the pipeline passes `only_new`, but the identity above must hold for every
    caller or it is not an identity — and `top --new` is a real one.
    """
    engine = _seed(env, ["Backend Engineer", "Platform Engineer"])
    results = rank_open_postings(engine, _settings(env), limit=10, only_new=True)
    # No posting carries a `new` event past the cursor here, so all of them are narrowed out.
    assert results.skipped_not_new == 2
    assert results.visible == []
    assert _accounted(results) == results.considered == 2
