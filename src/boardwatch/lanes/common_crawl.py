"""Board discovery from the Common Crawl URL index, probed against the real provider.

THIS IS NOT A `Lane` and it writes NOTHING to the store, for the reasons `github_lists` gives: the
deliverable is `(provider, slug)` boards for a human to read, and `companies import` stays the only
watched-write.

ENUMERATION USES THE STATIC INDEX FILES, NOT THE CDX SERVER, which answers 504 under load. The
collection's `cluster.idx` (~900k lines, 150 MB+) holds one line per index block, tab-separated:
`<surtkey> <timestamp>`, `<cdx file>`, `<offset>`, `<length>`, `<cluster>`. Streaming it and
range-GETting the blocks whose keys start with a provider's SURT prefix yields every captured URL
on that host.

`HttpCrawlSource` owns its own httpx client instead of `Fetcher`, for two reasons read off
`core/politeness.py`. `Fetcher._read_body` joins the whole body in memory, which a 150 MB stream
must never be, and `_classify` treats 206 as a failure, which is the only success a Range request
has. data.commoncrawl.org is the one host it reaches, at no more than one request a second.

A CRAWL SLUG IS A CLAIM, NOT A BOARD: it is any first path segment that ever appeared under the
host, so it is probed through the provider, and a board is proposed only when it answers with a
posting the ranker's own role gate calls in-field (and, under `us_only`, a US location).

DRAIN. A board dropped here for having no qualifying posting today is persisted nowhere. Re-running
re-probes it, and that is its re-entry path: no table, no state file.
"""

from __future__ import annotations

import gzip
import re
import threading
import time
import zlib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from typing import Literal, NamedTuple, Protocol
from urllib.parse import unquote

import httpx

from boardwatch.core.models import BoardRequest, RawPosting
from boardwatch.core.politeness import Fetcher, identifying_user_agent
from boardwatch.lanes.github_lists import Selection, one_line
from boardwatch.providers.base import Provider
from boardwatch.rank.location_gate import classify_location
from boardwatch.rank.role_gate import taxonomy_role_verdict
from boardwatch.rank.role_taxonomy import RoleTaxonomy

CC_DATA = "https://data.commoncrawl.org/"
COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
MIN_REQUEST_INTERVAL = 1.0

# SURT prefix -> provider. A SURT key reverses the host and ends it with `)`; the path follows.
SURT_PROVIDERS: dict[str, str] = {
    "io,greenhouse,boards)/": "greenhouse",
    "io,greenhouse,job-boards)/": "greenhouse",
    "com,ashbyhq,jobs)/": "ashby",
    "com,workable,apply)/": "workable",
    "com,smartrecruiters,jobs)/": "smartrecruiters",
}
DEFAULT_PROVIDERS: tuple[str, ...] = ("greenhouse", "ashby")

# Path segments that are the ATS's own furniture, not an employer.
ATS_CHROME = frozenset({
    "embed", "api", "assets", "static", "_next", "j", "jobs", "oneclick", "oneclick-ui",
    "sitemap", "sitemap.xml", "robots.txt", "favicon.ico",
})
_SLUG_SHAPE = re.compile(r"[a-z0-9._-]{2,80}")

# A probe needs a sample, not the whole board: SmartRecruiters spends one GET per posting for its
# location, and 50 of them at one a second would be the whole cost of a probe.
PROBE_DETAIL_BUDGET = 10
_ATTEMPTS = 3


class Block(NamedTuple):
    cdx_file: str
    offset: int
    length: int


class CrawlSource(Protocol):
    """The three reads enumeration makes; a test injects bytes through it."""

    def newest_collection(self) -> str: ...

    def cluster_lines(self, collection: str) -> Iterator[str]: ...

    def block(self, collection: str, block: Block) -> bytes: ...


class BlockUnavailable(Exception):
    """A block that could not be fetched after its retries. `enumerate_slugs` counts it: one bad
    block must not discard the others."""


class HttpCrawlSource:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": identifying_user_agent()}, timeout=120.0, follow_redirects=True
        )
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None

    def _pace(self) -> None:
        if self._last is not None:
            wait = self._last + MIN_REQUEST_INTERVAL - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def newest_collection(self) -> str:
        self._pace()
        response = self._client.get(COLLINFO_URL)
        response.raise_for_status()
        return str(response.json()[0]["id"])

    def cluster_lines(self, collection: str) -> Iterator[str]:
        self._pace()
        url = f"{CC_DATA}cc-index/collections/{collection}/indexes/cluster.idx"
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            yield from response.iter_lines()

    def block(self, collection: str, block: Block) -> bytes:
        url = f"{CC_DATA}cc-index/collections/{collection}/indexes/{block.cdx_file}"
        span = f"bytes={block.offset}-{block.offset + block.length - 1}"
        failure = "no attempt"
        for attempt in range(_ATTEMPTS):
            if attempt:
                self._sleep(8.0 * attempt)
            self._pace()
            try:
                with self._client.stream("GET", url, headers={"Range": span}) as response:
                    # Only 206 is a range answer. A 200 is the whole multi-GB file, refused unread.
                    if response.status_code == 206:
                        return response.read()
                    failure = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                failure = str(exc)
        raise BlockUnavailable(f"{block.cdx_file} {span}: {failure}")


def _parse_cluster_line(line: str) -> tuple[str, Block] | None:
    fields = line.rstrip("\n").split("\t")
    if len(fields) < 4:
        return None
    try:
        return fields[0].split(" ")[0], Block(fields[1], int(fields[2]), int(fields[3]))
    except ValueError:
        return None


def select_blocks(lines: Iterable[str], prefixes: Sequence[str]) -> dict[str, list[Block]]:
    """Per prefix, the index blocks that can hold it, in file order, streaming `lines` once.

    A block is named by its FIRST key, so records for a prefix begin in the block BEFORE the first
    block whose key is at or past the prefix. That block is included whether or not the next key
    matches, which is also what catches a prefix that sits wholly inside one block.
    """
    blocks: dict[str, list[Block]] = {prefix: [] for prefix in prefixes}
    entered: set[str] = set()
    previous: Block | None = None
    for line in lines:
        parsed = _parse_cluster_line(line)
        if parsed is None:
            continue
        key, block = parsed
        for prefix in prefixes:
            if key.startswith(prefix):
                if prefix not in entered and previous is not None:
                    blocks[prefix].append(previous)
                entered.add(prefix)
                blocks[prefix].append(block)
            elif key > prefix and prefix not in entered:
                entered.add(prefix)
                if previous is not None:
                    blocks[prefix].append(previous)
        previous = block
    return blocks


def slug_from_key(key: str, prefix: str) -> str | None:
    """The board slug in a SURT key under `prefix`, or None when the segment is not one."""
    segment = unquote(key[len(prefix):].split("/")[0].split("?")[0]).lower()
    if segment in ATS_CHROME or _SLUG_SHAPE.fullmatch(segment) is None:
        return None
    return segment


@dataclass(frozen=True)
class Enumeration:
    slugs: dict[str, tuple[str, ...]]  # provider -> sorted distinct slugs
    blocks_read: int
    blocks_failed: int
    blocks_omitted: int  # past `max_blocks`, so their slugs were never enumerated


def enumerate_slugs(
    source: CrawlSource,
    collection: str,
    providers: Sequence[str],
    *,
    max_blocks: int | None = None,
) -> Enumeration:
    prefixes = [p for p, name in SURT_PROVIDERS.items() if name in providers]
    chosen = select_blocks(source.cluster_lines(collection), prefixes)
    wanted: dict[Block, list[str]] = {}
    omitted = 0
    for prefix, blocks in chosen.items():
        kept = blocks if max_blocks is None else blocks[:max_blocks]
        omitted += len(blocks) - len(kept)
        for block in kept:
            wanted.setdefault(block, []).append(prefix)
    found: dict[str, set[str]] = {name: set() for name in providers}
    read = failed = 0
    for block, block_prefixes in wanted.items():
        try:
            text = gzip.decompress(source.block(collection, block)).decode("utf-8", "replace")
        except (BlockUnavailable, OSError, EOFError, zlib.error):
            failed += 1
            continue
        read += 1
        for line in text.splitlines():
            for prefix in block_prefixes:
                if line.startswith(prefix):
                    slug = slug_from_key(line.split(" ", 1)[0], prefix)
                    if slug is not None:
                        found[SURT_PROVIDERS[prefix]].add(slug)
    return Enumeration(
        slugs={name: tuple(sorted(slugs)) for name, slugs in found.items()},
        blocks_read=read, blocks_failed=failed, blocks_omitted=omitted,
    )


Outcome = Literal["admitted", "dead", "failed", "empty", "no_qualifying"]


@dataclass(frozen=True)
class ProbeResult:
    provider: str
    slug: str
    outcome: Outcome
    board_url: str = ""
    open_postings: int = 0
    qualifying: int = 0
    samples: tuple[str, ...] = ()


def _qualifies(posting: RawPosting, taxonomy: RoleTaxonomy, us_only: bool) -> bool:
    # `in_field` only: `uncertain` passes the ranker, but a board is being PROPOSED on this
    # evidence, and a title the gate cannot read is not evidence of the field.
    if taxonomy_role_verdict(posting.title, taxonomy)[0] != "in_field":
        return False
    # `us` only, so `unknown` (a bare "Remote") does not count: classify_location fails open,
    # which is right for keeping a posting and wrong for vouching for a board.
    return not us_only or classify_location(posting.locations) == "us"


def probe_board(
    provider: Provider, fetcher: Fetcher, slug: str, *, taxonomy: RoleTaxonomy, us_only: bool
) -> ProbeResult:
    """One board through the real provider. A failure is a counted outcome, never an exception:
    a crawl slug is third-party input and one bad board must not end a long probe."""
    url = provider.board_url(slug)
    request = BoardRequest(
        provider=provider.name, slug=slug, url=url, detail_budget=PROBE_DETAIL_BUDGET
    )
    try:
        snapshot = provider.fetch_board(fetcher, request)
    except Exception:
        return ProbeResult(provider.name, slug, "failed", url)
    if snapshot.status == "failed":
        return ProbeResult(provider.name, slug, "dead" if snapshot.dead else "failed", url)
    postings = snapshot.postings
    if not postings:
        return ProbeResult(provider.name, slug, "empty", url)
    open_count = (
        snapshot.board_reported_total
        if snapshot.board_reported_total is not None
        else max(len(postings), len(snapshot.listed_ids))
    )
    hits = [p.title for p in postings if _qualifies(p, taxonomy, us_only)]
    return ProbeResult(
        provider.name, slug, "admitted" if hits else "no_qualifying", url,
        open_postings=open_count, qualifying=len(hits), samples=tuple(hits[:2]),
    )


def probe_candidates(
    queues: Mapping[str, Sequence[str]],
    providers: Mapping[str, Provider],
    fetcher: Fetcher,
    *,
    taxonomy: RoleTaxonomy,
    us_only: bool,
    cap: int,
    on_result: Callable[[ProbeResult], None] | None = None,
) -> list[ProbeResult]:
    """Probe every provider's queue, one worker per provider, until `cap` boards are admitted.

    One worker each because `Fetcher` serializes a host behind one lock: more threads per provider
    would only queue. The workers stop between probes once the cap is met, so an in-flight probe
    can finish past it and `select` refuses the overshoot. A Ctrl-C sets the same stop flag and
    waits for at most one in-flight probe per worker. Nothing is written until the caller does.
    """
    stop = threading.Event()
    lock = threading.Lock()
    admitted = 0

    def work(name: str) -> list[ProbeResult]:
        nonlocal admitted
        done: list[ProbeResult] = []
        for slug in queues[name]:
            if stop.is_set():
                break
            result = probe_board(providers[name], fetcher, slug, taxonomy=taxonomy, us_only=us_only)
            done.append(result)
            with lock:
                if result.outcome == "admitted":
                    admitted += 1
                    if admitted >= cap:
                        stop.set()
                if on_result is not None:
                    on_result(result)
        return done

    with ThreadPoolExecutor(max_workers=max(len(queues), 1)) as pool:
        futures = [pool.submit(work, name) for name in queues]
        try:
            return [result for future in futures for result in future.result()]
        except BaseException:
            stop.set()
            raise


@dataclass(frozen=True)
class CrawlCensus:
    enumerated: int
    already_known: int
    probed: int
    dead: int
    failed: int
    empty: int
    no_qualifying: int
    admitted: int
    refused: int

    @property
    def not_probed(self) -> int:
        return self.enumerated - self.already_known - self.probed


def crawl_header(
    selection: Selection,
    census: CrawlCensus,
    results: Mapping[tuple[str, str], ProbeResult],
    *,
    collection: str,
    providers: Sequence[str],
    us_only: bool,
    generated_on: date,
    enumeration: Enumeration,
) -> str:
    """Comment header: the census, then one checkable evidence line per candidate."""
    lines = [
        "# boardwatch companies discover-crawl - candidate boards from the Common Crawl index, "
        "for review before import",
        "#",
        f"# generated {generated_on.isoformat()} from {collection} | providers "
        f"{', '.join(providers)} | us-only {'yes' if us_only else 'no'}",
        f"# index blocks read {enumeration.blocks_read} | failed {enumeration.blocks_failed} "
        f"| omitted by --max-blocks {enumeration.blocks_omitted}",
        f"# enumerated {census.enumerated} | already stored {census.already_known} "
        f"| probed {census.probed} | dead {census.dead} | failed {census.failed} "
        f"| empty {census.empty} | no qualifying posting {census.no_qualifying} "
        f"| admitted {census.admitted} | held back by the cap {census.refused} "
        f"| not probed {census.not_probed}",
        "#",
    ]
    if selection.admitted:
        lines.append("# Check each board URL names a real employer:")
        for c in selection.admitted:
            r = results[(c.provider, c.slug)]
            samples = "; ".join(one_line(t) for t in r.samples)
            lines.append(
                f"#   {c.provider}:{one_line(c.slug)} | {one_line(r.board_url)} "
                f"| {r.open_postings} open | {r.qualifying} qualifying | e.g. {samples}"
            )
    else:
        lines.append("# No new boards. Nothing to import.")
    return "\n".join(lines) + "\n\n"
