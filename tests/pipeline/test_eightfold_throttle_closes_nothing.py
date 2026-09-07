"""A board a throttle stopped mid-listing must close NOTHING (T74 part A, the dangerous edge).

The provider-level contract test pins `status == "partial"`; this pins the CONSEQUENCE, through
`apply_board` and the store, because that is where the damage would land. `_process_missing`
runs on `complete` snapshots only and `CLOSE_AFTER_MISSES` is 2, so a throttled board that
reported `complete` twice would delete every posting the throttle stopped it from listing —
2,150 of them across four boards on the run that measured this.

Counted through a different path than the one that produced it: the provider decides the status,
and this asserts on `postings.status` read back out of SQLite.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import insert, select

from boardwatch.core.models import BoardRequest
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers import eightfold
from boardwatch.providers.eightfold import EightfoldProvider
from boardwatch.scan.apply import CLOSE_AFTER_MISSES, apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "eightfold"
SLUG = "careers.acme.test"
DOMAIN = "acme.test"
BOOT_URL = f"https://{SLUG}/careers"
provider = EightfoldProvider()


@pytest.fixture(autouse=True)
def _pinned_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(eightfold, "_THROTTLE_BACKOFF_SECONDS", (0.0,) * eightfold._THROTTLE_RETRIES)


def _boot_html() -> bytes:
    escaped = json.dumps({"domain": DOMAIN}).replace('"', "&#34;")
    return (
        b'<!DOCTYPE html><html><body><code id="pcsx-data">'
        + escaped.encode()
        + b"</code></body></html>"
    )


def _search_url(start: int) -> str:
    return f"https://{SLUG}/api/pcsx/search?domain={DOMAIN}&start={start}"


def _detail_url(posting_id: str) -> str:
    return (
        f"https://{SLUG}/api/pcsx/position_details?domain={DOMAIN}&position_id={posting_id}"
    )


def _page(ids: list[str], count: int) -> dict[str, object]:
    """One `/api/pcsx/search` page in the recorded envelope shape, all text synthetic."""
    return {
        "status": 200,
        "error": {"message": "", "body": ""},
        "data": {
            "count": count,
            "positions": [
                {
                    "id": int(pid),
                    "name": f"Synthetic Role {pid}",
                    "locations": ["Springfield, Acmeland"],
                    "workLocationOption": "onsite",
                    "department": "Engineering",
                    "positionUrl": f"/careers/job/{pid}",
                    "postedTs": 1788652800,
                }
                for pid in ids
            ],
        },
        "metadata": None,
    }


def _mock_board(ids: list[str], count: int | None = None) -> None:
    respx.get(BOOT_URL).mock(return_value=httpx.Response(200, content=_boot_html()))
    respx.get(_search_url(0)).mock(
        return_value=httpx.Response(200, json=_page(ids, count if count is not None else len(ids)))
    )
    for pid in ids:
        detail = _page([pid], 1)["data"]["positions"][0]  # type: ignore[index]
        respx.get(_detail_url(pid)).mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": 200,
                    "error": {"message": "", "body": ""},
                    "data": dict(detail, jobDescription="<p>Synthetic body.</p>"),
                    "metadata": None,
                },
            )
        )


def _request(known: frozenset[str] = frozenset()) -> BoardRequest:
    return BoardRequest(
        provider="eightfold", slug=SLUG, url=BOOT_URL, known_posting_ids=known, detail_budget=50
    )


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _open_ids(engine, company_id: int) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.postings.c.provider_posting_id).where(
                tables.postings.c.company_id == company_id,
                tables.postings.c.status == "open",
            )
        ).all()
    return {row.provider_posting_id for row in rows}


@respx.mock
def test_a_permanently_throttled_board_closes_nothing_however_many_runs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme Corp", provider="eightfold", slug=SLUG,
                    source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )

    # Run 1: the board answers in full. Three postings land open.
    listed = ["1000000000001", "1000000000002", "1000000000003"]
    _mock_board(listed)
    first = provider.fetch_board(_fetcher(tmp_path), _request())
    assert first.status == "complete"
    apply_board(engine, first, company_id, insert_run(engine))
    assert _open_ids(engine, company_id) == set(listed)

    # Runs 2..N: the search endpoint is throttled from the FIRST page onwards, exactly as it was
    # on the four boards run 10 lost rows on. More runs than CLOSE_AFTER_MISSES, so a board that
    # reported `complete` with an empty inventory would have closed all three by now.
    respx.get(_search_url(0)).mock(return_value=httpx.Response(405))
    for _ in range(CLOSE_AFTER_MISSES + 1):
        throttled = provider.fetch_board(_fetcher(tmp_path), _request(known=frozenset(listed)))
        assert throttled.status != "complete"
        assert throttled.throttle_exhausted == 1
        apply_board(engine, throttled, company_id, insert_run(engine))

    assert _open_ids(engine, company_id) == set(listed)


@respx.mock
def test_a_board_throttled_after_its_first_page_still_closes_nothing(tmp_path: Path) -> None:
    """The narrower arm: page 0 answers, page 1 does not. The board has a real but SHORT
    inventory, which is the shape that would silently close the tail of a large board."""
    data_dir = tmp_path / "data"
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme Corp", provider="eightfold", slug=SLUG,
                    source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )

    full = [f"10000000000{i:02d}" for i in range(10)]
    tail = ["1000000000099"]
    respx.get(BOOT_URL).mock(return_value=httpx.Response(200, content=_boot_html()))
    # `count` is 10, matching page 0 exactly, so the completeness note in `fetch_board`
    # ("collected N of M") can NEVER be what carries the `partial` below — only the throttle
    # can. Without that the test passes against a retry that reports `complete` on exhaustion.
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=_page(full, 10)))
    respx.get(_search_url(10)).mock(return_value=httpx.Response(200, json=_page(tail, 10)))
    for pid in full + tail:
        detail = _page([pid], 1)["data"]["positions"][0]  # type: ignore[index]
        respx.get(_detail_url(pid)).mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": 200, "error": {"message": "", "body": ""},
                    "data": dict(detail, jobDescription="<p>Synthetic body.</p>"),
                    "metadata": None,
                },
            )
        )
    first = provider.fetch_board(_fetcher(tmp_path), _request())
    assert first.status == "complete"
    apply_board(engine, first, company_id, insert_run(engine))
    assert _open_ids(engine, company_id) == set(full + tail)

    # Now only the SECOND page is throttled: the board still lists ten of eleven postings.
    respx.get(_search_url(10)).mock(return_value=httpx.Response(405))
    for _ in range(CLOSE_AFTER_MISSES + 1):
        throttled = provider.fetch_board(
            _fetcher(tmp_path), _request(known=frozenset(full + tail))
        )
        assert throttled.status == "partial"
        assert throttled.listed_ids == frozenset(full)  # the tail is simply not in evidence
        apply_board(engine, throttled, company_id, insert_run(engine))

    # The tail posting is absent from `listed_ids` on three consecutive scans and is STILL open,
    # because a `partial` snapshot is not evidence of absence.
    assert _open_ids(engine, company_id) == set(full + tail)
