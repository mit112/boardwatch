"""The ranker gates the shortlist on seniority, and reports what it could not decide (D-246).

Three properties, and the third is the one that is easy to lose:

1. A title confidently above the target band lands in `hidden_over_seniority`, its own bucket,
   never folded into `hidden_hard_filter` or a low score.
2. `--include-over-seniority` drains that bucket **without consuming the queue**. A drain that
   writes `seen` is a re-entry path that closes behind you: looking into the quarantine would
   suppress those jobs from every run inside the TTL.
3. An unresolvable level token is `uncertain` — counted and passed through **visible**, and
   deliberately NOT part of the reconciliation identity, because those postings are already
   accounted for in `visible` and adding them would double-count.

Fixtures are local rather than in `tests/conftest.py`, following this suite's convention: every
top-ranker suite seeds its own corpus, and `tests/unit/test_top_accounting.py` is the model.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.cli.top_cmd import rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = utcnow()

# `staff` is a field-tier word: universal, certain, and it needs no company binding, so this
# title is the one shape the gate is allowed to DROP on.
OVER_BAND_TITLE = "Staff Software Engineer"
# A self-describing level token with no scheme bound for the company. The gate can see that it
# is a level and cannot say which band it means, so it abstains — the keystone case.
UNBOUND_LEVEL_TITLE = "Software Engineer, Specs, Level 5"
ORDINARY_TITLES = ["Backend Engineer", "Platform Engineer"]
# The role gate reads this as non-software. Its drain had the same queue-consuming defect.
NON_SWE_TITLE = "Deal Strategist"


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Config dir == data dir, so the leveling catalog, the bindings file and the store are all
    # read from one place. No `leveling-bindings.yaml` is written, which is what makes
    # UNBOUND_LEVEL_TITLE abstain rather than resolve.
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


@pytest.fixture()
def settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, config_dir=data_dir)


@pytest.fixture()
def engine(data_dir: Path) -> Engine:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    return engine


@pytest.fixture()
def seed(engine: Engine) -> Callable[[list[str]], None]:
    """One company, one open posting per title, `target_seniority_band="entry"`.

    The band is what arms the gate: at the shipped default of `any` it is inert and every
    assertion here would pass vacuously.
    """

    def _seed(titles: list[str]) -> None:
        with engine.begin() as conn:
            save_profile(
                conn, text="Backend engineer.", target_titles=[], exclude_titles=["intern"],
                locations=[], remote_only=False, skills=[], taxonomy_version="t",
                resume_max_pages=1, target_seniority_band="entry",
            )
            company_id = int(conn.execute(insert(companies).values(
                name="Acme", provider="greenhouse", slug="acme-acct",
                source="user", watched=True,
            )).inserted_primary_key[0])
            for offset, title in enumerate(titles):
                job_id = int(
                    conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0]
                )
                posting_id = int(conn.execute(insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{offset}",
                    title=title, normalized_title=title.casefold(),
                    locations_json=["Remote"], remote_policy="remote",
                    posted_at=NOW - timedelta(days=offset), first_seen_at=NOW, last_seen_at=NOW,
                    status="open", consecutive_missing=0, content_hash=f"hh-{offset}",
                    body_text="b",
                )).inserted_primary_key[0])
                conn.execute(insert(posting_versions).values(
                    posting_id=posting_id, content_hash=f"hh-{offset}", body_text="b",
                    captured_at=NOW, capture_reason="new",
                ))

    return _seed


@pytest.fixture()
def seeded_senior_posting(seed: Callable[[list[str]], None]) -> None:
    seed([OVER_BAND_TITLE])


@pytest.fixture()
def seeded_unbound_level_posting(seed: Callable[[list[str]], None]) -> None:
    seed([UNBOUND_LEVEL_TITLE])


@pytest.fixture()
def seeded_mixed(seed: Callable[[list[str]], None]) -> None:
    seed([OVER_BAND_TITLE, UNBOUND_LEVEL_TITLE, *ORDINARY_TITLES])


def test_above_band_postings_land_in_their_own_bucket(
    engine: Engine, settings: Settings, seeded_senior_posting: None
) -> None:
    r = rank_open_postings(engine, settings, limit=50)
    assert r.hidden_over_seniority == 1
    assert all(p.title != OVER_BAND_TITLE for p in r.visible)


def test_the_drain_reveals_them(
    engine: Engine, settings: Settings, seeded_senior_posting: None
) -> None:
    r = rank_open_postings(engine, settings, limit=50, include_over_seniority=True)
    assert any(p.title == OVER_BAND_TITLE for p in r.visible)


def test_the_drained_row_carries_the_text_that_vetoed_it(
    engine: Engine, settings: Settings, seeded_senior_posting: None
) -> None:
    """A veto you cannot read is a silent drop wearing a counter."""
    r = rank_open_postings(engine, settings, limit=50, include_over_seniority=True)
    drained = next(p for p in r.visible if p.title == OVER_BAND_TITLE)
    assert drained.band == "above_band"
    assert "staff" in drained.band_reason


def test_the_drain_does_not_consume_the_queue(
    engine: Engine, settings: Settings, seeded_senior_posting: None
) -> None:
    """A drain that records `seen` is a re-entry path that closes behind you."""
    r = rank_open_postings(engine, settings, limit=50, include_over_seniority=True)
    drained = [p for p in r.visible if p.title == OVER_BAND_TITLE]
    assert drained
    assert all(p.posting_id not in r.surfaced_job_ids for p in drained)


def test_the_non_swe_drain_does_not_consume_the_queue_either(
    engine: Engine, settings: Settings, seed: Callable[[list[str]], None]
) -> None:
    """The same defect existed for `--include-non-swe` and is fixed in the same change.

    Lives in this file rather than beside the role gate because the fix is one condition shared
    by both drains: a test that only covered the seniority half would let the other regress.
    """
    seed([NON_SWE_TITLE])
    r = rank_open_postings(engine, settings, limit=50, include_non_swe=True)
    drained = [p for p in r.visible if p.title == NON_SWE_TITLE]
    assert drained
    assert r.surfaced_job_ids == ()


def test_uncertain_is_counted_but_never_dropped(
    engine: Engine, settings: Settings, seeded_unbound_level_posting: None
) -> None:
    r = rank_open_postings(engine, settings, limit=50)
    assert r.uncertain_band == 1
    assert any(p.title == UNBOUND_LEVEL_TITLE for p in r.visible)


def test_the_accounting_identity_holds_with_the_new_bucket(
    engine: Engine, settings: Settings, seeded_mixed: None
) -> None:
    r = rank_open_postings(engine, settings, limit=5)
    accounted = (
        len(r.visible) + r.skipped_not_new + r.hidden_hard_filter + r.hidden_non_swe
        + r.hidden_over_seniority + r.hidden_ineligible + r.hidden_below_cutoff
        + r.hidden_duplicate + r.hidden_handled + r.hidden_applied
    )
    assert r.hidden_over_seniority == 1
    assert r.considered == accounted


def test_uncertain_band_is_not_part_of_the_identity(
    engine: Engine, settings: Settings, seeded_unbound_level_posting: None
) -> None:
    """It is a REPORTED counter, not a drop — folding it in would break reconciliation."""
    r = rank_open_postings(engine, settings, limit=50)
    assert r.uncertain_band == 1
    assert r.considered == (
        len(r.visible) + r.skipped_not_new + r.hidden_hard_filter + r.hidden_non_swe
        + r.hidden_over_seniority + r.hidden_ineligible + r.hidden_below_cutoff
        + r.hidden_duplicate + r.hidden_handled + r.hidden_applied
    )


def test_the_gate_is_inert_at_the_shipped_default(
    engine: Engine, settings: Settings, seed: Callable[[list[str]], None]
) -> None:
    """`target_seniority_band="any"` must change nothing, or every existing install regresses.

    Pinned here because every other test in this file arms the gate; without this one, a change
    that made the gate fire unconditionally would look correct.
    """
    seed([OVER_BAND_TITLE, UNBOUND_LEVEL_TITLE])
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=["intern"],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1, target_seniority_band="any",
        )
    r = rank_open_postings(engine, settings, limit=50)
    assert r.hidden_over_seniority == 0
    assert r.uncertain_band == 0
    assert {p.title for p in r.visible} == {OVER_BAND_TITLE, UNBOUND_LEVEL_TITLE}


def _disarm(engine) -> None:
    """Set the band back to the shipped default so the gate goes inert."""
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=["intern"],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1, target_seniority_band="any",
        )


def test_an_inert_gate_reports_what_it_declined_to_act_on(engine, settings, seeded_senior_posting):
    """`any` is the shipped default, so silence here means nobody ever learns the gate exists.

    The verdict short-circuits on `any` BEFORE parsing, so `hidden_over_seniority` and
    `uncertain_band` are structurally 0 on this path — this counter is the only signal, and
    without it "inert" is indistinguishable from "nothing to gate".
    """
    _disarm(engine)
    r = rank_open_postings(engine, settings, limit=50)
    assert r.hidden_over_seniority == 0          # inert: nothing is dropped
    assert r.uncertain_band == 0                 # and nothing abstains either
    assert r.band_tokens_seen_while_inert == 1   # but it SAW the `staff` in the title
    assert any(p.title == OVER_BAND_TITLE for p in r.visible)


def test_the_inert_counter_stays_zero_once_a_band_is_set(engine, settings, seeded_senior_posting):
    """Otherwise the notice would misfire on every armed run."""
    r = rank_open_postings(engine, settings, limit=50)   # fixture arms it at `entry`
    assert r.band_tokens_seen_while_inert == 0
    assert r.hidden_over_seniority == 1


def test_an_inert_gate_is_quiet_when_there_was_nothing_to_say(engine, settings, seed):
    """No signal, no notice — the report must not nag about a corpus it had no opinion on."""
    seed(ORDINARY_TITLES)
    _disarm(engine)
    r = rank_open_postings(engine, settings, limit=50)
    assert r.band_tokens_seen_while_inert == 0
