"""T305: board and provider health, read from the LATEST `board_scans` row per watched board and
`companies.last_health`.

Every expected value is hand-computed from the rows seeded below, not recomputed by the code
under test. Each control varies ONE clause against a board that must differ:

* an OLDER bad scan under a newer good one must not flag the board (latest only);
* a LANE-kind failure after a clean board scan must not flag the board (board-kind only);
* an UNWATCHED dead company must not appear;
* an `unchanged` (304) scan after a slow full read must not hide the slow read;
* NULL totals are "not measured" and never a mismatch.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert

from boardwatch.core.settings import load_settings
from boardwatch.delivery.api import ApiContext
from boardwatch.store.board_health_queries import (
    ISSUES,
    KNOWN_HEALTH,
    KNOWN_SCAN_STATUS,
    _Scan,
    classify_board,
    load_board_health,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import board_scans, companies, runs
from tests.conftest import write_bundled_role_taxonomy
from tests.unit.test_web_server import call, serving

T0 = datetime(2026, 11, 17, 4, 0, 0)


@pytest.fixture(autouse=True)
def _scratch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    write_bundled_role_taxonomy(tmp_path / "config")


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


def _company(
    conn: Connection,
    name: str,
    provider: str,
    *,
    health: str | None = "ok",
    watched: bool = True,
) -> int:
    return int(
        conn.execute(
            insert(companies).values(
                name=name,
                provider=provider,
                slug=name.lower().replace(" ", "-"),
                source="user",
                watched=watched,
                last_health=health,
            )
        ).inserted_primary_key[0]
    )


def _scan(
    conn: Connection,
    run_id: int,
    company_id: int,
    status: str,
    *,
    seconds: float = 1.0,
    kind: str = "board",
    dead: bool = False,
    reported: int | None = None,
    enumerated: int | None = None,
    gated: int | None = None,
    listed: int = 0,
    error: str | None = None,
) -> None:
    conn.execute(
        insert(board_scans).values(
            run_id=run_id,
            company_id=company_id,
            started_at=T0,
            finished_at=T0 + timedelta(seconds=seconds),
            status=status,
            postings_listed=listed,
            error=error,
            dead=dead,
            scan_kind=kind,
            board_reported_total=reported,
            board_enumerated=enumerated,
            listing_gated=gated,
        )
    )


def _seed(engine: Engine) -> dict[str, int]:
    ids: dict[str, int] = {}
    with engine.begin() as conn:
        run = int(conn.execute(insert(runs).values(started_at=T0)).inserted_primary_key[0])

        ids["dead"] = _company(conn, "Dead Co", "greenhouse", health="dead")
        _scan(conn, run, ids["dead"], "complete", seconds=9.0, listed=4)  # OLDER, good
        _scan(conn, run, ids["dead"], "failed", seconds=2.0, dead=True, error="404")

        ids["healthy"] = _company(conn, "Healthy", "greenhouse")
        _scan(conn, run, ids["healthy"], "complete", seconds=3.0, reported=5, enumerated=5, listed=5)

        ids["mismatch"] = _company(conn, "Short Board", "workday")
        _scan(conn, run, ids["mismatch"], "partial", seconds=12.0, reported=100, enumerated=60)

        ids["over"] = _company(conn, "Over Board", "workday")
        _scan(conn, run, ids["over"], "complete", seconds=4.0, reported=10, enumerated=12)

        ids["failing"] = _company(conn, "Failing Co", "lever", health="ok")
        _scan(conn, run, ids["failing"], "failed", seconds=1.5, error="HTTP 503")

        ids["empty"] = _company(conn, "Empty Co", "ashby", health="empty")
        _scan(conn, run, ids["empty"], "complete", seconds=0.5, reported=0, enumerated=0)

        ids["partial"] = _company(conn, "Partial Co", "ashby", health="ok")
        _scan(conn, run, ids["partial"], "partial", seconds=6.0)  # totals NULL: not measured

        ids["unreachable"] = _company(conn, "Unreachable Co", "lever", health="unreachable")
        _scan(conn, run, ids["unreachable"], "complete", seconds=1.0)

        ids["gated"] = _company(conn, "Gated Co", "workday")
        _scan(conn, run, ids["gated"], "complete", seconds=2.0, gated=30, listed=0)

        ids["unscanned"] = _company(conn, "Unscanned Co", "ashby", health=None)

        ids["lane"] = _company(conn, "Lane Touched", "ashby")
        _scan(conn, run, ids["lane"], "complete", seconds=1.0, listed=2)
        _scan(conn, run, ids["lane"], "failed", seconds=99.0, kind="lane")  # not the board's

        ids["unwatched"] = _company(conn, "Unwatched Dead", "ashby", health="dead", watched=False)
        _scan(conn, run, ids["unwatched"], "failed", seconds=1.0, dead=True)

        ids["slow"] = _company(conn, "Slow Co", "smartrecruiters")
        _scan(conn, run, ids["slow"], "complete", seconds=30.0, listed=7)
        _scan(conn, run, ids["slow"], "unchanged", seconds=0.1)  # newest row, but a 304
    return ids


def test_each_board_gets_the_one_issue_its_latest_state_calls_for(engine: Engine) -> None:
    ids = _seed(engine)
    with engine.connect() as conn:
        payload = load_board_health(conn)

    by_id = {row["company_id"]: row for row in payload["boards"]}
    issues = {name: by_id[ids[name]]["issue"] for name in
              ("dead", "mismatch", "over", "failing", "empty", "partial", "unreachable")}
    assert issues == {
        "dead": "dead",
        "mismatch": "mismatch",
        "over": "mismatch",
        "failing": "error",
        "empty": "empty",
        "partial": "partial",
        "unreachable": "unreachable",
    }
    # Healthy, never-scanned, gated, lane-touched, slow and unwatched boards are NOT rows.
    for quiet in ("healthy", "unscanned", "gated", "lane", "slow", "unwatched"):
        assert ids[quiet] not in by_id, quiet
    assert len(payload["boards"]) == 7
    assert payload["watched_boards"] == 12  # 13 companies seeded, one unwatched


def test_every_row_says_what_to_do_in_words_from_its_status(engine: Engine) -> None:
    ids = _seed(engine)
    with engine.connect() as conn:
        by_id = {r["company_id"]: r for r in load_board_health(conn)["boards"]}

    assert by_id[ids["dead"]]["action"] == "remove the board or fix its slug"
    assert by_id[ids["failing"]]["action"] == "check the board; retry next run"
    assert by_id[ids["mismatch"]]["action"] == "postings may be missing; re-scan"
    assert by_id[ids["unreachable"]]["action"] == "the provider did not answer; wait and retry next run"
    assert by_id[ids["empty"]]["action"].startswith("the board lists no postings; wait")
    assert by_id[ids["partial"]]["action"] == "the scan stopped early; retry next run"
    assert by_id[ids["failing"]]["label"] == "failing"


def test_the_latest_scan_decides_not_an_older_one(engine: Engine) -> None:
    """Dead Co has an older COMPLETE scan under a newer dead one; the lane control has an
    older complete board scan under a newer failed LANE scan and must stay quiet."""
    ids = _seed(engine)
    with engine.connect() as conn:
        by_id = {r["company_id"]: r for r in load_board_health(conn)["boards"]}
    assert by_id[ids["dead"]]["scan_status"] == "failed"
    assert ids["lane"] not in by_id


def test_a_count_mismatch_carries_the_gap_and_null_totals_never_flag(engine: Engine) -> None:
    ids = _seed(engine)
    with engine.connect() as conn:
        by_id = {r["company_id"]: r for r in load_board_health(conn)["boards"]}
    short = by_id[ids["mismatch"]]
    assert (short["reported_total"], short["enumerated"], short["missing"]) == (100, 60, 40)
    over = by_id[ids["over"]]
    assert over["missing"] == -2  # the scan counted MORE than the board reported
    # Partial with NULL totals is a partial scan, not a count mismatch.
    assert by_id[ids["partial"]]["missing"] is None
    assert by_id[ids["partial"]]["issue"] == "partial"


def test_provider_rollup_counts_are_hand_computed(engine: Engine) -> None:
    _seed(engine)
    with engine.connect() as conn:
        providers = {p["provider"]: p for p in load_board_health(conn)["providers"]}

    gh = providers["greenhouse"]  # Dead Co, Healthy
    assert (gh["boards"], gh["healthy"], gh["dead"]) == (2, 1, 1)
    wd = providers["workday"]  # Short Board, Over Board, Gated Co
    assert (wd["boards"], wd["healthy"], wd["mismatch"]) == (3, 1, 2)
    assert (wd["gated_boards"], wd["gated_postings"]) == (1, 30)
    lv = providers["lever"]  # Failing Co, Unreachable Co
    assert (lv["boards"], lv["error"], lv["unreachable"], lv["healthy"]) == (2, 1, 1, 0)
    ash = providers["ashby"]  # Empty, Partial, Unscanned, Lane Touched (Unwatched excluded)
    assert (ash["boards"], ash["healthy"], ash["empty"], ash["partial"]) == (4, 2, 1, 1)
    assert providers["smartrecruiters"]["boards"] == 1


def test_scan_length_is_the_latest_scan_that_read_the_board(engine: Engine) -> None:
    ids = _seed(engine)
    with engine.connect() as conn:
        payload = load_board_health(conn)

    # Slow Co's newest row is a 0.1 s 304; its real read took 30 s and is what is timed.
    assert payload["slowest"][0]["company_id"] == ids["slow"]
    assert payload["slowest"][0]["seconds"] == 30.0
    assert [s["seconds"] for s in payload["slowest"][:3]] == [30.0, 12.0, 6.0]
    assert 99.0 not in [s["seconds"] for s in payload["slowest"]]  # lane scan is not timed
    providers = {p["provider"]: p for p in payload["providers"]}
    # greenhouse: Dead Co newest non-304 is the 2.0 s failure, Healthy 3.0 s -> avg 2.5, max 3.0
    assert (providers["greenhouse"]["seconds_avg"], providers["greenhouse"]["seconds_max"]) == (2.5, 3.0)
    # smartrecruiters: only the 30 s read
    assert providers["smartrecruiters"]["seconds_avg"] == 30.0
    # a provider whose boards were never scanned has no timing, not 0
    with engine.begin() as conn:
        _company(conn, "Never Scanned", "jibe", health=None)
    with engine.connect() as conn:
        jibe = {p["provider"]: p for p in load_board_health(conn)["providers"]}["jibe"]
    assert (jibe["seconds_avg"], jibe["seconds_max"]) == (None, None)


def test_rows_are_ordered_worst_first(engine: Engine) -> None:
    _seed(engine)
    with engine.connect() as conn:
        order = [r["issue"] for r in load_board_health(conn)["boards"]]
    assert order == ["dead", "unreachable", "error", "mismatch", "mismatch", "partial", "empty"]


def test_every_closed_catalog_value_maps_and_an_unknown_value_is_shown_not_dropped() -> None:
    def scan(status: str = "complete", *, dead: bool = False) -> _Scan:
        return _Scan(status, dead, None, None, None, None, T0, T0)

    # Every last_health value in the enum maps to a defined outcome.
    assert {h: classify_board(h, None) for h in sorted(KNOWN_HEALTH)} == {
        "dead": "dead", "empty": "empty", "error": "error", "ok": None, "unreachable": "unreachable",
    }
    # Every scan status in the enum maps too.
    assert {s: classify_board("ok", scan(s)) for s in sorted(KNOWN_SCAN_STATUS)} == {
        "complete": None, "failed": "error", "partial": "partial", "unchanged": None,
    }
    # Outside both catalogs: "unknown", whose label is "unknown status" -- never None (dropped).
    assert classify_board("not-a-status", None) == "unknown"
    assert classify_board("ok", scan("not-a-status")) == "unknown"
    assert ISSUES["unknown"][0] == "unknown status"
    # Every issue the classifier can return has words.
    assert {classify_board(h, None) for h in KNOWN_HEALTH} - {None} <= set(ISSUES)


def test_the_route_serves_the_payload_and_needs_the_token(
    tmp_path: Path, engine: Engine
) -> None:
    ids = _seed(engine)
    (tmp_path / "out").mkdir()
    (tmp_path / "queue").mkdir()
    ctx = ApiContext(
        settings=load_settings(),
        out_root=(tmp_path / "out").resolve(),
        queue_root=(tmp_path / "queue").resolve(),
        owner_name="Example Owner",
        platform="darwin",
    )
    with serving(ctx) as live:
        assert call(live, "/api/board-health").status == 401
        response = call(live, "/api/board-health", bearer=live.token)
    assert response.status == 200
    payload = response.json()
    assert payload["watched_boards"] == 12
    assert {r["company_id"] for r in payload["boards"]} >= {ids["dead"], ids["failing"]}
    assert payload["slowest"][0]["seconds"] == 30.0
