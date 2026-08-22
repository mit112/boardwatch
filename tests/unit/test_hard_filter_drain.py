"""The hard filter must say WHICH clause vetoed and on WHAT text.

`passes_hard_filters` returns a bare bool, so all four of its veto clauses collapse into one
`hidden_hard_filter` counter with no reason attached — 17,891 drops on run 67, 59% of the corpus,
and the only bucket a human cannot inspect. These tests pin the reason-carrying sibling that makes
a drain possible: `hard_filter_verdict` returns the veto, `passes_hard_filters` stays a thin
wrapper over it so the two can never disagree about the same title.
"""

from boardwatch.rank.heuristic import (
    ProfileView,
    hard_filter_verdict,
    passes_hard_filters,
)


def _profile(**overrides: object) -> ProfileView:
    base: dict[str, object] = {
        "skills": frozenset({"Python"}),
        "target_titles": ("Backend Engineer",),
        "exclude_titles": (),
        "locations": ("New York",),
        "remote_only": False,
    }
    base.update(overrides)
    return ProfileView(**base)  # type: ignore[arg-type]


class TestTheVerdictNamesTheClause:
    def test_a_cleared_title_has_no_veto(self) -> None:
        profile = _profile(exclude_titles=("Senior",))
        assert hard_filter_verdict("Backend Engineer", ["NY"], "unknown", profile, "soft") is None

    def test_an_excluded_title_names_the_token_that_matched(self) -> None:
        profile = _profile(exclude_titles=("Senior", "Manager"))
        veto = hard_filter_verdict("Senior Software Engineer", ["NY"], "unknown", profile, "soft")
        assert veto is not None
        assert veto.clause == "excluded_title"
        # The drain's whole purpose: which of the 16 entries cost you this posting.
        assert veto.detail == "Senior"

    def test_a_non_us_location_names_the_place_that_decided(self) -> None:
        veto = hard_filter_verdict(
            "Backend Engineer", ["London, United Kingdom"], "unknown", _profile(), "hard"
        )
        assert veto is not None
        assert veto.clause == "non_us_location"
        assert "London, United Kingdom" in veto.detail

    def test_a_foreign_ad_marker_on_the_title_is_its_own_clause(self) -> None:
        veto = hard_filter_verdict(
            "Ingénieur Logiciel (H/F)", ["Remote"], "remote", _profile(), "hard"
        )
        assert veto is not None
        assert veto.clause == "foreign_ad_marker"

    def test_a_remote_only_profile_vetoing_an_onsite_role_is_its_own_clause(self) -> None:
        veto = hard_filter_verdict(
            "Backend Engineer", ["NY"], "unknown", _profile(remote_only=True), "hard"
        )
        assert veto is not None
        assert veto.clause == "remote_only"


class TestTheBoolStaysTheSameFunction:
    """A wrapper, not a copy — otherwise the two drift and the drain lies about the drop."""

    def test_the_bool_agrees_with_the_verdict_on_every_clause(self) -> None:
        cases = [
            ("Senior Software Engineer", ["NY"], "unknown", _profile(exclude_titles=("Senior",)), "soft"),
            ("Backend Engineer", ["NY"], "unknown", _profile(), "soft"),
            ("Backend Engineer", ["London, United Kingdom"], "unknown", _profile(), "hard"),
            ("Backend Engineer", ["San Francisco"], "unknown", _profile(), "hard"),
            ("Ingénieur Logiciel (H/F)", ["Remote"], "remote", _profile(), "hard"),
            ("Backend Engineer", ["NY"], "unknown", _profile(remote_only=True), "hard"),
        ]
        for title, locs, remote, profile, mode in cases:
            passed = passes_hard_filters(title, locs, remote, profile, mode)
            verdict = hard_filter_verdict(title, locs, remote, profile, mode)
            assert passed is (verdict is None), (title, mode, verdict)

    def test_soft_mode_never_vetoes_on_a_location_clause(self) -> None:
        # The three hard-mode clauses are gated as a group; soft mode leaves only exclude_titles.
        for locs in (["London, United Kingdom"], ["Buc"], ["Remote"]):
            assert hard_filter_verdict("Backend Engineer", locs, "unknown", _profile(), "soft") is None


# --------------------------------------------------------------------------------------
# The drain itself. Fixtures are local, following this suite's convention
# (tests/unit/test_top_seniority_gate.py is the model).
# --------------------------------------------------------------------------------------

from collections.abc import Callable  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import Engine, insert  # noqa: E402

from boardwatch.cli.top_cmd import rank_open_postings  # noqa: E402
from boardwatch.core.clock import utcnow  # noqa: E402
from boardwatch.core.settings import Settings  # noqa: E402
from boardwatch.store.db import ensure_schema, get_engine  # noqa: E402
from boardwatch.store.queries import save_profile  # noqa: E402
from boardwatch.store.tables import companies, jobs, posting_versions, postings  # noqa: E402

NOW = utcnow()

EXCLUDED_TOKEN = "Senior"
EXCLUDED_TITLE = "Senior Software Engineer"
ORDINARY_TITLES = ["Backend Engineer", "Platform Engineer"]


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
    """One company, one open posting per title, `exclude_titles=["Senior"]`.

    The exclusion is what arms clause 1 -- with an empty `exclude_titles` every assertion
    below would pass vacuously.
    """

    def _seed(titles: list[str]) -> None:
        with engine.begin() as conn:
            save_profile(
                conn, text="Backend engineer.", target_titles=[],
                exclude_titles=[EXCLUDED_TOKEN], locations=[], remote_only=False, skills=[],
                taxonomy_version="t", resume_max_pages=1, target_seniority_band="any",
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


def test_an_excluded_title_lands_in_the_bucket(
    engine: Engine, settings: Settings, seed: Callable[[list[str]], None]
) -> None:
    seed([EXCLUDED_TITLE])
    r = rank_open_postings(engine, settings, limit=50)
    assert r.hidden_hard_filter == 1
    assert all(p.title != EXCLUDED_TITLE for p in r.visible)


def test_the_drain_reveals_them(
    engine: Engine, settings: Settings, seed: Callable[[list[str]], None]
) -> None:
    seed([EXCLUDED_TITLE])
    r = rank_open_postings(engine, settings, limit=50, include_hard_filter=True)
    assert any(p.title == EXCLUDED_TITLE for p in r.visible)
    # Drained, not re-counted -- otherwise the reconciliation identity double-counts it.
    assert r.hidden_hard_filter == 0


def test_the_drained_row_names_the_clause_and_the_token_that_vetoed_it(
    engine: Engine, settings: Settings, seed: Callable[[list[str]], None]
) -> None:
    """The whole point of the drain: which of the profile's entries cost you this posting."""
    seed([EXCLUDED_TITLE])
    r = rank_open_postings(engine, settings, limit=50, include_hard_filter=True)
    drained = next(p for p in r.visible if p.title == EXCLUDED_TITLE)
    assert drained.hard_filter == "excluded_title"
    assert EXCLUDED_TOKEN in drained.hard_filter_reason


def test_the_drained_row_says_so_in_its_why_cell(
    engine: Engine, settings: Settings, seed: Callable[[list[str]], None]
) -> None:
    """A drained row must never read as an ordinary lead in the table."""
    from boardwatch.cli.top_cmd import _why_cell  # noqa: PLC0415

    seed([EXCLUDED_TITLE])
    r = rank_open_postings(engine, settings, limit=50, include_hard_filter=True)
    drained = next(p for p in r.visible if p.title == EXCLUDED_TITLE)
    assert EXCLUDED_TOKEN in _why_cell(drained)


def test_the_drain_does_not_consume_the_queue(
    engine: Engine, settings: Settings, seed: Callable[[list[str]], None]
) -> None:
    """A drain that records `seen` is a re-entry path that closes behind you (D-110)."""
    seed([EXCLUDED_TITLE])
    r = rank_open_postings(engine, settings, limit=50, include_hard_filter=True)
    drained = [p for p in r.visible if p.title == EXCLUDED_TITLE]
    assert drained
    assert r.surfaced_job_ids == ()


def test_the_drain_is_not_bounded_by_the_rank_cutoff(
    engine: Engine, settings: Settings, seed: Callable[[list[str]], None]
) -> None:
    """Mit's ruling: unbounded. An audit that silently truncates is the measurement error this
    project has already paid for twice, and 59% of the corpus is exactly where it would hide."""
    seed([EXCLUDED_TITLE, "Senior Platform Engineer", "Senior Data Engineer"])
    r = rank_open_postings(engine, settings, limit=1, include_hard_filter=True)
    assert len(r.visible) == 3
    assert r.hidden_below_cutoff == 0


def test_the_accounting_identity_holds_with_the_drain_open(
    engine: Engine, settings: Settings, seed: Callable[[list[str]], None]
) -> None:
    seed([EXCLUDED_TITLE, *ORDINARY_TITLES])
    for drained in (False, True):
        # `record_surfaced=False` so the two passes are independent: a recording pass writes
        # `seen` for the ordinary rows, and the next pass would then count them as
        # `hidden_handled`. The identity holds either way -- this keeps the test reading
        # about the drain rather than about the ledger.
        r = rank_open_postings(
            engine, settings, limit=50, include_hard_filter=drained, record_surfaced=False
        )
        # All TEN terms, per RankedResults' own docstring. An eight-term version of this sum
        # passes vacuously whenever handled/applied happen to be 0 in the fixture.
        accounted = (
            len(r.visible) + r.skipped_not_new + r.hidden_hard_filter + r.hidden_non_swe
            + r.hidden_over_seniority + r.hidden_ineligible + r.hidden_duplicate
            + r.hidden_applied + r.hidden_handled + r.hidden_below_cutoff
        )
        assert accounted == r.considered, (drained, r)


def test_the_operator_summary_line_names_the_bucket(engine: Engine) -> None:
    """Mit's ruling: once the bucket is drainable, the one-line summary names it. It is the
    largest cut in the pipeline and was the only one absent from the operator's daily line."""
    from boardwatch.cli.run_cmd import _shortlist_line  # noqa: PLC0415
    from boardwatch.pipeline.runner import PipelineSummary  # noqa: PLC0415
    from boardwatch.reports.run_funnel import ShortlistCounts  # noqa: PLC0415

    summary = PipelineSummary(run_id=1)
    summary.shortlist = ShortlistCounts(
        considered=100, shortlisted=1, hidden_hard_filter=59,
    )
    assert "59 hard-filtered" in _shortlist_line(summary)
