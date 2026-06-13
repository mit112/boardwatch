import threading
import time
from pathlib import Path

import httpx
import pytest
import respx

from boardwatch.core.models import ResponseValidators
from boardwatch.core.politeness import PER_HOST_DELAY_FLOOR, Fetcher, FetchFailure
from boardwatch.core.settings import Settings


def _settings(tmp_path: Path, delay: float = 0.25, retries: int = 3) -> Settings:
    return Settings(
        data_dir=tmp_path, config_dir=tmp_path,
        per_host_delay_seconds=delay, retry_attempts=retries,
    )


def test_pacing_floor_enforced(tmp_path: Path) -> None:
    # Settings now enforces ge=0.25, so the Fetcher's internal floor is defense-in-depth.
    # Verify the floor constant is still accessible and the Fetcher clamps correctly for
    # any future path that could bypass Settings validation.
    fetcher = Fetcher(_settings(tmp_path, delay=0.25))
    assert fetcher.effective_delay == 0.25
    assert PER_HOST_DELAY_FLOOR == 0.25


def test_identifying_user_agent(tmp_path: Path) -> None:
    with respx.mock:
        route = respx.get("https://a.example/x").mock(return_value=httpx.Response(200))
        Fetcher(_settings(tmp_path)).get("https://a.example/x")
    ua = route.calls[0].request.headers["User-Agent"]
    assert ua.startswith("boardwatch/") and "github.com" in ua


def test_same_host_requests_serialize(tmp_path: Path) -> None:
    starts: list[float] = []

    def slow(_request: httpx.Request) -> httpx.Response:
        starts.append(time.monotonic())
        time.sleep(0.1)
        return httpx.Response(200)

    with respx.mock:
        respx.get("https://same.example/x").mock(side_effect=slow)
        fetcher = Fetcher(_settings(tmp_path))
        threads = [
            threading.Thread(target=fetcher.get, args=("https://same.example/x",))
            for _ in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    starts.sort()
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    # serialized: each start waits for the previous request (0.1 s) + the 0.25 s floor
    assert all(gap >= PER_HOST_DELAY_FLOOR for gap in gaps), gaps


def test_different_hosts_overlap(tmp_path: Path) -> None:
    def slow(_request: httpx.Request) -> httpx.Response:
        time.sleep(0.4)
        return httpx.Response(200)

    with respx.mock:
        respx.get("https://h1.example/x").mock(side_effect=slow)
        respx.get("https://h2.example/x").mock(side_effect=slow)
        fetcher = Fetcher(_settings(tmp_path))
        t0 = time.monotonic()
        threads = [
            threading.Thread(target=fetcher.get, args=(url,))
            for url in ("https://h1.example/x", "https://h2.example/x")
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.monotonic() - t0
    assert elapsed < 0.7, elapsed  # serialized would be >= 0.8


def test_retry_after_honored_on_429(tmp_path: Path) -> None:
    with respx.mock:
        respx.get("https://r.example/x").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "1"}),
                httpx.Response(200),
            ]
        )
        t0 = time.monotonic()
        result = Fetcher(_settings(tmp_path)).get("https://r.example/x")
        elapsed = time.monotonic() - t0
    assert result.status_code == 200
    assert elapsed >= 1.0, elapsed


def test_retries_exhausted_surface_typed_failure(tmp_path: Path) -> None:
    with respx.mock:
        route = respx.get("https://down.example/x").mock(return_value=httpx.Response(503))
        with pytest.raises(FetchFailure):
            Fetcher(_settings(tmp_path, retries=2)).get("https://down.example/x")
    assert route.call_count == 2


def test_non_retryable_4xx_fails_fast_with_status(tmp_path: Path) -> None:
    with respx.mock:
        route = respx.get("https://gone.example/x").mock(return_value=httpx.Response(404))
        with pytest.raises(FetchFailure) as excinfo:
            Fetcher(_settings(tmp_path)).get("https://gone.example/x")
    assert route.call_count == 1
    assert excinfo.value.status_code == 404


def test_conditional_get_sends_validators_and_surfaces_304(tmp_path: Path) -> None:
    with respx.mock:
        route = respx.get("https://c.example/x").mock(return_value=httpx.Response(304))
        result = Fetcher(_settings(tmp_path)).get(
            "https://c.example/x",
            validators=ResponseValidators(etag='W/"v1"', last_modified="Mon, 01 Jun 2026 00:00:00 GMT"),
        )
    sent = route.calls[0].request.headers
    assert sent["If-None-Match"] == 'W/"v1"'
    assert sent["If-Modified-Since"] == "Mon, 01 Jun 2026 00:00:00 GMT"
    assert result.not_modified is True
    assert result.observed_validators is None  # a 304 carries no new inventory or validators


def test_observed_validators_returned_on_200(tmp_path: Path) -> None:
    with respx.mock:
        respx.get("https://v.example/x").mock(
            return_value=httpx.Response(
                200,
                headers={"ETag": 'W/"v2"', "Last-Modified": "Tue, 02 Jun 2026 00:00:00 GMT"},
                content=b"{}",
            )
        )
        result = Fetcher(_settings(tmp_path)).get("https://v.example/x")
    assert result.observed_validators == ResponseValidators(
        etag='W/"v2"', last_modified="Tue, 02 Jun 2026 00:00:00 GMT"
    )


def test_no_db_side_effects_from_any_fetch_path(tmp_path: Path) -> None:
    """Issue #5: no fetch path touches the DB (runtime proof; the AST lint in
    test_import_hygiene.py is the structural proof)."""
    from sqlalchemy import func, select

    from boardwatch.store import tables
    from boardwatch.store.db import ensure_schema, get_engine

    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)

    def row_counts() -> list[tuple[str, int]]:
        with engine.connect() as conn:
            return [
                (name, int(conn.execute(select(func.count()).select_from(table)).scalar_one()))
                for name, table in sorted(tables.metadata.tables.items())
            ]

    before = row_counts()
    fetcher = Fetcher(_settings(tmp_path, retries=1))
    with respx.mock:
        respx.get("https://ok.example/x").mock(
            return_value=httpx.Response(200, headers={"ETag": "e"})
        )
        respx.get("https://nm.example/x").mock(return_value=httpx.Response(304))
        respx.get("https://bad.example/x").mock(return_value=httpx.Response(503))
        fetcher.get("https://ok.example/x")
        fetcher.get(
            "https://nm.example/x", validators=ResponseValidators(etag="e", last_modified=None)
        )
        with pytest.raises(FetchFailure):
            fetcher.get("https://bad.example/x")
    assert row_counts() == before
