"""`boardwatch seeds` — the read-only report over seeds no ENABLED resolver can select (D-426).

Invocation shape follows `tests/cli/test_coverage_cmd.py`, the sibling command this mirrors.
The properties here are the ones a review found unverified, and two of them are where real defects
were living: that `claimable` comes from ONE snapshot rather than two reads a writer can straddle,
and that `--limit` is honoured on the `--json` path.

**`BOARDWATCH_CONFIG_DIR` is pinned in every test, never inherited.** `conftest.py` autouses
`BOARDWATCH_DATA_DIR` but deliberately does NOT pin the config dir, so without this these tests
would read the operator's real `config.toml` — and `lanes_enabled` is exactly what they assert on,
so they would pass or fail according to whose machine ran them.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run
from boardwatch.store.seed_queries import record_seeds

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)

_URLS = tuple(f"https://grnh.se/{i}" for i in range(5)) + (
    "https://click.appcast.io/a",
    "https://click.appcast.io/b",
    "https://ttigroup.com/x",
    # On jsonld's own catalog, so it is claimable WHEN that lane is enabled and not otherwise.
    "https://careers.garmin.com/job/1",
)


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A data dir holding the seeds above, with the config dir pinned alongside it."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(data_dir))
    engine = get_engine(data_dir)
    ensure_schema(engine)
    run = insert_run(engine)
    with engine.begin() as conn:
        record_seeds(conn, _URLS, discovered_by="indeed", run_id=run, now=NOW)
    engine.dispose()
    return data_dir


def _enable(data_dir: Path, lanes: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "config.toml").write_text(f"lanes_enabled = [{lanes}]\n")


def _cli(data_dir: Path, args: list[str]):
    return CliRunner().invoke(app, ["--data-dir", str(data_dir), "seeds", *args])


def test_the_total_and_the_breakdown_are_read_in_ONE_statement(store: Path) -> None:
    """Two reads is two SNAPSHOTS on SQLite, and the report publishes their difference.

    pysqlite does not begin a transaction for a `SELECT`, so a count-then-group implementation
    sees the database as of each execution even inside `conn.begin()`. A concurrent run inserting
    seeds between them makes the breakdown larger than the total, and `claimed = unresolved -
    unclaimed` then prints NEGATIVE with a share above 100% — reproduced at `unresolved: 9,
    unclaimed: 12, claimable -3 (133.3%)` while this was two statements.

    Wrapping it in a transaction did not fix that; making it one statement did. So the property
    worth pinning is the statement COUNT — asserting only `claimed == unresolved - unclaimed` on a
    quiet store passes against the broken version and defends nothing.
    """
    from sqlalchemy import event

    from boardwatch.store.seed_queries import ResolverCatalog, read_seed_claims

    engine = get_engine(store)
    seen: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if "lane_seeds" in statement:
            seen.append(statement)

    with engine.connect() as conn:
        reading = read_seed_claims(
            conn,
            catalogs=(
                ResolverCatalog(
                    hosts=frozenset({"careers.garmin.com"}),
                    host_suffixes=frozenset(),
                    max_attempts=3,
                ),
            ),
        )
    engine.dispose()

    assert len(seen) == 1, (
        f"the reading must touch lane_seeds exactly once; {len(seen)} statements means the total "
        f"and the breakdown can straddle a concurrent write again"
    )
    assert reading.unresolved == len(_URLS)
    assert sum(h.seeds for h in reading.unclaimed_hosts) == len(_URLS) - 1


def test_the_published_split_is_internally_consistent(store: Path) -> None:
    """`claimable` is a subtraction, so it must never print negative or exceed the queue."""
    _enable(store, '"jsonld"')
    result = _cli(store, ["--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["claimed"] == payload["unresolved"] - payload["unclaimed"]
    assert payload["claimed"] >= 0
    assert 0.0 <= payload["unclaimed_share"] <= 1.0


def test_a_registered_resolver_that_is_not_ENABLED_claims_nothing(store: Path) -> None:
    """The leak's worst case must not be reported as its healthy half.

    `lanes_enabled` is empty by default and the runner builds only the lanes it names, so with
    `jsonld` off the `careers.garmin.com` seed is drained by nobody and belongs in the unclaimed
    set — even though `jsonld` is registered and would claim it if switched on.
    """
    _enable(store, "")
    off = json.loads(_cli(store, ["--json", "--limit", "0"]).stdout)
    assert off["resolvers_enabled"] == []
    assert "jsonld" in off["resolvers_registered"]
    assert off["claimed"] == 0
    assert off["unclaimed"] == len(_URLS)
    assert "careers.garmin.com" in {h["host"] for h in off["unclaimed_hosts"]}

    _enable(store, '"jsonld"')
    on = json.loads(_cli(store, ["--json", "--limit", "0"]).stdout)
    assert on["resolvers_enabled"] == ["jsonld"]
    assert on["claimed"] == 1
    assert "careers.garmin.com" not in {h["host"] for h in on["unclaimed_hosts"]}


def test_limit_bounds_the_json_payload_too_and_still_reports_the_full_total(store: Path) -> None:
    """`--json` honouring `--limit` matters more than the table: a script cannot see truncation."""
    _enable(store, '"jsonld"')
    payload = json.loads(_cli(store, ["--json", "--limit", "1"]).stdout)
    assert len(payload["unclaimed_hosts"]) == 1
    assert payload["hosts_total"] == 3, "the full host count survives truncation"
    assert payload["unclaimed_hosts"][0]["host"] == "grnh.se", "largest first"
    assert payload["unclaimed_hosts"][0]["seeds"] == 5


def test_a_negative_limit_is_refused_before_anything_is_read_or_printed(store: Path) -> None:
    """Below the `--json` return it never runs; below the summary a script sees plausible stdout."""
    _enable(store, '"jsonld"')
    for args in (["--limit", "-3"], ["--limit", "-3", "--json"]):
        result = _cli(store, args)
        assert result.exit_code == 1, args
        assert "--limit must be non-negative" in result.output
        assert "unresolved seeds" not in result.output
        assert "{" not in result.output


def test_an_absent_schema_reports_and_stops_rather_than_tracebacking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "empty"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(data_dir))
    result = _cli(data_dir, [])
    assert result.exit_code == 1
    assert "schema: ABSENT" in result.output


def test_an_empty_queue_reports_no_share_rather_than_zero_percent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A share of nothing is not zero percent, and 0.0% would read as a healthy drain."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(data_dir))
    engine = get_engine(data_dir)
    ensure_schema(engine)
    engine.dispose()
    payload = json.loads(_cli(data_dir, ["--json"]).stdout)
    assert payload["unresolved"] == 0
    assert payload["unclaimed_share"] is None
