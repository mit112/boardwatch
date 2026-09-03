"""The `grnh.se` seed resolver: what it resolves, what it refuses, and what it never writes.

Every test here goes through a REAL `Fetcher` against `respx`-mocked transport, the same harness
`test_jsonld_lane.py` uses and for the same reason: the redirect-following, the per-host lock and
the `FetchFailure` classification are all in the path being tested. A stub returning a canned
`FetchResult` would pass while the client that has to follow the redirect was never exercised.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
import yaml

from boardwatch.core.clock import utcnow
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes.grnh_seeds import candidate_document, resolve, without_known
from boardwatch.registry.validate import CompanyEntry
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.seed_queries import LaneSeed, record_seeds

BOARD = "https://job-boards.greenhouse.io/speechify/jobs/4567890"


def _fetcher(tmp_path: Path) -> Fetcher:
    """A real `Fetcher` at the pacing FLOOR, with redirect-following ON as production has it."""
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        ),
        client=httpx.Client(timeout=5.0, follow_redirects=True),
    )


def _seed(token: str, seed_id: int = 1) -> LaneSeed:
    return LaneSeed(
        id=seed_id, url=f"https://grnh.se/{token}", host="grnh.se",
        discovered_by="indeed", attempts=0,
    )


def _redirect(router: respx.Router, token: str, target: str) -> None:
    router.get(f"https://grnh.se/{token}").mock(
        return_value=httpx.Response(302, headers={"Location": target})
    )
    router.get(target).mock(return_value=httpx.Response(200, text="ok"))


@respx.mock
def test_a_seed_resolves_to_the_board_behind_its_redirect(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """The DESTINATION names the board; the seed URL names nothing.

    Non-vacuous by construction: `parse_board_target` RAISES on `grnh.se/<token>`, so an
    implementation that read `seed.url` instead of the redirect target resolves zero boards here
    rather than merely mislabelling one.
    """
    _redirect(respx_mock, "abc123", BOARD)

    result = resolve((_seed("abc123"),), _fetcher(tmp_path))

    assert [(b.provider, b.slug) for b in result.boards] == [("greenhouse", "speechify")]
    assert result.boards[0].final_url == BOARD
    assert result.census.resolved == 1
    assert result.census.off_board == 0
    assert result.census.failed == 0


@respx.mock
def test_seeds_sharing_one_board_collapse_to_a_single_candidate(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """MEASURED: ~1.3 seeds per board, and `speechify` alone carried 4 of the 12 sampled.

    Without the dedupe this proposes the same board once per seed, so a reviewer reads four
    identical rows and `companies import` upserts the same watch repeatedly.
    """
    _redirect(respx_mock, "one", BOARD)
    _redirect(respx_mock, "two", "https://job-boards.greenhouse.io/speechify/jobs/999")

    result = resolve((_seed("one", 1), _seed("two", 2)), _fetcher(tmp_path))

    assert [(b.provider, b.slug) for b in result.boards] == [("greenhouse", "speechify")]
    assert result.census.seeds_read == 2
    assert result.census.resolved == 1


@respx.mock
def test_a_destination_that_is_not_a_supported_board_is_counted_not_dropped(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """A short link may point anywhere. Counting it is what keeps the census honest."""
    _redirect(respx_mock, "elsewhere", "https://careers.example.com/jobs/1")

    result = resolve((_seed("elsewhere"),), _fetcher(tmp_path))

    assert result.boards == ()
    assert result.census.off_board == 1
    assert result.census.failed == 0


@respx.mock
def test_one_dead_link_does_not_discard_the_boards_resolved_beside_it(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """A pass aborting on the first 500 loses every board already resolved in it.

    Ordered dead-first deliberately: with the failure LAST, an implementation that aborts still
    returns the good board and the test passes against the broken version.
    """
    respx_mock.get("https://grnh.se/dead").mock(return_value=httpx.Response(500))
    _redirect(respx_mock, "live", BOARD)

    result = resolve((_seed("dead", 1), _seed("live", 2)), _fetcher(tmp_path))

    assert [(b.provider, b.slug) for b in result.boards] == [("greenhouse", "speechify")]
    assert result.census.failed == 1
    assert result.census.resolved == 1


@respx.mock
def test_the_fetch_result_carries_the_redirect_target_not_the_requested_url(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """Pins the `FetchResult.final_url` contract this resolver rests on.

    Asserted against the REQUESTED url as a literal: `final_url` defaults to `""`, so a client
    that stopped populating it would leave this equal to neither and fail.
    """
    _redirect(respx_mock, "abc123", BOARD)

    result = _fetcher(tmp_path).get("https://grnh.se/abc123")

    assert result.final_url == BOARD
    assert result.final_url != "https://grnh.se/abc123"


@respx.mock
def test_the_candidate_file_validates_as_the_registry_format_import_accepts(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """The file's whole purpose is to survive `companies import`'s validator."""
    _redirect(respx_mock, "abc123", BOARD)
    result = resolve((_seed("abc123"),), _fetcher(tmp_path))

    document = candidate_document(result, generated_on=date(2026, 9, 2))
    parsed = yaml.safe_load(document)

    assert [CompanyEntry.model_validate(row).slug for row in parsed["companies"]] == ["speechify"]


@respx.mock
def test_every_candidate_carries_its_evidence_url_for_review(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """`boards.greenhouse.io/embed/job_app?token=<n>` parses to the board `embed`.

    That is a real greenhouse URL form and it is NOT filtered, for the reason
    `lanes/github_lists.py` gives: a suppression list is a guess about which slugs are chrome. The
    evidence URL beside the slug is what makes it refusable at a glance, so its ABSENCE is the
    defect this pins -- the row would otherwise read as an ordinary employer board.
    """
    embed = "https://boards.greenhouse.io/embed/job_app?token=6099883"
    _redirect(respx_mock, "chrome", embed)

    result = resolve((_seed("chrome"),), _fetcher(tmp_path))
    document = candidate_document(result, generated_on=date(2026, 9, 2))

    assert ("greenhouse", "embed") == (result.boards[0].provider, result.boards[0].slug)
    assert f"greenhouse:embed | {embed}" in document
    # and the slug still reaches the importable half, so a reviewer deletes it rather than
    # discovering the emitter silently decided for them
    assert yaml.safe_load(document)["companies"][0]["slug"] == "embed"


@pytest.mark.parametrize("value", ["speechify\nrogue: yes", "speechify\r\ninjected: 1"])
def test_a_newline_in_a_resolved_value_cannot_break_out_of_the_header_comment(
    value: str, tmp_path: Path
) -> None:
    """The slug and URL come from a REDIRECT TARGET, so they are remote input.

    A newline inside one would end the `#` comment and let the remainder parse as YAML.
    """
    from boardwatch.lanes.grnh_seeds import GrnhCensus, GrnhResolution, ResolvedBoard

    resolution = GrnhResolution(
        boards=(ResolvedBoard("greenhouse", value, "https://grnh.se/x", "https://x/"),),
        census=GrnhCensus(seeds_read=1, resolved=1, duplicate=0, off_board=0, failed=0),
        errors=(),
    )
    document = candidate_document(resolution, generated_on=date(2026, 9, 2))

    # Asserted by PARSING rather than by splitting on a marker: a split on "companies:" is itself
    # defeated by a value containing that string, which is the very injection being tested.
    parsed = yaml.safe_load(document)
    assert list(parsed) == ["companies"]
    assert len(parsed["companies"]) == 1


# ------------------------------------------------------------------------------------------
# Findings from the 2026-09-02 review: each of these fails against the version reviewed.
# ------------------------------------------------------------------------------------------


@respx.mock
def test_two_different_boards_both_survive_the_dedupe(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """The NEGATIVE CONTROL the dedupe test needs, and did not have.

    Every other test resolves at most one board, so an over-broad key -- `provider` alone, say --
    collapses distinct employers into one row and the whole suite still passes. This is the only
    test that can see that, and it is the failure mode that silently loses boards.
    """
    _redirect(respx_mock, "one", BOARD)
    _redirect(respx_mock, "two", "https://job-boards.greenhouse.io/rackner/jobs/1")

    result = resolve((_seed("one", 1), _seed("two", 2)), _fetcher(tmp_path))

    assert sorted(b.slug for b in result.boards) == ["rackner", "speechify"]
    assert result.census.resolved == 2
    assert result.census.duplicate == 0


@respx.mock
def test_a_board_named_by_an_expired_posting_is_kept_not_discarded(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """An aged seed backlog is mostly DEAD REQUISITIONS on LIVE boards.

    The Indeed lane discovers a posting, the employer closes it, the seed is followed weeks
    later. The redirect still named the board, so discarding the 404 throws away exactly what
    this command exists to find and files it under "dead short link".
    """
    respx_mock.get("https://grnh.se/expired").mock(
        return_value=httpx.Response(302, headers={"Location": BOARD})
    )
    respx_mock.get(BOARD).mock(return_value=httpx.Response(404))

    result = resolve((_seed("expired"),), _fetcher(tmp_path))

    assert [(b.provider, b.slug) for b in result.boards] == [("greenhouse", "speechify")]
    assert result.census.from_expired_posting == 1
    assert result.census.failed == 0


@respx.mock
def test_a_short_link_that_dies_before_naming_a_board_is_still_a_failure(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """The complement of the test above: without it, `failed` could be dead code."""
    respx_mock.get("https://grnh.se/gone").mock(return_value=httpx.Response(404))

    result = resolve((_seed("gone"),), _fetcher(tmp_path))

    assert result.boards == ()
    assert result.census.failed == 1
    assert result.census.from_expired_posting == 0


@respx.mock
def test_the_census_accounts_for_every_seed_it_read(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """A seed in none of the buckets is a silent loss, and dedupe was exactly that.

    Four seeds, one per outcome, asserted as a REconciliation rather than four separate counts:
    the sum is the property, and pinning the parts individually is what let a fifth outcome go
    uncounted in the first place.
    """
    _redirect(respx_mock, "a", BOARD)
    _redirect(respx_mock, "b", "https://job-boards.greenhouse.io/speechify/jobs/2")  # duplicate
    _redirect(respx_mock, "c", "https://careers.example.com/jobs/1")  # off-board
    respx_mock.get("https://grnh.se/d").mock(return_value=httpx.Response(404))  # failed

    result = resolve(
        tuple(_seed(t, i) for i, t in enumerate("abcd", start=1)), _fetcher(tmp_path)
    )

    c = result.census
    assert (c.seeds_read, c.resolved, c.duplicate, c.off_board, c.failed) == (4, 1, 1, 1, 1)
    assert c.reconciles()


def test_boards_already_stored_are_dropped_but_still_counted(tmp_path: Path) -> None:
    """Without this the reviewer re-triages the same list, including rows they just deleted.

    The command charges no attempt and never sets `resolved_at`, so the seed set is identical on
    every invocation -- the only thing that can shrink the file is the store.
    """
    from boardwatch.lanes.grnh_seeds import GrnhCensus, GrnhResolution, ResolvedBoard

    resolution = GrnhResolution(
        boards=(
            ResolvedBoard("greenhouse", "speechify", "https://grnh.se/a", "https://x/"),
            ResolvedBoard("greenhouse", "rackner", "https://grnh.se/b", "https://y/"),
        ),
        census=GrnhCensus(seeds_read=2, resolved=2, duplicate=0, off_board=0, failed=0),
        errors=(),
    )

    trimmed = without_known(
        resolution, is_known=lambda provider, slug: slug == "speechify"
    )

    assert [b.slug for b in trimmed.boards] == ["rackner"]
    assert trimmed.census.already_stored == 1
    # `resolved` still reports what was RESOLVED: the seed went somewhere, it just buys nothing.
    assert trimmed.census.resolved == 2


def test_an_exception_repr_cannot_break_out_of_the_header_comment() -> None:
    """The errors block was the one header path `_one_line` was not applied to."""
    from boardwatch.lanes.grnh_seeds import GrnhCensus, GrnhResolution

    resolution = GrnhResolution(
        boards=(),
        census=GrnhCensus(seeds_read=1, resolved=0, duplicate=0, off_board=0, failed=1),
        errors=("https://grnh.se/x: Boom(\ncompanies: [{name: evil}]\n)",),
    )

    document = candidate_document(resolution, generated_on=date(2026, 9, 2))

    assert yaml.safe_load(document) == {"companies": []}


@respx.mock
def test_the_default_stdout_path_emits_a_document_that_still_parses(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """`console.print` WORD-WRAPS, which breaks header comments onto un-`#`-prefixed lines.

    Asserted through the real CLI at an 80-column stdout, because the defect lives in the
    command's choice of writer and is invisible to any test that calls `candidate_document`
    directly. Against `console.print` the header wraps and `safe_load` raises.
    """
    from typer.testing import CliRunner

    from boardwatch.cli.app import app

    _redirect(respx_mock, "abc123", BOARD)
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    engine = get_engine(data)
    ensure_schema(engine)  # `init` PROMPTS; this is what it calls underneath
    run = insert_run(engine)
    with engine.begin() as conn:
        # The sanctioned single write point, not a raw insert: it is what applies
        # `is_seedable_url`, so the row under test is one production could actually hold.
        record_seeds(
            conn, ("https://grnh.se/abc123",), discovered_by="indeed", run_id=run, now=utcnow()
        )

    invoked = CliRunner().invoke(
        app, ["--data-dir", str(data), "companies", "discover-grnh", "--limit", "5"]
    )

    assert invoked.exit_code == 0, invoked.output
    assert yaml.safe_load(invoked.stdout)["companies"][0]["slug"] == "speechify"


@respx.mock
def test_two_expired_postings_on_one_board_are_deduped_and_counted(
    respx_mock: respx.Router, tmp_path: Path
) -> None:
    """The 404 path has its OWN dedupe, and a mutation campaign found it uncounted.

    Both branches append a board, so both must charge the `duplicate` bucket -- otherwise a
    backlog of expired postings on one board reconciles to fewer seeds than it read, and the
    header's whole purpose is to make that visible. Removing the increment on THIS path passed
    the entire suite before this test existed.
    """
    for token in ("x", "y"):
        respx_mock.get(f"https://grnh.se/{token}").mock(
            return_value=httpx.Response(302, headers={"Location": BOARD})
        )
    respx_mock.get(BOARD).mock(return_value=httpx.Response(410))

    result = resolve((_seed("x", 1), _seed("y", 2)), _fetcher(tmp_path))

    c = result.census
    assert [b.slug for b in result.boards] == ["speechify"]
    assert (c.seeds_read, c.resolved, c.duplicate, c.failed) == (2, 1, 1, 0)
    assert c.reconciles()
    assert c.from_expired_posting == 1
