"""`boardwatch companies facets` — what a board actually offers to slice on (T75).

Every assertion here defends something a wrong answer costs directly. Until this command the
only way to learn a descriptor's spelling was to guess, watch the scan fail and read the offered
names out of the stored error: descriptors are matched EXACTLY, so a misspelt one becomes a
board that fails every scan forever. Ten live boards were probed on 2026-09-07 and a blanket
`#jobFamilyGroup=Technology` was wrong on seven of them.

The command reaches the network and NOTHING else: no store is opened, so no schema migration
runs and no watched board is needed — an operator must be able to inspect a board before
deciding to watch it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner, Result

from boardwatch.cli.app import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "workday"
SLUG = "acme.wd5.myworkdayjobs.com/acme/AcmeCareers"
LIST_URL = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/jobs"

runner = CliRunner()


def _fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture()
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """A pinned config dir and a tmp data dir with NO store in it at all.

    The data dir is deliberately never initialised: this command must answer without one, and
    the "no file was created" assertion below only means something because nothing pre-creates
    it. `per_host_delay_seconds` is left at its default — one request pays it once.
    """
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    data = tmp_path / "data"

    def invoke(*args: str) -> Result:
        return runner.invoke(app, ["--data-dir", str(data), "companies", "facets", *args])

    invoke.data_dir = data  # type: ignore[attr-defined]
    return invoke


def _payload(result: Result) -> dict[str, Any]:
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def _group(payload: dict[str, Any], parameter: str) -> dict[str, Any]:
    matches = [g for g in payload["groups"] if g["parameter"] == parameter]
    assert matches, f"{parameter} missing from {[g['parameter'] for g in payload['groups']]}"
    return matches[0]


@respx.mock
def test_a_group_nested_inside_another_group_is_reported_not_dropped(cli: Any) -> None:
    """THE ONE THAT MUST FAIL AGAINST A TOP-LEVEL-ONLY WALK.

    Live Citi 2026-09-07 answers a `locationMainGroup` whose values are themselves GROUPS
    (`facetParameter: "locations"`) carrying the buckets, with no id or count of their own. A
    top-level-only read reports `locations` absent — and an absent group is a board-level ERROR
    in the slicing path, so the naive reading makes this command REFUSE a slice the tenant
    really offers. T-Mobile answers THREE such nested groups, not one.
    """
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog.json"))
    )
    payload = _payload(cli(f"workday:{SLUG}", "--all", "--json"))
    locations = _group(payload, "locations")
    assert [b["descriptor"] for b in locations["buckets"]] == ["1 ACME WAY  SPRINGFIELD"]
    assert locations["buckets"][0]["postings"] == 4589
    assert locations["buckets"][0]["target"] == (
        f"workday:{SLUG}#locations=1 ACME WAY  SPRINGFIELD"
    )
    # `locationMainGroup` holds no bucket of its own, so it is not reported as an empty group
    assert "locationMainGroup" not in [g["parameter"] for g in payload["groups"]]
    assert "locationMainGroup" not in payload["groups_withheld"]


@respx.mock
def test_every_bucket_carries_its_count_and_a_copy_pasteable_sliced_slug(cli: Any) -> None:
    """The counts are the actionable part: this board's `Technology` bucket holds 25 of 4,589
    postings, and an operator picks a bucket by size. The slug is spelt out per bucket because
    the descriptor's case and spacing are matched EXACTLY against the live catalog."""
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog.json"))
    )
    payload = _payload(cli(f"workday:{SLUG}", "--json"))
    assert payload["provider"] == "workday"
    assert payload["slug"] == SLUG
    assert _group(payload, "jobFamilyGroup")["buckets"] == [
        # biggest FIRST, which is the whole ordering requirement
        {
            "descriptor": "Operations, Sales & Marketing",
            "postings": 4564,
            "target": f"workday:{SLUG}#jobFamilyGroup=Operations, Sales & Marketing",
        },
        {
            "descriptor": "Technology",
            "postings": 25,
            "target": f"workday:{SLUG}#jobFamilyGroup=Technology",
        },
    ]


@respx.mock
def test_the_opaque_facet_id_is_never_printed(cli: Any) -> None:
    """The id is a tenant-specific hash resolved from the live board on every fetch and stored
    nowhere. Publishing it invites someone to paste it into a slug, where it would mean nothing
    on any other tenant and answer HTTP 400 on this one after a re-index."""
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog.json"))
    )
    human = cli(f"workday:{SLUG}", "--all")
    machine = cli(f"workday:{SLUG}", "--all", "--json")
    assert human.exit_code == 0 and machine.exit_code == 0
    assert "3f2c9a1e708d01575bddff0c12010001" not in human.output
    assert "3f2c9a1e708d01575bddff0c12010001" not in machine.output


@respx.mock
def test_the_group_is_found_whatever_the_tenant_spells_it(cli: Any) -> None:
    """MEASURED 2026-09-07: NVIDIA answers `jobFamilyGroup` and T-Mobile answers
    `Job_Family_Group` for the same dimension. Matching the literal spelling would hide the
    ONLY sliceable group T-Mobile has, and the default view would report the board unsliceable
    when its 30-posting IT bucket is right there."""
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog_underscored.json"))
    )
    payload = _payload(cli(f"workday:{SLUG}", "--json"))
    assert [g["parameter"] for g in payload["groups"]] == ["Job_Family_Group"]
    assert _group(payload, "Job_Family_Group")["sliceable"] is True
    assert [b["postings"] for b in _group(payload, "Job_Family_Group")["buckets"]] == [
        1902, 259, 30
    ]


@respx.mock
def test_the_default_view_withholds_the_noisy_groups_and_all_prints_them(cli: Any) -> None:
    """The bound. One live tenant answers 1,091 `locations` buckets and 51 provinces beside the
    one group that decides which roles a slice holds, so a full dump buries the useful line.
    Withheld groups are NAMED and counted, never silently dropped."""
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog_underscored.json"))
    )
    default = _payload(cli(f"workday:{SLUG}", "--json"))
    assert default["groups_withheld"] == [
        "timeType", "locationCountry", "locations", "locationRegionStateProvince", "distance",
    ]
    every = _payload(cli(f"workday:{SLUG}", "--all", "--json"))
    assert every["groups_withheld"] == []
    # sliceable first even under --all, so it is never printed below a province list
    assert [g["parameter"] for g in every["groups"]][0] == "Job_Family_Group"
    assert {g["parameter"] for g in every["groups"]} == {
        "Job_Family_Group", "timeType", "locationCountry", "locations",
        "locationRegionStateProvince", "distance",
    }
    human = cli(f"workday:{SLUG}")
    assert human.exit_code == 0
    assert "5 group(s) not shown" in human.output
    assert "--all prints them" in human.output


@respx.mock
def test_a_board_with_nothing_worth_slicing_says_so(cli: Any) -> None:
    """A real, actionable answer, not an error: one live board (Abbott, 2026-09-07) offers no
    group holding engineering at all. Here the board offers no job-family group whatsoever, so
    the default view has nothing to show and has to say that rather than print an empty table
    that reads like "this board has no facets"."""
    trimmed = dict(_fx("list_facet_catalog_underscored.json"))
    trimmed["facets"] = [
        g for g in trimmed["facets"] if g.get("facetParameter") != "Job_Family_Group"
    ]
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=trimmed))
    human = cli(f"workday:{SLUG}")
    assert human.exit_code == 0, human.output
    assert "Nothing worth slicing" in human.output
    assert _payload(cli(f"workday:{SLUG}", "--json"))["groups"] == []


@respx.mock
def test_a_slug_that_already_names_a_slice_is_answered_for_the_whole_board(cli: Any) -> None:
    """The catalog is a property of the BOARD. A filtered response re-aggregates its facets over
    the slice, so answering a sliced slug with the slice's own counts would hand an operator
    comparing buckets the wrong numbers. The fragment is dropped and the suggested slugs are
    spelt off the bare triple."""
    route = respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog.json"))
    )
    payload = _payload(cli(f"workday:{SLUG}#jobFamilyGroup=Technology", "--json"))
    assert payload["slug"] == SLUG
    assert _group(payload, "jobFamilyGroup")["buckets"][0]["target"].startswith(
        f"workday:{SLUG}#"
    )
    # one unfiltered request, and its body carries no applied facet
    assert route.call_count == 1
    assert json.loads(route.calls[0].request.content)["appliedFacets"] == {}


@respx.mock
def test_a_printed_slug_survives_brackets_and_a_narrow_terminal_intact(cli: Any) -> None:
    """The printed slug is the deliverable, so rich must not touch it. Two live-plausible
    descriptors break the naive rendering: one carrying `[` (rich reads it as markup and eats
    it) and one longer than the terminal (rich word-wraps and crops, and a slug broken across
    lines is not copy-pasteable). Both go out verbatim, on ONE line each."""
    bracketed = "Technology [EMEA]"
    long = "Software Engineering, Architecture and Site Reliability, Group and Subsidiaries"
    payload = {
        "total": 3,
        "jobPostings": [],
        "facets": [{"facetParameter": "jobFamilyGroup", "values": [
            {"id": "aa01", "descriptor": bracketed, "count": 2},
            {"id": "aa02", "descriptor": long, "count": 1},
        ]}],
    }
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    result = cli(f"workday:{SLUG}")
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    for descriptor in (bracketed, long):
        wanted = f"workday:{SLUG}#jobFamilyGroup={descriptor}"
        assert any(line.strip().endswith(wanted) for line in lines), (descriptor, result.output)


@pytest.mark.parametrize(
    ("target", "named"),
    [
        ("greenhouse:acme", "greenhouse"),
        ("https://boards.greenhouse.io/acme", "greenhouse"),
        ("lever:acme", "lever"),
    ],
)
def test_a_non_workday_board_exits_non_zero_with_a_named_reason(
    cli: Any, target: str, named: str
) -> None:
    """Only Workday can be sliced today. An empty table would read as "this board has no
    facets" — a different and false claim, and the one an unattended agent would act on."""
    result = cli(target)
    assert result.exit_code == 1, result.output
    assert named in result.output
    assert "cannot be sliced by facet" in result.output
    assert "workday" in result.output


def test_an_unrecognized_target_exits_non_zero_without_reaching_the_network(cli: Any) -> None:
    result = cli("not a board at all")
    assert result.exit_code == 1, result.output


@respx.mock
def test_a_board_that_answers_no_json_exits_non_zero(cli: Any) -> None:
    # A live Workday host can answer 200 with an HTML maintenance page (observed on one
    # tenant), which must be a named refusal rather than a traceback or an empty table.
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, content=b"<html>down</html>"))
    result = cli(f"workday:{SLUG}")
    assert result.exit_code == 1, result.output
    assert "facet catalog" in result.output


@respx.mock
def test_it_opens_no_store_so_it_needs_no_watched_board_and_migrates_nothing(cli: Any) -> None:
    """The `pure`-adjacent half of the contract. `build_context` would run `alembic upgrade
    head` on a production database as a side effect of asking what a board offers (D-279), and
    the operator has not decided to watch this board yet — there may be no store at all."""
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog.json"))
    )
    result = cli(f"workday:{SLUG}", "--json")
    assert result.exit_code == 0, result.output
    data_dir: Path = cli.data_dir
    assert not list(data_dir.rglob("*.db")), sorted(p.name for p in data_dir.rglob("*"))


@respx.mock
def test_under_json_stdout_carries_one_object_and_nothing_else(cli: Any) -> None:
    """The pipe contract every `--json` command here honours: a readable note leaking onto
    stdout fails this by itself, because `json.loads` runs on the WHOLE of stdout."""
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=_fx("list_facet_catalog_underscored.json"))
    )
    result = runner.invoke(
        app,
        ["--data-dir", str(cli.data_dir), "companies", "facets", f"workday:{SLUG}", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert isinstance(json.loads(result.stdout), dict)
