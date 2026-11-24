"""T340's shadow: where a newest-first head scan would have stopped, and what it would have missed.

The rule is T338's measured one (2026-11-24): stop after HEAD_QUIET_PAGES (2) consecutive pages with
no new row and no row dated within the last day. Each test below fails against a named wrong
version: one quiet page (K = 1), no date guard, or a miss count that is not the rows beyond the stop.
"""

from __future__ import annotations

import copy
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import Engine, insert, select

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers import base
from boardwatch.providers.base import HeadShadow, head_scan_shadow, listed_within_a_day
from boardwatch.providers.oraclehcm import OracleHCMProvider
from boardwatch.providers.smartrecruiters import SmartRecruitersProvider
from boardwatch.providers.workday import WorkdayProvider, _listed_day
from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run

pytestmark = pytest.mark.usefixtures("no_real_sleep")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TODAY = date(2026, 11, 24)
NEW, OLD_KNOWN, FRESH_KNOWN = (True, False), (False, False), (False, True)


@pytest.fixture(autouse=True)
def _pinned_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "utcnow", lambda: datetime(2026, 11, 24, 12, 0))


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(Settings(data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
                            per_host_delay_seconds=0.25))


# ------------------------------------------------------------------------- the rule itself

def test_it_stops_after_two_quiet_pages_and_counts_the_new_rows_beyond() -> None:
    pages = [[NEW], [OLD_KNOWN], [OLD_KNOWN], [NEW, NEW], [OLD_KNOWN]]
    assert head_scan_shadow(pages) == HeadShadow(5, 3, 2)


def test_one_quiet_page_between_busy_ones_does_not_stop_it() -> None:
    # K = 1 would stop at page 2 and miss the new row on page 3.
    pages = [[NEW], [OLD_KNOWN], [NEW], [OLD_KNOWN]]
    assert head_scan_shadow(pages) == HeadShadow(4, 4, 0)


def test_a_burst_of_fresh_rows_keeps_it_reading() -> None:
    # DaVita and CarMax list 6-9 pages of rows posted today, most of them gated. Without the
    # date guard these pages read quiet and the new row after the burst is missed.
    pages = [[FRESH_KNOWN], [FRESH_KNOWN], [FRESH_KNOWN], [NEW], [OLD_KNOWN]]
    assert head_scan_shadow(pages) == HeadShadow(5, 5, 0)


def test_an_unreadable_date_is_fresh_and_two_days_old_is_not() -> None:
    assert listed_within_a_day(None, TODAY)
    assert listed_within_a_day(date(2026, 11, 23), TODAY)
    assert not listed_within_a_day(date(2026, 11, 22), TODAY)


@pytest.mark.parametrize(("text", "expected"), [
    ("Posted Today", date(2026, 11, 24)),
    ("Posted Yesterday", date(2026, 11, 23)),
    ("Posted 3 Days Ago", date(2026, 11, 21)),
    ("Posted 30+ Days Ago", date(2026, 10, 25)),
    ("", None),
    ("Publié aujourd'hui", None),  # a localized tenant: unreadable, so the head scan keeps paging
])
def test_workday_reads_its_relative_posted_text(text: str, expected: date | None) -> None:
    assert _listed_day({"postedOn": text}, TODAY) == expected


# ------------------------------------------------------------- each provider, end to end
# Five pages: page 0 holds new rows, pages 1-2 are old and known (the stop), page 3 holds ONE new
# old row (the miss), page 4 is the last. Expected everywhere: 5 pages, 3 read, 1 missed.

def _plan(page_size: int, last: int) -> list[list[tuple[int, bool, bool]]]:
    """(id, known, fresh) per row, per page."""
    pages, n = [], 0
    for index, size in enumerate([page_size] * 4 + [last]):
        rows = []
        for i in range(size):
            known = not ((index == 0 and i < 2) or (index == 3 and i == 0))
            rows.append((n, known, index == 0))
            n += 1
        pages.append(rows)
    return pages


EXPECTED = (5, 3, 1)


def _shadow(snapshot: BoardSnapshot) -> tuple[int | None, int | None, int | None]:
    return snapshot.listing_pages, snapshot.head_pages, snapshot.head_missed


@respx.mock
def test_workday_records_the_shadow(tmp_path: Path) -> None:
    host, url = "acme.wd5.myworkdayjobs.com", "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/jobs"
    template = json.loads((FIXTURES / "workday/list_page_full.json").read_text())
    plan = _plan(20, 5)

    def page(rows: list[tuple[int, bool, bool]]) -> dict[str, Any]:
        payload = copy.deepcopy(template)
        payload["jobPostings"] = [
            {**template["jobPostings"][0], "externalPath": f"/job/Austin/Role_JR{n}",
             "postedOn": "Posted Today" if fresh else "Posted 30+ Days Ago"}
            for n, _, fresh in rows
        ]
        return payload

    respx.post(url).mock(side_effect=[httpx.Response(200, json=page(p)) for p in plan])
    respx.get(url__regex=rf"https://{host}/wday/cxs/acme/AcmeCareers/job/.*").mock(
        return_value=httpx.Response(200, json=json.loads((FIXTURES / "workday/detail_normal.json").read_text()))
    )
    known = frozenset(f"JR{n}" for p in plan for n, k, _ in p if k)
    snap = WorkdayProvider().fetch_board(_fetcher(tmp_path), BoardRequest(
        provider="workday", slug=f"{host}/acme/AcmeCareers", url=url, known_posting_ids=known))
    assert _shadow(snap) == EXPECTED


@respx.mock
def test_smartrecruiters_records_the_shadow(tmp_path: Path) -> None:
    template = json.loads((FIXTURES / "smartrecruiters/list_normal.json").read_text())
    plan = _plan(100, 10)
    total = sum(len(p) for p in plan)
    for index, rows in enumerate(plan):
        payload = {**template, "offset": index * 100, "totalFound": total, "content": [
            {**template["content"][0], "id": str(n),
             "releasedDate": "2026-11-24T08:00:00.000Z" if fresh else "2026-09-01T08:00:00.000Z"}
            for n, _, fresh in rows
        ]}
        respx.get(f"https://api.smartrecruiters.com/v1/companies/acme/postings?limit=100&offset={index * 100}").mock(
            return_value=httpx.Response(200, json=payload))
    respx.get(url__regex=r"https://api\.smartrecruiters\.com/v1/companies/acme/postings/\d+$").mock(
        return_value=httpx.Response(200, content=(FIXTURES / "smartrecruiters/detail_normal.json").read_bytes()))
    known = frozenset(str(n) for p in plan for n, k, _ in p if k)
    url = "https://api.smartrecruiters.com/v1/companies/acme/postings?limit=100&offset=0"
    snap = SmartRecruitersProvider().fetch_board(_fetcher(tmp_path), BoardRequest(
        provider="smartrecruiters", slug="acme", url=url, known_posting_ids=known))
    assert _shadow(snap) == EXPECTED


@respx.mock
def test_oraclehcm_records_the_shadow(tmp_path: Path) -> None:
    host = "acme.fa.us2.oraclecloud.com"
    template = json.loads((FIXTURES / "oraclehcm/list_page_full.json").read_text())
    plan = _plan(200, 10)
    provider = OracleHCMProvider()
    for index, rows in enumerate(plan):
        payload = copy.deepcopy(template)
        item = payload["items"][0]
        item["TotalJobsCount"] = sum(len(p) for p in plan)
        item["requisitionList"] = [
            {**template["items"][0]["requisitionList"][0], "Id": str(n),
             "PostedDate": "2026-11-24" if fresh else "2026-09-01"}
            for n, _, fresh in rows
        ]
        respx.get(provider._page_url(host, "CX_1", offset=index * 200)).mock(
            return_value=httpx.Response(200, json=payload))
    respx.get(url__regex=rf"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails.*").mock(
        return_value=httpx.Response(200, content=(FIXTURES / "oraclehcm/detail_normal.json").read_bytes()))
    known = frozenset(str(n) for p in plan for n, k, _ in p if k)
    snap = provider.fetch_board(_fetcher(tmp_path), BoardRequest(
        provider="oraclehcm", slug=f"{host}/CX_1", url=provider.board_url(f"{host}/CX_1"),
        known_posting_ids=known))
    assert _shadow(snap) == EXPECTED


# ------------------------------------------------------------------------------ persisted

@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def test_the_scan_row_carries_the_shadow_and_null_where_none_was_computed(engine: Engine) -> None:
    with engine.begin() as conn:
        company_id = int(conn.execute(insert(tables.companies).values(
            name="Acme", provider="workday", slug="acme", source="user", watched=True,
        )).inserted_primary_key[0])
    run_id = insert_run(engine)
    apply_board(engine, BoardSnapshot(status="partial", postings=[], url="https://x/y",
                                      listing_pages=40, head_pages=3, head_missed=0),
                company_id, run_id)
    apply_board(engine, BoardSnapshot(status="partial", postings=[], url="https://x/y"),
                company_id, run_id)
    with engine.connect() as conn:
        rows = conn.execute(select(tables.board_scans.c.listing_pages, tables.board_scans.c.head_pages,
                                   tables.board_scans.c.head_missed)
                            .order_by(tables.board_scans.c.id)).all()
    assert [tuple(r) for r in rows] == [(40, 3, 0), (None, None, None)]
