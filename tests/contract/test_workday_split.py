"""T351: a censored Workday listing is split by facet, inside the board's own scope.

Every test runs against `_Tenant`, a fake CXS search endpoint that behaves as the live service was
measured to: `total` censored at 2,000, offsets past it wrapping to page 1, `total` and `facets`
only at offset 0, two applied groups an AND (genpt, 2026-11-24), and an applied group answered
with its UNFILTERED counts while every other group is re-aggregated over the filtered rows (genpt,
the same day). `locations` sits nested under `locationMainGroup`, as it does live.
"""

from __future__ import annotations

import json
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
from boardwatch.providers import workday
from boardwatch.providers.workday import WorkdayProvider
from boardwatch.rank.heuristic import ProfileView
from boardwatch.rank.listing_gate import build_listing_gate
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run

pytestmark = pytest.mark.usefixtures("no_real_sleep")

SLUG = "acme.wd5.myworkdayjobs.com/acme/AcmeCareers"
LIST_URL = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/jobs"
CENSOR = 2000
NESTED = frozenset({"locations"})  # served inside `locationMainGroup`, as live
provider = WorkdayProvider()


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _pid(index: int) -> str:
    return f"R{index:05d}"


@dataclass
class _Tenant:
    """A planted board: `values[i][group]` is row i's values in that group (several for a
    multi-valued group, none for a row the group does not tag)."""

    values: list[dict[str, list[str]]]
    titles: Callable[[int], str] = lambda index: f"Engineer {index}"
    # a child query this answers 500, keyed on the descriptor it applies
    fail_on: frozenset[str] = frozenset()
    # reported-count drift on the ROOT's facets only, by descriptor
    root_bias: dict[str, int] = field(default_factory=dict)
    # rows the ROOT's facets do not count yet: posted between the root's request and a child's
    root_hidden: frozenset[int] = frozenset()
    # a child query's own stated `total` overstated, by the descriptor it applies
    child_total_bias: dict[str, int] = field(default_factory=dict)
    # serve page 1 again at offset == the query's size, the Intel tail, instead of a short page
    repeat_past_end: bool = False
    # serve page 1 again from this offset on, for a query applying the descriptor
    wrap_at: dict[str, int] = field(default_factory=dict)
    # the size at which `total` is censored; None for a tenant that states its real total
    censor: int | None = CENSOR
    bodies: list[dict[str, Any]] = field(default_factory=list)

    def ids(self) -> frozenset[str]:
        return frozenset(_pid(i) for i in range(len(self.values)))

    def _groups(self) -> list[str]:
        return list(dict.fromkeys(g for row in self.values for g in row))

    def _matches(self, applied: dict[str, list[str]], skip: str | None = None) -> list[int]:
        return [
            i for i, row in enumerate(self.values)
            if all(
                set(row.get(group, [])) & {_descriptor(v) for v in wanted}
                for group, wanted in applied.items() if group != skip
            )
        ]

    def _facets(self, applied: dict[str, list[str]], root: bool) -> list[dict[str, Any]]:
        top: list[dict[str, Any]] = []
        nested: list[dict[str, Any]] = []
        for group in self._groups():
            counts: dict[str, int] = {}
            # an APPLIED group keeps the counts it has without its own filter (measured live)
            for i in self._matches(applied, skip=group):
                if root and i in self.root_hidden:
                    continue
                for value in self.values[i].get(group, []):
                    counts[value] = counts.get(value, 0) + 1
            entries = [
                {
                    "id": f"id-{value}", "descriptor": value,
                    "count": count + (self.root_bias.get(value, 0) if root else 0),
                }
                for value, count in counts.items()
            ]
            facet = {"facetParameter": group, "values": entries}
            (nested if group in NESTED else top).append(facet)
        if nested:
            top.append({"facetParameter": "locationMainGroup", "values": nested})
        return top

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        applied: dict[str, list[str]] = body["appliedFacets"]
        if any(_descriptor(v) in self.fail_on for ids in applied.values() for v in ids):
            return httpx.Response(500)
        matched = self._matches(applied)
        offset = body["offset"]
        wraps = [self.wrap_at[_descriptor(v)] for ids in applied.values() for v in ids
                 if _descriptor(v) in self.wrap_at]
        if (
            (self.censor is not None and offset >= self.censor)
            or (self.repeat_past_end and offset == len(matched) and offset)
            or any(offset >= at for at in wraps)
        ):
            offset = 0  # the wrap: page 1 again, byte for byte
        rows = [
            {
                "externalPath": f"/job/Austin/Role-{i}_{_pid(i)}", "title": self.titles(i),
                "locationsText": "Austin, TX", "postedOn": "Posted 30+ Days Ago",
            }
            for i in matched[offset : offset + 20]
        ]
        payload: dict[str, Any] = {"jobPostings": rows, "total": 0, "facets": []}
        if body["offset"] == 0:
            bias = sum(
                self.child_total_bias.get(_descriptor(v), 0)
                for ids in applied.values() for v in ids
            )
            stated = len(matched) if self.censor is None else min(len(matched), self.censor)
            payload["total"] = stated + bias
            payload["facets"] = self._facets(applied, root=applied == {})
        return httpx.Response(200, json=payload)


def _descriptor(facet_id: str) -> str:
    return facet_id.removeprefix("id-")


def _planted(n: int = 2600) -> list[dict[str, list[str]]]:
    """The ticket's planted board: 2,600 rows, two single-valued dimensions and a multi-valued
    nested `locations`. jobFamilyGroup partitions it 900/700/500/300/200; timeType 2,400/200, so
    a split on it leaves a child still censored."""
    families = [("Eng", 900), ("Ops", 700), ("Sales", 500), ("Legal", 300), ("Admin", 200)]
    family = [name for name, size in families for _ in range(size)]
    rows = []
    for i in range(n):
        locations = [f"L{i % 5}"] + ([f"L{(i + 1) % 5}"] if i % 26 == 0 else [])
        rows.append({
            "jobFamilyGroup": [family[i % len(family)]],
            "timeType": ["Part time" if i % 13 == 0 else "Full time"],
            "locations": locations,
        })
    return rows


def _request(
    known: frozenset[str], budget: int = 0, slug: str = SLUG, url: str = LIST_URL
) -> BoardRequest:
    return BoardRequest(
        provider="workday", slug=slug, url=url, known_posting_ids=known, detail_budget=budget,
    )


def _scan(tmp_path: Path, tenant: _Tenant, known: frozenset[str] | None = None) -> BoardSnapshot:
    with respx.mock:
        respx.post(LIST_URL).mock(side_effect=tenant)
        return provider.fetch_board(
            _fetcher(tmp_path), _request(tenant.ids() if known is None else known)
        )


# ---- 1. exact expected ids --------------------------------------------------------------

def test_a_censored_board_is_split_and_lists_exactly_the_planted_ids(tmp_path: Path) -> None:
    tenant = _Tenant(_planted())
    snapshot = _scan(tmp_path, tenant)
    assert snapshot.listed_ids == tenant.ids()  # all 2,600: none missing past the censor
    assert snapshot.board_enumerated == 2600
    assert snapshot.status == "complete", snapshot.error
    assert (snapshot.board_reported_total, snapshot.board_total_censored) == (2600, True)
    # the root, then one child per jobFamilyGroup value: the cheapest exhaustive plan
    children = [b["appliedFacets"] for b in tenant.bodies[1:] if b["offset"] == 0]
    assert children == [{"jobFamilyGroup": [f"id-{v}"]} for v in
                        ("Eng", "Ops", "Sales", "Legal", "Admin")]
    assert len(tenant.bodies) == 1 + sum(c // 20 + 1 for c in (900, 700, 500, 300, 200))
    assert len(tenant.bodies) <= workday._MAX_PAGES
    assert snapshot.listing_pages == len(tenant.bodies)
    assert snapshot.head_pages is None and snapshot.head_missed is None
    assert snapshot.listing_runs is None


def test_a_split_on_a_multi_valued_group_lists_each_row_once(tmp_path: Path) -> None:
    """jobFamilyGroup here has a child still censored, so the nested, multi-valued `locations`
    ranks first: 100 rows sit under two of its values, and each must be listed once."""
    rows = _planted()
    for i, row in enumerate(rows):
        row["jobFamilyGroup"] = ["Eng" if i < 2300 else "Ops"]
    tenant = _Tenant(rows)
    snapshot = _scan(tmp_path, tenant)
    assert snapshot.status == "complete", snapshot.error
    assert {next(iter(b["appliedFacets"])) for b in tenant.bodies[1:]} == {"locations"}
    assert snapshot.listed_ids == tenant.ids()
    assert snapshot.board_enumerated == 2600  # 2,700 rows by the facet's own counts


def test_a_child_still_censored_is_split_again_under_its_own_size(tmp_path: Path) -> None:
    """timeType is the only exhaustive group, and its Full time child (2,400) is censored
    again. That child's size is read with its own applied group EXCLUDED: that group
    still reports the root's counts, and a size of 2,600 would make every group under it look
    non-exhaustive."""
    rows = _planted()
    for i, row in enumerate(rows):
        del row["jobFamilyGroup"], row["locations"]
        row["workerSubType"] = ["Regular"]  # one value: never a split, but a second count
        if row["timeType"] == ["Full time"]:
            row["Department"] = [f"D{i % 4}"]  # Part time rows carry none: 2,400 of 2,600
    tenant = _Tenant(rows)
    snapshot = _scan(tmp_path, tenant)
    assert snapshot.status == "complete", snapshot.error
    assert snapshot.listed_ids == tenant.ids()
    depth = max(len(b["appliedFacets"]) for b in tenant.bodies)
    assert depth == 2  # Full time, then each Department under it


# ---- 2. yield at equal budget -----------------------------------------------------------

def _accepted(tmp_path: Path, tenant: _Tenant, known: frozenset[str]) -> tuple[int, int]:
    """(ids the real listing gate accepted, ids it gated out) on one scan."""
    gate = build_listing_gate(
        ProfileView(skills=frozenset(), target_titles=(), exclude_titles=("accountant",),
                    locations=(), remote_only=False, target_countries=("USA",)),
        None, "hard",
    )
    with respx.mock:
        respx.post(LIST_URL).mock(side_effect=tenant)
        snapshot = provider.fetch_board(
            _fetcher(tmp_path), _request(known).model_copy(update={"listing_gate": gate})
        )
    # budget 0: every unseen row the gate keeps is deferred, so the deferral IS the accepted count
    assert snapshot.detail_deferred is not None
    return snapshot.detail_deferred, len(snapshot.gated_listings)


def test_on_the_first_split_night_the_split_pager_accepts_more_per_100_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first night a split runs, the store knows what the blind pager could reach: the first
    2,000 rows. Measured through the real `build_listing_gate`, one title in seven gated out.

    Scoped to that night on purpose. Where new rows are spread evenly over the board (a cold
    store, or the steady state after the first sweep), the split accepts MORE ids in all but
    about 4% FEWER per 100 requests: it re-reads the root's first page and ends every child on a
    short page, where the blind pager wastes one wrap page. The figures are in T351's record."""
    def tenant() -> _Tenant:
        return _Tenant(_planted(), titles=lambda i: "Senior Accountant" if i % 7 == 0
                       else f"Engineer {i}")
    known = frozenset(_pid(i) for i in range(CENSOR))
    split_board, blind_board = tenant(), tenant()
    split = _accepted(tmp_path, split_board, known)
    with monkeypatch.context() as patch:
        patch.setattr(workday, "_plan_split", lambda *args: "forced blind")
        blind = _accepted(tmp_path, blind_board, known)
    unknown = range(CENSOR, 2600)
    gated = sum(1 for i in unknown if i % 7 == 0)
    assert split == (len(unknown) - gated, gated)  # every unknown row, through the real gate
    assert blind == (0, 0)  # the blind pager never reaches a row it does not already know
    assert 100 * split[0] / len(split_board.bodies) > 100 * blind[0] / len(blind_board.bodies)


# ---- 3. the two-cycle false-closure test ---------------------------------------------------

SENTINEL = 2599  # an Admin row: listed only in the Admin child


def _store(tmp_path: Path) -> tuple[Any, int]:
    engine = get_engine(tmp_path)
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(conn.execute(
            insert(tables.companies).values(
                name="Acme", provider="workday", slug=SLUG, source="user", watched=True,
            )
        ).inserted_primary_key[0])
    seed = RawPosting(
        provider_posting_id=_pid(SENTINEL), title="Engineer", url="https://x/s",
        locations=[], body_text="b", raw_json={},
    )
    apply_board(engine, BoardSnapshot(
        status="complete", postings=[seed], url=LIST_URL, observed_validators=None,
        error=None, listed_ids=frozenset({_pid(SENTINEL)}),
    ), company_id, insert_run(engine))
    return engine, company_id


def _sentinel(engine: Any, company_id: int) -> tuple[str, int, int]:
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.postings.c.id, tables.postings.c.status,
                   tables.postings.c.consecutive_missing)
            .where(tables.postings.c.company_id == company_id,
                   tables.postings.c.provider_posting_id == _pid(SENTINEL))
        ).one()
        closed = conn.execute(
            select(tables.posting_events.c.id).where(
                tables.posting_events.c.posting_id == row.id,
                tables.posting_events.c.kind == "closed",
            )
        ).all()
    return row.status, row.consecutive_missing, len(closed)


def _two_scans(
    tmp_path: Path, tenant: Callable[[], _Tenant]
) -> tuple[tuple[str, int, int], str]:
    """(the sentinel's status, misses and closed events after two scans, the last scan's error)"""
    engine, company_id = _store(tmp_path)
    for _ in range(2):
        board = tenant()
        snapshot = _scan(tmp_path, board, board.ids() | {_pid(SENTINEL)})
        apply_board(engine, snapshot, company_id, insert_run(engine))
    return _sentinel(engine, company_id), snapshot.error or ""


def test_null_control_a_readable_split_closes_a_posting_the_board_stopped_listing(
    tmp_path: Path,
) -> None:
    """Without this, the two tests below could pass on a fixture that never closes anything:
    the same split, every child readable, and the sentinel no longer on the board."""
    status, error = _two_scans(tmp_path, lambda: _Tenant(_planted()[:SENTINEL]))
    assert status == ("closed", 2, 1)
    assert error == ""


def test_a_child_that_fails_two_nights_running_closes_nothing(tmp_path: Path) -> None:
    status, error = _two_scans(
        tmp_path, lambda: _Tenant(_planted(), fail_on=frozenset({"Admin"}))
    )
    assert status == ("open", 0, 0)
    assert "split jobFamilyGroup=Admin: page at offset 0: " in error


def test_a_child_past_the_page_budget_two_nights_running_closes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forty Admin rows were posted after the root's facets were counted (drift between
    requests), so the plan fits and the listing then runs out of pages inside Admin, the last
    child, before the page that holds the sentinel."""
    plan = 1 + sum(c // 20 + 1 for c in (900, 700, 500, 300, 160))
    monkeypatch.setattr(workday, "_MAX_PAGES", plan)
    def tenant() -> _Tenant:
        return _Tenant(_planted(), root_hidden=frozenset(range(2560, 2600)))

    status, error = _two_scans(tmp_path, tenant)
    assert status == ("open", 0, 0)
    assert "split jobFamilyGroup=Admin: stopped, the page budget of" in error
    board = tenant()
    _scan(tmp_path, board)
    assert len(board.bodies) == plan  # not one page over: the sentinel's page is never asked for


# ---- 4. what must be partial ----------------------------------------------------------------

def test_a_non_exhaustive_split_lists_more_than_a_blind_read_and_stays_partial(
    tmp_path: Path,
) -> None:
    """The only exhaustive group (200 regions) is too dear for the budget; jobFamilyGroup leaves
    200 rows untagged. Splitting on it lists 2,400 rows, more than the blind 2,000, and can
    never certify."""
    rows = _planted()
    for i, row in enumerate(rows):
        row["Region"] = [f"R{i % 200}"]
        if i >= 2400:
            del row["jobFamilyGroup"]
        del row["timeType"], row["locations"]
    snapshot = _scan(tmp_path, _Tenant(rows))
    assert snapshot.status == "partial"
    assert "split on jobFamilyGroup covers 2400 of 2600" in (snapshot.error or "")
    assert snapshot.board_enumerated == 2400


def test_a_censored_child_with_nothing_left_to_split_is_partial(tmp_path: Path) -> None:
    rows = [{"jobFamilyGroup": ["Eng" if i < 2300 else "Ops"]} for i in range(2600)]
    snapshot = _scan(tmp_path, _Tenant(rows))
    assert snapshot.status == "partial"
    assert "jobFamilyGroup=Eng: censored at 2000" in (snapshot.error or "")


def test_a_union_that_matches_the_facet_sum_with_a_leaf_ending_on_the_wrap_is_partial(
    tmp_path: Path,
) -> None:
    """Legal (300) repeats page 1 from offset 200, and the 100 rows it never served were posted
    after the root's facets were counted, so the union (2,500) still meets the root's size. It is
    the leaf's ending that fails the certificate."""
    rows = _planted()
    for row in rows:
        del row["locations"]
    snapshot = _scan(tmp_path, _Tenant(
        rows, wrap_at={"Legal": 200}, root_hidden=frozenset(range(2300, 2400)),
    ))
    assert snapshot.board_reported_total == len(snapshot.listed_ids) == 2500
    assert snapshot.status == "partial"
    assert snapshot.error == (
        "split jobFamilyGroup=Legal: page at offset 200 added no new postings; stopping "
        "(200 collected, listing may be incomplete)"
    )


def test_a_leaf_that_repeats_page_one_exactly_past_its_own_total_is_complete(
    tmp_path: Path,
) -> None:
    """Every jobFamilyGroup value is a multiple of 20, and this tenant answers the page past a
    query's last row with page 1 again instead of a short page, as genpt's Production child did
    live. At exactly the child's own total, with that many rows listed, that is its end."""
    rows = _planted()
    for row in rows:
        del row["locations"]
        row["timeType"] = ["Full time"] if row["jobFamilyGroup"] == ["Eng"] else ["Part time"]
    snapshot = _scan(tmp_path, _Tenant(rows, repeat_past_end=True))
    assert snapshot.listed_ids == frozenset(_pid(i) for i in range(2600))
    assert snapshot.status == "complete", snapshot.error


def test_a_union_short_of_the_root_after_every_child_certified_is_partial(
    tmp_path: Path,
) -> None:
    """The root states 2,605 in both single-valued groups (rows closed between requests), and the
    split is on the multi-valued `locations`, whose 2,700 covers it: every child lists its own
    count exactly, and only the union shows the board is short."""
    rows = _planted()
    for i, row in enumerate(rows):
        row["jobFamilyGroup"] = ["Eng" if i < 2300 else "Ops"]
    snapshot = _scan(tmp_path, _Tenant(rows, root_bias={"Eng": 5, "Full time": 5}))
    assert snapshot.status == "partial"
    assert snapshot.error == (
        "split listed 2600 distinct postings of 2605; listing may be incomplete"
    )


def test_a_size_stated_by_one_group_alone_never_certifies(tmp_path: Path) -> None:
    """The review's replay: one group, and 100 rows past the first page that it does not tag.
    The group sums to 2,500, which is also the only size the page states, so it passes the
    exhaustive test against its own count. One count is not a certificate."""
    rows = [{"jobFamilyGroup": [f"F{i % 5}"]} if i < 2500 else {} for i in range(2600)]
    snapshot = _scan(tmp_path, _Tenant(rows))
    assert len(snapshot.listed_ids) == 2500
    assert snapshot.status == "partial"
    assert snapshot.error == (
        "split a size of 2500 is stated by one count only; listing cannot certify"
    )


def test_a_first_page_row_in_no_child_is_partial_even_when_the_union_meets_the_size(
    tmp_path: Path,
) -> None:
    """Row 5, on the root's first page, carries no jobFamilyGroup. The root's count of Admin is
    one high (a row closed between requests) and one Admin row was posted after it, so every
    count agrees and the union meets the size. Only the first page shows the gap."""
    rows = _planted() + [{"jobFamilyGroup": ["Admin"], "timeType": ["Full time"]}]
    del rows[5]["jobFamilyGroup"]
    snapshot = _scan(tmp_path, _Tenant(
        rows, root_bias={"Admin": 1}, root_hidden=frozenset({2600}),
    ))
    assert _pid(2600) in snapshot.listed_ids
    assert snapshot.status == "partial"
    assert snapshot.error == "split 1 rows of the first page are in no child"


def test_a_child_whose_own_counts_miss_rows_its_parent_counted_is_partial(
    tmp_path: Path,
) -> None:
    """The review's second replay. Full time (2,400 on the root's page) is censored and split
    by Department, which tags only 2,300 of its rows, and so does every other group inside it.
    Part time grew by 100 between requests, so the root's union still meets 2,600. The child's
    own size is its parent's count, so its 2,300 cannot pass."""
    rows = _planted()
    for i, row in enumerate(rows):
        del row["jobFamilyGroup"], row["locations"]
        row["workerSubType"] = ["Regular"]
        if row["timeType"] == ["Full time"]:
            row["Department"] = [f"D{i % 4}"]
    full_time = [i for i, row in enumerate(rows) if row["timeType"] == ["Full time"]]
    part_time = [i for i, row in enumerate(rows) if row["timeType"] == ["Part time"]]
    for i in full_time[-100:]:  # untagged by every group the child is split on
        rows[i] = {"timeType": ["Full time"]}
    # Brand, 200 values (too dear to split on), tags the rest, twice on 100 Part time rows: its
    # 2,600 is the root's second count, so the root's size is corroborated and its union met.
    for i, row in enumerate(rows):
        if "workerSubType" in row:
            row["Brand"] = [f"B{i % 200}"] + ([f"B{(i + 1) % 200}"] if i in part_time[:100] else [])
    rows += [{"timeType": ["Part time"], "workerSubType": ["Regular"]} for _ in range(100)]
    hidden = frozenset(range(2600, 2700))  # posted after the root's facets were counted
    snapshot = _scan(tmp_path, _Tenant(rows, root_hidden=hidden))
    assert snapshot.status == "partial"
    notes = [n for n in (snapshot.error or "").split("; ") if n.startswith("split ")]
    # the root itself is clean: every note is the child's
    assert all(n.startswith("split timeType=Full time: ") for n in notes), notes
    assert "split timeType=Full time: listed 2300 distinct postings of 2400" in notes


def test_a_leaf_short_of_its_parents_count_is_partial_even_when_a_sibling_grew(
    tmp_path: Path,
) -> None:
    """Verification round: a Legal posting moved to Eng after Eng was read, so it is in no child,
    and an Admin posting was added. Legal lists its own 299 exactly and the union meets 2,600;
    only the parent's count of 300 for Legal shows the gap."""
    rows = _planted() + [{"jobFamilyGroup": ["Admin"], "timeType": ["Full time"]}]
    rows[2150] = {"timeType": rows[2150]["timeType"]}  # left Legal; Eng was read before it came
    snapshot = _scan(tmp_path, _Tenant(
        rows, root_bias={"Legal": 1}, root_hidden=frozenset({2600}),
    ))
    assert snapshot.status == "partial"
    assert "split jobFamilyGroup=Legal: incomplete listing: collected 299 of 300 postings" in (
        snapshot.error or ""
    )


def test_a_ragged_facet_parameter_is_never_a_witness(tmp_path: Path) -> None:
    """Verification round: one valid group, and a ragged entry carrying a copy of its counts,
    must not corroborate the size."""
    rows = [{"jobFamilyGroup": [f"F{i % 5}"]} if i < 2500 else {} for i in range(2600)]
    tenant = _Tenant(rows)
    original = tenant._facets

    def ragged(applied: dict[str, list[str]], root: bool) -> list[dict[str, Any]]:
        facets = original(applied, root)
        return [*facets, {**facets[0], "facetParameter": []}]

    tenant._facets = ragged  # type: ignore[method-assign]
    snapshot = _scan(tmp_path, tenant)
    assert snapshot.status == "partial"
    assert "stated by one count only" in (snapshot.error or "")


def test_a_censored_slice_with_no_recovered_size_and_an_early_end_is_partial(
    tmp_path: Path,
) -> None:
    """Verification round: censored, with only its applied group in the facets, so no size and
    no split, and the pager ends on a short page before 2,000 rows."""
    rows = [{"Country": ["USA"]} for _ in range(2500)]
    tenant = _Tenant(rows)
    original = tenant.__call__

    def early(request: httpx.Request) -> httpx.Response:
        response = original(request)
        body = json.loads(request.content)
        if body["appliedFacets"] and body["offset"] >= 1000:
            return httpx.Response(200, json={"jobPostings": [], "total": 0, "facets": []})
        return response

    with respx.mock:
        respx.post(LIST_URL).mock(side_effect=early)
        snapshot = provider.fetch_board(_fetcher(tmp_path), _request(
            tenant.ids(), slug=f"{SLUG}#Country=USA", url=f"{LIST_URL}#Country=USA",
        ))
    assert (snapshot.board_total_censored, snapshot.board_reported_total) == (True, None)
    assert snapshot.status == "partial"
    assert "incomplete listing: collected 1000 of 2000 postings" in (snapshot.error or "")


def test_a_ragged_facet_parameter_does_not_crash_a_censored_board(tmp_path: Path) -> None:
    tenant = _Tenant(_planted())
    original = tenant._facets

    def ragged(applied: dict[str, list[str]], root: bool) -> list[dict[str, Any]]:
        return [*original(applied, root), {"facetParameter": [], "values": []}, 7]

    tenant._facets = ragged  # type: ignore[method-assign]
    assert _scan(tmp_path, tenant).status == "complete"


def test_a_leaf_that_lists_fewer_rows_than_its_own_total_is_partial(tmp_path: Path) -> None:
    """Legal states 310 and serves 300 before its short page. The union still meets the root's
    2,600, so only the leaf's own count can catch it."""
    snapshot = _scan(tmp_path, _Tenant(_planted(), child_total_bias={"Legal": 10}))
    assert snapshot.status == "partial"
    assert snapshot.error == (
        "split jobFamilyGroup=Legal: incomplete listing: collected 300 of 310 postings"
    )


# ---- 5. a sliced board stays inside its slice; 6. an uncensored board is untouched -----

def test_a_sliced_boards_split_never_reads_outside_its_slice(tmp_path: Path) -> None:
    rows = _planted()
    for i, row in enumerate(rows):
        row["Country"] = ["USA"] if i < 2500 else ["Canada"]
    rows += [{"Country": ["Canada"], "jobFamilyGroup": ["Eng"]} for _ in range(300)]
    tenant = _Tenant(rows)
    with respx.mock:
        respx.post(LIST_URL).mock(side_effect=tenant)
        snapshot = provider.fetch_board(_fetcher(tmp_path), _request(
            tenant.ids(), slug=f"{SLUG}#Country=USA", url=f"{LIST_URL}#Country=USA",
        ))
    assert tenant.bodies[0]["appliedFacets"] == {}  # the catalog read, as every slice does
    assert all(b["appliedFacets"].get("Country") == ["id-USA"] for b in tenant.bodies[1:])
    assert snapshot.listed_ids == frozenset(_pid(i) for i in range(2500))
    assert snapshot.status == "complete", snapshot.error
    assert snapshot.board_reported_total == 2500  # the slice's size, not its parent's 2,900


def test_an_uncensored_board_over_2000_still_pages_blind_to_the_backstop(tmp_path: Path) -> None:
    """A tenant that states its real total above 2,000 (CVS, Lowe's) is not censored, so it is
    never split: 150 pages and the backstop's note, exactly as before."""
    tenant = _Tenant(_planted(3100), censor=None)
    snapshot = _scan(tmp_path, tenant)
    assert [(b["appliedFacets"], b["offset"]) for b in tenant.bodies] == [
        ({}, offset) for offset in range(0, 150 * 20, 20)
    ]
    assert snapshot.board_total_censored is False
    assert snapshot.error == (
        "page cap of 150 pages reached; listing may be incomplete, treating as partial so "
        "unseen postings are not closed"
    )


def test_an_uncensored_board_sends_exactly_the_blind_pagers_requests(tmp_path: Path) -> None:
    tenant = _Tenant(_planted(1500))
    snapshot = _scan(tmp_path, tenant)
    assert [(b["appliedFacets"], b["offset"]) for b in tenant.bodies] == [
        ({}, offset) for offset in range(0, 1501, 20)
    ]
    assert snapshot.status == "complete"
    assert snapshot.head_pages is not None  # the head-scan shadow still runs off a blind read
