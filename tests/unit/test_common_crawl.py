"""Common Crawl board discovery: block selection, slug extraction, the probe and the cap.

No network anywhere. Enumeration runs on injected bytes through the `CrawlSource` seam, the probe
runs on fake providers that return snapshots, and `HttpCrawlSource` runs on an `httpx.MockTransport`.
Every expected value is written out by hand from the fixture lines below, never recomputed.
"""

from __future__ import annotations

import gzip

import httpx
import pytest

from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.lanes.common_crawl import (
    Block,
    BlockUnavailable,
    HttpCrawlSource,
    enumerate_slugs,
    probe_board,
    probe_candidates,
    select_blocks,
    slug_from_key,
)
from boardwatch.rank.role_taxonomy import RoleTaxonomy, parse_role_taxonomy

ASHBY = "com,ashbyhq,jobs)/"
TAXONOMY: RoleTaxonomy = parse_role_taxonomy({"version": 1, "field": "software", "bundled": True})


def _idx(key: str, cdx: str, offset: int, length: int) -> str:
    return f"{key} 20261001000000\t{cdx}\t{offset}\t{length}\t1\n"


A = Block("cdx-00000.gz", 0, 10)
B = Block("cdx-00000.gz", 10, 20)
C = Block("cdx-00001.gz", 0, 30)
D = Block("cdx-00001.gz", 30, 40)

CLUSTER = [
    _idx("com,aardvark)/", *A),
    _idx("com,ashbyhq,jobs)/alpha/1", *B),
    _idx("com,ashbyhq,jobs)/mmm/2", *C),
    _idx("com,ashbyhq,jobs)/zzz/3", *D),
    _idx("com,zeta)/", "cdx-00002.gz", 0, 50),
]


def test_the_block_before_the_first_match_is_selected() -> None:
    """A block is named by its first key, so ashby's earliest records sit in block A."""
    assert select_blocks(CLUSTER, [ASHBY]) == {ASHBY: [A, B, C, D]}


def test_a_prefix_wholly_inside_one_block_selects_that_block() -> None:
    lines = [_idx("com,a)/", *A), _idx("com,zzz)/", *B)]

    assert select_blocks(lines, ["com,mmm)/"]) == {"com,mmm)/": [A]}


def test_malformed_cluster_lines_are_skipped() -> None:
    lines = ["garbage\n", _idx("com,ashbyhq,jobs)/q/1", "cdx-9.gz", "x", 1)]

    assert select_blocks(lines, [ASHBY]) == {ASHBY: []}


@pytest.mark.parametrize(
    "key, expected",
    [
        ("com,ashbyhq,jobs)/Acme/1", "acme"),
        ("com,ashbyhq,jobs)/%41cme-co/1", "acme-co"),
        ("com,ashbyhq,jobs)/acme?x=1", "acme"),
        ("com,ashbyhq,jobs)/a.b_c-1/2", "a.b_c-1"),
        ("com,ashbyhq,jobs)/embed/job_app", None),
        ("com,ashbyhq,jobs)/_next/static", None),
        ("com,ashbyhq,jobs)/sitemap.xml", None),
        ("com,ashbyhq,jobs)/j/123", None),
        ("com,ashbyhq,jobs)/a/1", None),
        ("com,ashbyhq,jobs)/has%20space/1", None),
        ("com,ashbyhq,jobs)/x" + "y" * 80, None),
        ("com,ashbyhq,jobs)/?for=acme", None),
        ("com,ashbyhq,jobs)/", None),
    ],
)
def test_slug_extraction(key: str, expected: str | None) -> None:
    assert slug_from_key(key, ASHBY) == expected


class FakeSource:
    def __init__(self, cluster: list[str], blocks: dict[Block, bytes | Exception]) -> None:
        self.cluster = cluster
        self.blocks = blocks
        self.requested: list[Block] = []

    def newest_collection(self) -> str:
        return "CC-TEST"

    def cluster_lines(self, collection: str):  # type: ignore[no-untyped-def]
        yield from self.cluster

    def block(self, collection: str, block: Block) -> bytes:
        self.requested.append(block)
        found = self.blocks[block]
        if isinstance(found, Exception):
            raise found
        return found


def _gz(*keys: str) -> bytes:
    return gzip.compress("".join(f"{k} 20261001000000 {{}}\n" for k in keys).encode())


def test_enumeration_returns_distinct_clean_slugs_per_provider() -> None:
    source = FakeSource(
        CLUSTER,
        {
            A: _gz("com,aardvark)/x", "com,ashbyhq,jobs)/Acme/9"),
            B: _gz("com,ashbyhq,jobs)/acme/1", "com,ashbyhq,jobs)/embed/job_app?for=evil"),
            C: _gz("com,ashbyhq,jobs)/mmm/2", "com,ashbyhq,jobs)/Bad%20Slug/1"),
            D: _gz("com,ashbyhq,jobs)/zzz/3", "com,ashbyhq,jobs)/api/x", "com,zeta)/acme"),
        },
    )

    found = enumerate_slugs(source, "CC-TEST", ["ashby"])

    # `acme` appears twice (two cases) and `aardvark`/`zeta` belong to other hosts.
    assert found.slugs == {"ashby": ("acme", "mmm", "zzz")}
    assert (found.blocks_read, found.blocks_failed, found.blocks_omitted) == (4, 0, 0)
    assert source.requested == [A, B, C, D]


def test_a_failed_or_corrupt_block_is_counted_and_the_rest_still_read() -> None:
    source = FakeSource(
        CLUSTER,
        {
            A: BlockUnavailable("503"),
            B: b"not gzip at all",
            C: _gz("com,ashbyhq,jobs)/mmm/2"),
            D: _gz("com,ashbyhq,jobs)/zzz/3"),
        },
    )

    found = enumerate_slugs(source, "CC-TEST", ["ashby"])

    assert found.slugs == {"ashby": ("mmm", "zzz")}
    assert (found.blocks_read, found.blocks_failed) == (2, 2)


def test_max_blocks_omits_the_tail_and_says_so() -> None:
    source = FakeSource(CLUSTER, {A: _gz(), B: _gz("com,ashbyhq,jobs)/alpha/1")})

    found = enumerate_slugs(source, "CC-TEST", ["ashby"], max_blocks=2)

    assert found.slugs == {"ashby": ("alpha",)}
    assert (found.blocks_read, found.blocks_omitted) == (2, 2)
    assert source.requested == [A, B]


# ---- the probe ----------------------------------------------------------------------------


def _posting(title: str, *locations: str) -> RawPosting:
    return RawPosting(
        provider_posting_id=title, title=title, url="https://x.test/1", locations=list(locations),
        body_text="", raw_json={},
    )


class FakeProvider:
    name = "ashby"
    board_hosts: tuple[str, ...] = ()

    def __init__(self, boards: dict[str, BoardSnapshot | Exception]) -> None:
        self.boards = boards
        self.probed: list[str] = []

    def board_url(self, slug: str) -> str:
        return f"https://api.test/{slug}"

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot:
        self.probed.append(request.slug)
        found = self.boards[request.slug]
        if isinstance(found, Exception):
            raise found
        return found

    def healthcheck(self, fetcher: Fetcher, slug: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError


def _snap(*postings: RawPosting, status: str = "complete", dead: bool = False) -> BoardSnapshot:
    return BoardSnapshot(
        status=status, postings=list(postings), url="https://api.test/x", dead=dead  # type: ignore[arg-type]
    )


def _fetcher(tmp_path) -> Fetcher:  # type: ignore[no-untyped-def]
    return Fetcher(
        Settings(data_dir=tmp_path, config_dir=tmp_path), client=httpx.Client()
    )


def _probe(tmp_path, boards, slug, *, us_only=False):  # type: ignore[no-untyped-def]
    return probe_board(
        FakeProvider(boards), _fetcher(tmp_path), slug, taxonomy=TAXONOMY, us_only=us_only
    )


def test_a_dead_board_is_counted_and_a_raising_provider_is_not_propagated(tmp_path) -> None:  # type: ignore[no-untyped-def]
    boards: dict[str, BoardSnapshot | Exception] = {
        "gone": _snap(status="failed", dead=True),
        "flaky": _snap(status="failed"),
        "boom": RuntimeError("provider bug"),
    }

    assert _probe(tmp_path, boards, "gone").outcome == "dead"
    assert _probe(tmp_path, boards, "flaky").outcome == "failed"
    assert _probe(tmp_path, boards, "boom").outcome == "failed"


def test_an_empty_board_is_not_admitted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert _probe(tmp_path, {"e": _snap()}, "e").outcome == "empty"


def test_a_board_of_only_out_of_field_titles_is_not_admitted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    boards = {"sales": _snap(_posting("Account Executive", "Austin, TX"))}

    result = _probe(tmp_path, boards, "sales")

    assert (result.outcome, result.qualifying, result.open_postings) == ("no_qualifying", 0, 1)


def test_a_title_the_gate_cannot_read_is_not_evidence_of_the_field(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`uncertain` passes the ranker, but a board is proposed on `in_field` evidence only."""
    boards = {"vague": _snap(_posting("Founding Generalist", "Austin, TX"))}

    assert _probe(tmp_path, boards, "vague").outcome == "no_qualifying"


def test_an_admitted_board_carries_its_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    boards = {
        "acme": _snap(
            _posting("Software Engineer", "Austin, TX"),
            _posting("Backend Engineer", "Austin, TX"),
            _posting("Platform Software Engineer", "Austin, TX"),
            _posting("Account Executive", "Austin, TX"),
        )
    }

    result = _probe(tmp_path, boards, "acme")

    assert result.outcome == "admitted"
    assert (result.open_postings, result.qualifying) == (4, 3)
    assert result.samples == ("Software Engineer", "Backend Engineer")
    assert result.board_url == "https://api.test/acme"


def test_us_only_rejects_foreign_and_unknown_locations(tmp_path) -> None:  # type: ignore[no-untyped-def]
    boards = {
        "abroad": _snap(_posting("Software Engineer", "London, United Kingdom")),
        "vague": _snap(_posting("Software Engineer", "Remote")),
        "home": _snap(_posting("Software Engineer", "Remote", "Austin, TX")),
    }

    # Control: without --us-only the same foreign and vague boards qualify, so the gate below is
    # what rejected them and not the title.
    assert _probe(tmp_path, boards, "abroad").outcome == "admitted"
    assert _probe(tmp_path, boards, "vague").outcome == "admitted"
    assert _probe(tmp_path, boards, "abroad", us_only=True).outcome == "no_qualifying"
    assert _probe(tmp_path, boards, "vague", us_only=True).outcome == "no_qualifying"
    assert _probe(tmp_path, boards, "home", us_only=True).outcome == "admitted"


def test_us_only_needs_the_title_and_the_location_on_the_same_posting(tmp_path) -> None:  # type: ignore[no-untyped-def]
    boards = {
        "split": _snap(
            _posting("Software Engineer", "London, United Kingdom"),
            _posting("Account Executive", "Austin, TX"),
        )
    }

    assert _probe(tmp_path, boards, "split", us_only=True).outcome == "no_qualifying"


def test_probing_stops_at_the_cap_and_runs_one_worker_per_provider(tmp_path) -> None:  # type: ignore[no-untyped-def]
    good = _snap(_posting("Software Engineer", "Austin, TX"))
    provider = FakeProvider({"a": good, "b": good, "c": good, "d": good})

    results = probe_candidates(
        {"ashby": ["a", "b", "c", "d"]}, {"ashby": provider}, _fetcher(tmp_path),
        taxonomy=TAXONOMY, us_only=False, cap=2,
    )

    assert [r.slug for r in results] == ["a", "b"]
    assert provider.probed == ["a", "b"]


# ---- the HTTP source ----------------------------------------------------------------------


def test_http_source_sends_a_range_requires_206_and_paces_to_one_a_second() -> None:
    seen: list[httpx.Request] = []
    now = [100.0]
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("cdx-00000.gz"):
            return httpx.Response(206, content=b"bytes")
        return httpx.Response(200, content=b"whole file")

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    source = HttpCrawlSource(
        httpx.Client(transport=httpx.MockTransport(handler)), sleep=sleep, clock=lambda: now[0]
    )

    assert source.block("CC-X", Block("cdx-00000.gz", 5, 10)) == b"bytes"
    assert seen[0].headers["Range"] == "bytes=5-14"
    assert seen[0].url.host == "data.commoncrawl.org"
    # The clock did not move between requests, so the second one waited the full second.
    assert source.block("CC-X", Block("cdx-00000.gz", 5, 10)) == b"bytes"
    assert slept == [1.0]
    with pytest.raises(BlockUnavailable, match="HTTP 200"):
        source.block("CC-X", Block("cdx-00001.gz", 0, 10))
