"""`slate_direct_share`: a share of each ranked tier reserved for leads that apply straight to a
form the owner's fill tool handles. It REORDERS within a tier and nothing else, so every filter,
counter and refill after the sort sees the same postings (the D-650 shape: a filter after a rank
cutoff that does not refill).

Expected orders below are traced by hand from the rule in `interleave_direct`'s docstring, never
produced by calling it.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from sqlalchemy import CursorResult, insert

from boardwatch.cli import top_cmd
from boardwatch.cli.top_cmd import RankedPosting, interleave_direct, rank_open_postings
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings, load_settings
from boardwatch.delivery.apply_routes import ApplyRoute, ApplyRoutes, ApplyRoutesConfig
from boardwatch.rank.heuristic import Score
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine


def _lead(name: str, tier: int) -> RankedPosting:
    """`D...` names are direct, everything else is not; the id is the position in a name list."""
    return RankedPosting(
        posting_id=0, title=name, company="c", score=Score(0.0, {}, 0, 0), why="", tier=tier
    )


def _names(rows: list[RankedPosting]) -> list[str]:
    return [r.title for r in rows]


def _is_direct(r: RankedPosting) -> bool:
    return r.title.startswith("D")


def _tier3(*names: str) -> list[RankedPosting]:
    return [_lead(n, 3) for n in names]


# ---------------------------------------------------------------------------------------------
# interleave_direct
# ---------------------------------------------------------------------------------------------


def test_share_zero_returns_the_identical_order() -> None:
    rows = _tier3("O1", "D1", "O2", "D2")
    assert _names(interleave_direct(rows, _is_direct, 0.0)) == ["O1", "D1", "O2", "D2"]


def test_half_share_alternates_direct_first_then_best_remaining() -> None:
    rows = _tier3("O1", "O2", "O3", "O4", "D1", "D2", "D3", "D4")
    out = interleave_direct(rows, _is_direct, 0.5)
    assert _names(out) == ["D1", "O1", "D2", "O2", "D3", "O3", "D4", "O4"]


def test_quarter_share_gives_one_direct_in_four_and_then_the_leftovers() -> None:
    rows = _tier3("O1", "O2", "O3", "O4", "D1", "D2", "D3", "D4")
    out = interleave_direct(rows, _is_direct, 0.25)
    assert _names(out) == ["D1", "O1", "O2", "O3", "D2", "O4", "D3", "D4"]


def test_full_share_puts_every_direct_lead_first() -> None:
    rows = _tier3("O1", "D1", "O2", "D2")
    assert _names(interleave_direct(rows, _is_direct, 1.0)) == ["D1", "D2", "O1", "O2"]


def test_a_direct_lead_already_ranked_high_is_not_pushed_down() -> None:
    """The quota is a floor. A direct lead that is the best remaining lead takes its natural
    slot, and counts toward the share."""
    rows = _tier3("D1", "D2", "O1", "O2")
    assert _names(interleave_direct(rows, _is_direct, 0.25)) == ["D1", "D2", "O1", "O2"]


def test_a_direct_shortage_leaves_no_gap_and_loses_nothing() -> None:
    rows = _tier3("O1", "O2", "D1", "O3", "O4")
    out = interleave_direct(rows, _is_direct, 1.0)
    assert _names(out) == ["D1", "O1", "O2", "O3", "O4"]
    assert len(out) == len(rows)


def test_no_direct_lead_at_all_is_a_no_op() -> None:
    rows = _tier3("O1", "O2", "O3")
    assert _names(interleave_direct(rows, _is_direct, 1.0)) == ["O1", "O2", "O3"]


def test_only_direct_leads_keep_their_order() -> None:
    rows = _tier3("D1", "D2", "D3")
    assert _names(interleave_direct(rows, _is_direct, 0.5)) == ["D1", "D2", "D3"]


def test_every_lead_appears_exactly_once() -> None:
    rows = [_lead(n, t) for n, t in [
        ("O1", 1), ("D1", 1), ("O2", 1), ("O3", 2), ("D2", 2), ("D3", 3), ("O4", 3), ("D4", 3),
    ]]
    for share in (0.0, 0.1, 0.5, 0.9, 1.0):
        out = interleave_direct(rows, _is_direct, share)
        assert sorted(_names(out)) == sorted(_names(rows))


def test_each_kind_keeps_its_internal_order() -> None:
    rows = _tier3("O1", "D1", "O2", "D2", "O3", "D3", "O4", "D4")
    for share in (0.2, 0.5, 0.8):
        out = _names(interleave_direct(rows, _is_direct, share))
        assert [n for n in out if n.startswith("D")] == ["D1", "D2", "D3", "D4"]
        assert [n for n in out if n.startswith("O")] == ["O1", "O2", "O3", "O4"]


def test_a_lower_tier_direct_lead_never_passes_a_higher_tier_lead() -> None:
    """Tier 0-1 leads are the prefix of the slate (`runner._slate_size`), so the share works
    inside a tier and never across one."""
    rows = [_lead("O1a", 1), _lead("O1b", 1), _lead("D3a", 3), _lead("O3a", 3)]
    out = interleave_direct(rows, _is_direct, 1.0)
    assert _names(out) == ["O1a", "O1b", "D3a", "O3a"]
    assert [r.tier for r in out] == sorted(r.tier for r in rows)


def test_each_tier_gets_its_own_share() -> None:
    rows = [
        _lead("O1a", 1), _lead("O1b", 1), _lead("D1a", 1),
        _lead("O3a", 3), _lead("D3a", 3),
    ]
    out = interleave_direct(rows, _is_direct, 0.5)
    assert _names(out) == ["D1a", "O1a", "O1b", "D3a", "O3a"]


def test_the_quota_counts_positions_within_the_tier_not_the_whole_list() -> None:
    """Three tier-1 leads precede the tier. Counted from the top of the list, tier 3 would owe a
    direct lead for four positions at once and put both directs first; counted inside the tier
    it owes one at position 0 and the next at position 4 (share 0.25)."""
    rows = [_lead(f"O1{c}", 1) for c in "abc"]
    rows += [_lead(n, 3) for n in ("O3a", "O3b", "O3c", "O3d", "D3a", "D3b")]
    out = interleave_direct(rows, _is_direct, 0.25)
    assert _names(out) == [
        "O1a", "O1b", "O1c", "D3a", "O3a", "O3b", "O3c", "D3b", "O3d",
    ]


# ---------------------------------------------------------------------------------------------
# ApplyRoutes.is_direct_auto
# ---------------------------------------------------------------------------------------------


def _routes() -> ApplyRoutes:
    config = ApplyRoutesConfig(
        auto_hosts=("ashbyhq.com", "greenhouse.io"),
        unresolved_hosts=("linkedin.com", "indeed.com"),
        unresolved_url_markers=("gh_jid=",),
        native_fill_hosts=("linkedin.com",),
        no_employer_statuses=("no_employer_link",),
    )
    return ApplyRoutes(config=config, link_status={7: "no_employer_link"}, problem=None)


def test_a_subdomain_of_a_listed_host_is_direct() -> None:
    assert _routes().is_direct_auto("https://jobs.ashbyhq.com/acme/123")


def test_a_host_that_is_not_listed_is_not_direct() -> None:
    assert not _routes().is_direct_auto("https://careers.acme.test/jobs/1")


def test_linkedin_is_not_direct_even_when_it_routes_auto_through_native_fill() -> None:
    routes = _routes()
    url = "https://www.linkedin.com/jobs/view/7"
    assert routes.route(posting_id=7, apply_url=url) is ApplyRoute.AUTO
    assert not routes.is_direct_auto(url)


def test_a_company_page_embedding_an_ats_is_not_direct() -> None:
    assert not _routes().is_direct_auto("https://acme.test/careers?gh_jid=4001")


def test_a_listed_host_on_an_aggregator_path_marker_is_not_direct() -> None:
    assert not _routes().is_direct_auto("https://boards.greenhouse.io/acme/jobs/1?gh_jid=1")


def test_a_missing_or_unreadable_link_is_not_direct() -> None:
    routes = _routes()
    assert not routes.is_direct_auto(None)
    assert not routes.is_direct_auto("not a url")


def test_unconfigured_routes_call_nothing_direct() -> None:
    routes = ApplyRoutes(config=None, link_status={}, problem=None)
    assert not routes.is_direct_auto("https://jobs.ashbyhq.com/acme/123")


# ---------------------------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------------------------


def test_the_setting_defaults_to_off_and_is_range_checked() -> None:
    base = {"data_dir": Path("d"), "config_dir": Path("c")}
    assert Settings(**base).slate_direct_share == 0.0
    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError):
            Settings(**base, slate_direct_share=bad)


# ---------------------------------------------------------------------------------------------
# Through rank_open_postings
# ---------------------------------------------------------------------------------------------

STRONG = "We are hiring a backend engineer to work on Python and PostgreSQL services."
WEAK = "We are hiring a backend engineer to work on Python services."
_INPUT = "3\nacme\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\nsoftware\n"
_ROUTES_TOML = 'auto_hosts = ["ashbyhq.com"]\nunresolved_hosts = ["linkedin.com"]\n'


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _pk(result: CursorResult[Any]) -> int:
    key = result.inserted_primary_key
    assert key is not None
    return int(key[0])


def _seed(data_dir: Path) -> dict[str, int]:
    """Two strongly scored aggregator copies and two weaker direct ones: score alone ranks the
    aggregator copies first. Returns name -> posting id."""
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    engine = get_engine(data_dir)
    ensure_schema(engine)
    now = utcnow()
    spec = {
        "agg1": ("https://www.linkedin.com/jobs/view/1", STRONG),
        "agg2": ("https://www.linkedin.com/jobs/view/2", STRONG),
        "dir1": ("https://jobs.ashbyhq.com/acme/1", WEAK),
        "dir2": ("https://jobs.ashbyhq.com/acme/2", WEAK),
    }
    ids: dict[str, int] = {}
    with engine.begin() as conn:
        for n, (name, (url, body)) in enumerate(spec.items()):
            company_id = _pk(conn.execute(insert(tables.companies).values(
                name=f"Acme{n}", provider="greenhouse", slug=f"acme{n}",
                source="user", watched=False,
            )))
            job_id = _pk(conn.execute(insert(tables.jobs).values(created_at=now)))
            posting_id = _pk(conn.execute(insert(tables.postings).values(
                company_id=company_id, provider_posting_id=f"p-{n}", job_id=job_id,
                title="Backend Engineer", normalized_title="backend engineer", url=url,
                locations_json=["Remote"], remote_policy="remote", first_seen_at=now,
                last_seen_at=now, status="open", consecutive_missing=0,
                content_hash=f"h-{n}", body_text=body,
            )))
            conn.execute(insert(tables.posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{n}", body_text=body,
                captured_at=now, capture_reason="new",
            ))
            ids[name] = posting_id
    cli = CliRunner()
    assert cli.invoke(app, ["--data-dir", str(data_dir), "init"], input=_INPUT).exit_code == 0
    return ids


def _rank(data_dir: Path, share: float, *, limit: int) -> tuple[top_cmd.RankedResults, str]:
    settings = load_settings(data_dir=data_dir).model_copy(update={"slate_direct_share": share})
    buffer = StringIO()
    ranked = rank_open_postings(
        get_engine(data_dir), settings, limit=limit, record_surfaced=False,
        output_console=Console(file=buffer, width=200),
    )
    return ranked, buffer.getvalue()


def _reconciles(r: top_cmd.RankedResults) -> bool:
    return r.considered == (
        len(r.visible) + r.skipped_not_new + r.hidden_hard_filter + r.hidden_non_swe
        + r.hidden_zero_signal + r.hidden_over_seniority + r.hidden_ineligible
        + r.hidden_duplicate + r.hidden_applied + r.hidden_handled + r.hidden_slate_cap
        + r.hidden_cluster_cap + r.hidden_lane_copy + r.hidden_requisition_twin
        + r.hidden_below_cutoff
    )


def test_the_share_reorders_the_slate_and_the_funnel_still_reconciles(env: Path) -> None:
    ids = _seed(env)
    (env.parent / "cfg").mkdir(exist_ok=True)
    (env.parent / "cfg" / "apply-routes.toml").write_text(_ROUTES_TOML)

    off, off_out = _rank(env, 0.0, limit=2)
    # The precondition that makes the next assertions mean something: by score alone the two
    # aggregator copies fill the slate.
    assert {p.posting_id for p in off.visible} == {ids["agg1"], ids["agg2"]}
    assert "slate_direct_share" not in off_out

    full, full_out = _rank(env, 1.0, limit=2)
    assert {p.posting_id for p in full.visible} == {ids["dir1"], ids["dir2"]}
    assert "2 direct of 2 on the ranked slate" in full_out

    half, _ = _rank(env, 0.5, limit=2)
    assert half.visible[0].posting_id in {ids["dir1"], ids["dir2"]}
    assert half.visible[1].posting_id in {ids["agg1"], ids["agg2"]}

    for ranked in (off, full, half):
        assert ranked.considered == 4
        assert _reconciles(ranked)
        assert ranked.hidden_below_cutoff == 4 - len(ranked.visible)


def test_an_unreadable_link_ledger_does_not_turn_the_share_off(env: Path) -> None:
    """`is_direct_auto` reads no ledger, and a ledger mid-rewrite must not change the slate."""
    ids = _seed(env)
    (env.parent / "cfg").mkdir(exist_ok=True)
    missing = env.parent / "cfg" / "missing.json"
    # A TOML literal string ('...'): a Windows path's backslashes are escapes in a "..." string.
    (env.parent / "cfg" / "apply-routes.toml").write_text(
        _ROUTES_TOML + f"\nlink_ledgers = ['{missing}']\n"
    )
    ranked, out = _rank(env, 1.0, limit=2)
    assert {p.posting_id for p in ranked.visible} == {ids["dir1"], ids["dir2"]}
    assert "inert" not in out


def test_without_apply_routes_the_share_is_inert_and_says_so(env: Path) -> None:
    ids = _seed(env)
    ranked, out = _rank(env, 1.0, limit=2)
    assert {p.posting_id for p in ranked.visible} == {ids["agg1"], ids["agg2"]}
    assert "slate_direct_share 1 is inert" in out


def test_an_unreadable_routes_file_leaves_the_order_alone_and_says_so(env: Path) -> None:
    ids = _seed(env)
    (env.parent / "cfg").mkdir(exist_ok=True)
    (env.parent / "cfg" / "apply-routes.toml").write_text("auto_hosts = [")
    ranked, out = _rank(env, 1.0, limit=2)
    assert {p.posting_id for p in ranked.visible} == {ids["agg1"], ids["agg2"]}
    assert "inert" in out
    assert "apply-routes.toml" in out


def test_at_zero_the_routes_file_is_never_read(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(env)

    def boom(_config_dir: Path) -> ApplyRoutes:
        raise AssertionError("load_apply_routes must not run at share 0")

    monkeypatch.setattr(top_cmd, "load_apply_routes", boom)
    ranked, _ = _rank(env, 0.0, limit=2)
    assert len(ranked.visible) == 2


def test_the_share_does_not_move_config_hash_so_no_disposition_goes_stale(tmp_path: Path) -> None:
    """`policy_version` derives from `config_hash`: IN would stale every permanent disposition."""
    from boardwatch.core.settings import Settings
    from boardwatch.reports.manifest import config_hash, routing_hash

    dirs = {"data_dir": tmp_path / "data", "config_dir": tmp_path / "cfg"}
    off = Settings(**dirs, slate_direct_share=0.0)
    on = Settings(**dirs, slate_direct_share=0.5)
    assert config_hash(off) == config_hash(on)
    assert routing_hash(off) != routing_hash(on)


def test_verified_destination_counts_as_direct_while_source_stays_aggregator(env: Path) -> None:
    from boardwatch.store.application_destinations import record_application_destination
    ids = _seed(env)
    (env.parent / "cfg").mkdir(exist_ok=True)
    (env.parent / "cfg" / "apply-routes.toml").write_text(_ROUTES_TOML)
    with get_engine(env).begin() as conn:
        record_application_destination(
            conn, posting_id=ids["agg1"], url="https://jobs.ashbyhq.com/acme/resolved-1",
            source_url="https://www.linkedin.com/jobs/view/1",
            evidence_ref="ledger.json#1", verified_at=utcnow(),
        )
    ranked, out = _rank(env, 1.0, limit=1)
    assert [p.posting_id for p in ranked.visible] == [ids["agg1"]]
    assert "1 direct of 1 on the ranked slate" in out
