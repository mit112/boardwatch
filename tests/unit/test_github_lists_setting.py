"""T188 (DESIGN-T183 E2/N2): which public GitHub lists are read is the `lane_github_lists` setting.

Before this the two new-grad software lists were `github_lists.LIST_REPOS`, read for every tenant.
The setting defaults to empty, and empty fetches nothing and says `no_lists`.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from github_lists_shape import S1_REPO, S2_REPO, listings
from pydantic import ValidationError
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import Settings
from boardwatch.lanes.base import LaneContext
from boardwatch.lanes.facets import LaneFacets
from boardwatch.lanes.github_lists import fetch_listings, list_urls
from boardwatch.lanes.jsonld import JsonLdLane
from boardwatch.pipeline.runner import LANE_FACTORIES
from tests.unit.test_jsonld_lane import _Admits, _fetcher, _Reader

LISTS = (S1_REPO, S2_REPO)


def test_the_setting_is_empty_by_default_and_refuses_a_non_pair(tmp_path: Path) -> None:
    assert Settings(data_dir=tmp_path, config_dir=tmp_path).lane_github_lists == ()
    for bad in ("SimplifyJobs", "a/b/c", "owner/../x/y", "https://github.com/a/b"):
        with pytest.raises(ValidationError, match="owner/repo"):
            Settings(data_dir=tmp_path, config_dir=tmp_path, lane_github_lists=(bad,))


def test_two_configured_lists_are_both_read(tmp_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        for (_repo, url), shape in zip(list_urls(LISTS), ("S1", "S2"), strict=True):
            router.get(url).mock(return_value=httpx.Response(200, json=listings(shape)))
        sources = fetch_listings(_fetcher(tmp_path), LISTS)
    assert list(sources) == [S1_REPO, S2_REPO]
    assert all(sources.values())


def test_no_configured_list_reads_nothing(tmp_path: Path) -> None:
    with respx.mock(assert_all_mocked=True) as router:
        assert fetch_listings(_fetcher(tmp_path), ()) == {}
        assert router.calls.call_count == 0


def test_the_jsonld_lane_reports_no_lists_and_requests_none(tmp_path: Path) -> None:
    with respx.mock(assert_all_mocked=True) as router:
        result = JsonLdLane(_Reader(()), list_repos=()).collect(_fetcher(tmp_path), _Admits())
        assert router.calls.call_count == 0
    assert result.not_attemptable == "no_lists"


def test_the_jsonld_lane_reads_both_configured_lists(tmp_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        routes = [
            router.get(url).mock(return_value=httpx.Response(200, text="[]"))
            for _repo, url in list_urls(LISTS)
        ]
        result = JsonLdLane(_Reader(()), list_repos=LISTS).collect(_fetcher(tmp_path), _Admits())
    assert [route.call_count for route in routes] == [1, 1]
    assert result.not_attemptable is None


def test_the_registry_hands_the_jsonld_lane_the_setting(tmp_path: Path) -> None:
    built = LANE_FACTORIES["jsonld"](
        LaneContext(
            settings=Settings(data_dir=tmp_path, config_dir=tmp_path, lane_github_lists=LISTS),
            facets=LaneFacets(), rotation_index=0,
        )
    )
    assert isinstance(built, JsonLdLane)
    assert built._list_repos == LISTS


def test_companies_discover_with_no_list_fetches_nothing_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with respx.mock(assert_all_mocked=True) as router:
        result = CliRunner().invoke(
            app, ["--data-dir", str(tmp_path / "data"), "companies", "discover"]
        )
        assert router.calls.call_count == 0
    assert result.exit_code == 1, result.stdout
    assert "not attemptable (no_lists)" in result.stdout
