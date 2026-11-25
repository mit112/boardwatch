"""T352: an Oracle HCM board past the result window is listed as its two posting-date children.

`_Site` is a fake list endpoint in the shape the live service was measured to have: newest first,
`TotalJobsCount` only at offset 0, an empty page past the window, and `selectedPostingDatesFacet`
30 and 31 partitioning the board (ejwl, jpmc and eigx, 2026-11-24). The window is 4 rows and a
page 2, so the fixture stays small enough to read.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import insert, select

from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers import oraclehcm
from boardwatch.providers.oraclehcm import OracleHCMProvider
from boardwatch.rank.heuristic import ProfileView
from boardwatch.rank.listing_gate import build_listing_gate
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run

pytestmark = pytest.mark.usefixtures("no_real_sleep")

HOST = "acme.fa.us2.oraclecloud.com"
SLUG = f"{HOST}/CX_1"
LIST_PREFIX = f"https://{HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?"
WINDOW, PAGE = 4, 2
provider = OracleHCMProvider()


@pytest.fixture(autouse=True)
def _small_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oraclehcm, "_RESULT_WINDOW", WINDOW)
    monkeypatch.setattr(oraclehcm, "_PAGE_LIMIT", PAGE)
    monkeypatch.setattr(oraclehcm, "_SPLIT_MAX_PAGES", 2 * (WINDOW // PAGE + 1) + 1)


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


@dataclass
class _Site:
    """`recent` and `older` are the ids under and over 30 days, each newest first."""

    recent: list[str]
    older: list[str]
    fail: frozenset[str] = frozenset()  # facet values answering 500
    root_bias: int = 0  # the root's own TotalJobsCount drifted by this much
    child_bias: dict[str, int] = field(default_factory=dict)  # a child's stated total, drifted
    repeat_from: int | None = None  # from this offset on, serve the first page again
    root_ids: list[str] | None = None  # the root's own ids, when they are not recent + older
    inserted: dict[str, str] = field(default_factory=dict)  # a child gains this newest id after page 0
    calls: list[tuple[str | None, int]] = field(default_factory=list)

    def ids(self) -> frozenset[str]:
        return frozenset(self.recent + self.older)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        finder = request.url.params["finder"]
        offset = int(re.search(r"offset=(\d+)", finder).group(1))  # type: ignore[union-attr]
        facet = re.search(r"selectedPostingDatesFacet=(\d+)", finder)
        part = facet.group(1) if facet else None
        assert re.search(rf"limit={PAGE},", finder)
        self.calls.append((part, offset))
        if part in self.fail:
            return httpx.Response(500)
        root = self.recent + self.older if self.root_ids is None else self.root_ids
        ids = {None: root, "30": self.recent, "31": self.older}[part]
        if part in self.inserted and offset > 0:
            ids = [self.inserted[part], *ids]  # posted while the child was being read
        start = 0 if self.repeat_from is not None and offset >= self.repeat_from else offset
        served = ids[start : min(start + PAGE, WINDOW)] if start < WINDOW else []
        total = len(ids) + (self.root_bias if part is None else self.child_bias.get(part, 0))
        item: dict[str, Any] = {
            "TotalJobsCount": total if offset == 0 else 0,
            "requisitionList": [
                {"Id": pid, "Title": f"Engineer {pid}", "PrimaryLocation": "Austin, TX",
                 "PostedDate": "2026-11-01"}
                for pid in served
            ],
        }
        return httpx.Response(200, json={"items": [item]})


def _site(recent: int, older: int, **kwargs: Any) -> _Site:
    return _Site([f"N{i}" for i in range(recent)], [f"O{i}" for i in range(older)], **kwargs)


def _request(known: frozenset[str]) -> BoardRequest:
    return BoardRequest(
        provider="oraclehcm", slug=SLUG, url=provider.board_url(SLUG), known_posting_ids=known,
        detail_budget=0,
    )


def _scan(tmp_path: Path, site: _Site, known: frozenset[str] | None = None) -> BoardSnapshot:
    with respx.mock:
        respx.get(url__startswith=LIST_PREFIX).mock(side_effect=site)
        return provider.fetch_board(
            _fetcher(tmp_path), _request(site.ids() if known is None else known)
        )


# ---- exact ids, and the two shapes the ticket names --------------------------------------

def test_a_board_past_the_window_is_listed_as_its_two_posting_date_children(
    tmp_path: Path,
) -> None:
    site = _site(3, 4)
    snapshot = _scan(tmp_path, site)
    assert snapshot.status == "complete", snapshot.error
    assert snapshot.listed_ids == site.ids()
    assert site.calls == [(None, 0), ("30", 0), ("30", 2), ("31", 0), ("31", 2), ("31", 4)]
    assert snapshot.board_reported_total == 7
    assert snapshot.listing_pages == 6
    assert snapshot.head_pages is None and snapshot.head_missed is None
    assert snapshot.listing_runs is None


def test_a_child_still_past_the_window_is_partial_with_both_childrens_counts(
    tmp_path: Path,
) -> None:
    snapshot = _scan(tmp_path, _site(1, 7))
    assert snapshot.status == "partial"
    assert (
        "posting-date split does not certify: 1 under 30 days and 7 over, against the "
        "board's 8, with a window of 4"
    ) in (snapshot.error or "")
    assert snapshot.board_enumerated == 5  # all of recent, the window of older


def test_a_board_within_the_window_sends_exactly_the_blind_pagers_requests(
    tmp_path: Path,
) -> None:
    site = _site(1, 3)
    snapshot = _scan(tmp_path, site)
    assert site.calls == [(None, 0), (None, 2), (None, 4)]
    assert snapshot.status == "complete", snapshot.error
    assert snapshot.head_pages is not None


# ---- what else must be partial -------------------------------------------------------------

def test_a_full_page_that_repeats_one_already_read_stops_and_is_partial(tmp_path: Path) -> None:
    """The guard the unsplit pager always had, which no test pinned: a full page adding no new
    id stops the pager and keeps the board partial, so nothing unread is closed."""
    site = _site(1, 3, repeat_from=2)
    snapshot = _scan(tmp_path, site)
    assert site.calls == [(None, 0), (None, 2)]
    assert snapshot.status == "partial"
    assert snapshot.error == (
        "page at offset 2 added no new postings; stopping (2 collected, listing may be "
        "incomplete); incomplete listing: collected 2 of 4 postings; treating as partial so "
        "unseen postings are not closed"
    )

def test_children_whose_totals_do_not_sum_to_the_roots_are_partial(tmp_path: Path) -> None:
    """A posting closed between the root's request and the children's: every child lists its
    own total, and the two still fall one short of the board the root stated."""
    snapshot = _scan(tmp_path, _site(3, 4, root_bias=1))
    assert snapshot.status == "partial"
    assert snapshot.error == (
        "posting-date split does not certify: 3 under 30 days and 4 over, against the "
        "board's 8, with a window of 4"
    )


def test_a_child_that_lists_fewer_ids_than_its_own_total_is_partial(tmp_path: Path) -> None:
    """Within the window, and the totals sum: only the child's own count is short."""
    snapshot = _scan(tmp_path, _site(3, 2, child_bias={"31": 1}, root_bias=1))
    assert snapshot.status == "partial"
    assert "posting-date facet 31: incomplete listing: collected 2 of 3 postings" in (
        snapshot.error or ""
    )


def test_overlapping_children_whose_totals_sum_right_are_partial(tmp_path: Path) -> None:
    """Review round 1: ABC and CDEF sum to the root's 7 and each lists its own total, while G is
    in neither."""
    site = _Site(["A", "B", "C"], ["C", "D", "E", "F"], root_ids=list("ABCDEFG"))
    snapshot = _scan(tmp_path, site, frozenset("ABCDEFG"))
    assert snapshot.status == "partial"
    assert snapshot.error == "posting-date split listed 6 distinct postings of the board's 7"


def test_a_child_that_moved_while_it_was_read_is_partial(tmp_path: Path) -> None:
    """Review round 1: a newer posting arrives after the child's first page, so a row is served
    twice. Over a full window that pushes original rows past it unseen; any repeat is a no."""
    site = _site(3, 4, inserted={"30": "N9"})
    snapshot = _scan(tmp_path, site, site.ids() | {"N9"})
    assert snapshot.status == "partial"
    assert "posting-date facet 30: 1 postings served on two pages" in (snapshot.error or "")


def test_a_board_deadline_before_the_first_child_is_partial_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Fetcher, "request_fits_board_deadline", lambda self: False)
    snapshot = _scan(tmp_path, _site(3, 4))
    assert snapshot.status == "partial"
    assert "posting-date facet 30: not read, the board deadline is near" in (snapshot.error or "")


# ---- yield at equal budget -----------------------------------------------------------------

def _accepted_per_100(tmp_path: Path, site: _Site, known: frozenset[str]) -> float:
    gate = build_listing_gate(
        ProfileView(skills=frozenset(), target_titles=(), exclude_titles=(), locations=(),
                    remote_only=False, target_countries=("USA",)),
        None, "hard",
    )
    with respx.mock:
        respx.get(url__startswith=LIST_PREFIX).mock(side_effect=site)
        snapshot = provider.fetch_board(
            _fetcher(tmp_path), _request(known).model_copy(update={"listing_gate": gate})
        )
    assert snapshot.detail_deferred is not None  # budget 0: the deferral IS the accepted count
    return 100 * snapshot.detail_deferred / len(site.calls)


def test_on_the_first_split_night_the_split_accepts_more_per_100_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The store knows what the window let the blind pager reach. As in T351, the split is
    cheaper per id only on that night; on a cold store it costs a root page and a short page per
    child that the blind pager does not spend."""
    known = frozenset({"N0", "N1", "N2", "O0"})  # the first four, newest first
    split = _accepted_per_100(tmp_path, _site(3, 4), known)
    with monkeypatch.context() as patch:
        patch.setattr(oraclehcm, "_RESULT_WINDOW", 10**9)  # never splits: the blind pager
        blind = _accepted_per_100(tmp_path, _site(3, 4), known)
    assert blind == 0
    assert split > blind


# ---- the two-cycle false-closure test -------------------------------------------------------

SENTINEL = "O3"  # the oldest row: listed only in the over-30-days child


def _two_scans(tmp_path: Path, site: Callable[[], _Site]) -> tuple[tuple[str, int, int], str]:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="oraclehcm", slug=SLUG, source="user", watched=True,
            )
        ).inserted_primary_key[0])
    seed = RawPosting(provider_posting_id=SENTINEL, title="Engineer", url="https://x/s",
                      locations=[], body_text="b", raw_json={})
    apply_board(engine, BoardSnapshot(
        status="complete", postings=[seed], url=provider.board_url(SLUG), observed_validators=None,
        error=None, listed_ids=frozenset({SENTINEL}),
    ), company_id, insert_run(engine))
    for _ in range(2):
        board = site()
        snapshot = _scan(tmp_path, board, board.ids() | {SENTINEL})
        apply_board(engine, snapshot, company_id, insert_run(engine))
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.postings.c.id, tables.postings.c.status,
                   tables.postings.c.consecutive_missing)
            .where(tables.postings.c.company_id == company_id,
                   tables.postings.c.provider_posting_id == SENTINEL)
        ).one()
        closed = conn.execute(select(tables.posting_events.c.id).where(
            tables.posting_events.c.posting_id == row.id,
            tables.posting_events.c.kind == "closed",
        )).all()
    return (row.status, row.consecutive_missing, len(closed)), snapshot.error or ""


def test_null_control_a_readable_split_closes_a_posting_the_board_stopped_listing(
    tmp_path: Path,
) -> None:
    status, error = _two_scans(tmp_path, lambda: _Site(["N0", "N1", "N2"], ["O0", "O1", "O2"]))
    assert status == ("closed", 2, 1)
    assert error == ""


def test_a_child_that_fails_two_nights_running_closes_nothing(tmp_path: Path) -> None:
    status, error = _two_scans(tmp_path, lambda: _site(3, 4, fail=frozenset({"31"})))
    assert status == ("open", 0, 0)
    assert "posting-date facet 31: page at offset 0: " in error


def test_a_child_cut_by_the_page_budget_two_nights_running_closes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the root, 30's two pages and 31's first: the page holding the sentinel is never asked for
    monkeypatch.setattr(oraclehcm, "_SPLIT_MAX_PAGES", 4)
    status, error = _two_scans(tmp_path, lambda: _site(3, 4))
    assert status == ("open", 0, 0)
    assert "posting-date facet 31: stopped, the page budget of 4 is spent" in error
