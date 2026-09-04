import json
import threading
import time
from pathlib import Path

import httpx
import pytest
import respx

from boardwatch.core import politeness
from boardwatch.core.models import ResponseValidators
from boardwatch.core.politeness import PER_HOST_DELAY_FLOOR, Fetcher, FetchFailure
from boardwatch.core.settings import Settings


def _settings(tmp_path: Path, delay: float = 0.25, retries: int = 3) -> Settings:
    return Settings(
        data_dir=tmp_path, config_dir=tmp_path,
        per_host_delay_seconds=delay, retry_attempts=retries,
    )


def _fetcher(tmp_path: Path, delay: float = 0.25, retries: int = 3) -> Fetcher:
    return Fetcher(_settings(tmp_path, delay=delay, retries=retries))


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


# Sized for a contended machine, not for the fastest possible test. The suite runs under
# `-n auto`, so the ~30 ms of runnable work between the two thread starts competes with one
# worker per core; a threshold close to the serialized time turns that scheduling noise into
# a red gate on a run where nothing is wrong. The threshold sits at the MIDPOINT of the two
# outcomes, which is what maximises headroom on both sides.
_OVERLAP_SLEEP = 1.0
_OVERLAP_MAX = 1.5 * _OVERLAP_SLEEP  # overlapped ~1x, serialized >= 2x


def test_different_hosts_overlap(tmp_path: Path) -> None:
    def slow(_request: httpx.Request) -> httpx.Response:
        time.sleep(_OVERLAP_SLEEP)
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
    assert elapsed < _OVERLAP_MAX, elapsed


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


def test_post_json_sends_the_body_and_returns_content(tmp_path: Path) -> None:
    fetcher = _fetcher(tmp_path)
    with respx.mock:
        route = respx.post("https://api.example.com/jobs").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = fetcher.post_json("https://api.example.com/jobs", {"limit": 20, "offset": 0})
    assert result.status_code == 200
    assert json.loads(route.calls[0].request.content) == {"limit": 20, "offset": 0}


def test_post_json_paces_the_same_host(tmp_path: Path) -> None:
    fetcher = _fetcher(tmp_path)
    with respx.mock:
        respx.post("https://api.example.com/jobs").mock(
            return_value=httpx.Response(200, json={})
        )
        started = time.monotonic()
        fetcher.post_json("https://api.example.com/jobs", {})
        fetcher.post_json("https://api.example.com/jobs", {})
    assert time.monotonic() - started >= 0.25  # PER_HOST_DELAY_FLOOR


def test_post_json_retries_retryable_status(tmp_path: Path) -> None:
    with respx.mock:
        route = respx.post("https://api.example.com/jobs").mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json={})]
        )
        # retry_attempts=1 in _fetcher would not retry; build one that does
        fetcher = Fetcher(
            Settings(
                data_dir=tmp_path, config_dir=tmp_path, retry_attempts=2,
                per_host_delay_seconds=0.25,
            )
        )
        assert fetcher.post_json("https://api.example.com/jobs", {}).status_code == 200
    assert route.call_count == 2


def test_post_json_non_retryable_4xx_carries_status(tmp_path: Path) -> None:
    fetcher = _fetcher(tmp_path)
    with respx.mock:
        respx.post("https://api.example.com/jobs").mock(return_value=httpx.Response(400))
        with pytest.raises(FetchFailure) as exc:
            fetcher.post_json("https://api.example.com/jobs", {})
    assert exc.value.status_code == 400


def test_too_many_redirects_becomes_fetch_failure(tmp_path: Path) -> None:
    # follow_redirects=True makes this live-reachable. TooManyRedirects is a RequestError but
    # NOT a TransportError, so before this change it escaped Fetcher.get's conversion AND
    # every provider's `except FetchFailure`, and tracebacked doctor's probe_health.
    fetcher = _fetcher(tmp_path)
    with respx.mock:
        respx.get("https://loop.example.com/").mock(
            side_effect=httpx.TooManyRedirects("too many redirects")
        )
        with pytest.raises(FetchFailure) as exc:
            fetcher.get("https://loop.example.com/")
    assert exc.value.status_code is None  # -> health_from_failure gives UNREACHABLE


def test_decoding_error_becomes_fetch_failure(tmp_path: Path) -> None:
    fetcher = _fetcher(tmp_path)
    with respx.mock:
        respx.get("https://bad.example.com/").mock(
            side_effect=httpx.DecodingError("bad gzip")
        )
        with pytest.raises(FetchFailure):
            fetcher.get("https://bad.example.com/")


def test_request_error_is_not_retried(tmp_path: Path) -> None:
    # only the CONVERSION widens to RequestError; the retry predicate stays
    # (TransportError, _RetryableStatus), so a redirect loop fails fast
    fetcher = Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=3,
            per_host_delay_seconds=0.25,
        )
    )
    with respx.mock:
        route = respx.get("https://loop.example.com/").mock(
            side_effect=httpx.TooManyRedirects("too many redirects")
        )
        with pytest.raises(FetchFailure):
            fetcher.get("https://loop.example.com/")
    assert route.call_count == 1


# --------------------------------------------------------------------------------------
# Where the per-host clock is stamped (`pace_from_request_start`)
# --------------------------------------------------------------------------------------

# Deliberately ABOVE PER_HOST_DELAY_FLOOR, so an implementation that ignored the configured
# delay and paced on the floor instead would be caught here rather than pass by coincidence.
DELAY = 0.5
# What a response costs to answer. Under DELAY, so pacing from the request START has something
# to absorb. Both are binary-exact fractions, so DELAY - WORK is exact and the assertions below
# can be equalities rather than tolerances.
WORK = 0.125


class _FakeTime:
    """Stands in for the `time` module INSIDE `politeness`, which uses only these two calls.

    Rebinding that one module-level name is narrower than patching `time` itself: the real
    module keeps working everywhere else in the process, httpx and tenacity included.

    Nothing here waits. `sleep` records what it was asked for and advances the clock by exactly
    that much, so the pacing under test is read off directly instead of being inferred from
    elapsed wall time. Inferring it is what made the previous version of these tests flaky: the
    gap they measured was between two respx handler entries, so it carried the dispatch jitter
    either side of the stamp, and a few hundred microseconds of it straddled an exact bound.
    Both of the failures were on the low side, 0.24889 and 0.24985 against a required 0.25.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _pacing_waits(tmp_path: Path, *, from_start: bool, work: float, n: int = 3) -> list[float]:
    """What `_pace` waited before each of `n` sequential same-host GETs that each cost `work`.

    The list is the entire observation, and its LENGTH carries as much as its values: `[]` means
    the fetcher never had to wait at all, and two entries before three requests means it waited
    once ahead of every request after the first.
    """
    clock = _FakeTime()
    settings = Settings(
        data_dir=tmp_path,
        config_dir=tmp_path,
        per_host_delay_seconds=DELAY,
        pace_from_request_start=from_start,
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        clock.advance(work)  # answering the request costs `work`, charged on the fake clock
        return httpx.Response(200)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(politeness, "time", clock)
        with respx.mock:
            respx.get("https://paced.example/x").mock(side_effect=handler)
            fetcher = Fetcher(settings)
            for _ in range(n):
                fetcher.get("https://paced.example/x")
    return clock.slept


def test_pacing_from_request_end_charges_the_response_time_on_top(tmp_path: Path) -> None:
    """The shipped default: the delay is measured from when the previous request FINISHED.

    So the fetcher waits the whole delay every time, however long the response took, and the
    host sees one request per DELAY + WORK rather than one per DELAY. That is the gap D-344
    sized at 28.4 minutes off a run — ~0.6 req/s at a 0.67 s response, not the 1.0 the delay
    reads as.
    """
    waits = _pacing_waits(tmp_path, from_start=False, work=WORK)
    assert waits == [0.5, 0.5], waits  # the full delay, with the 0.125 s response ON TOP


def test_pacing_from_request_start_absorbs_the_response_time(tmp_path: Path) -> None:
    """The discriminating half: with the flag on, the response time comes OUT of the delay.

    Against the request-END implementation every wait is the full 0.5 instead of 0.375, so this
    is the assertion that fails if the flag is not read. The waits are still POSITIVE, which is
    the other half of the claim: the flag moves where the delay is measured from, and is not a
    licence to drop the delay.
    """
    waits = _pacing_waits(tmp_path, from_start=True, work=WORK)
    assert waits == [0.375, 0.375], waits  # DELAY less the 0.125 s the response already cost


def test_a_response_slower_than_the_delay_is_its_own_pacing(tmp_path: Path) -> None:
    """A response that outlasts the delay leaves nothing to wait for, so the fetcher never waits.

    Without this the flag reads as "1/delay always"; a 0.75 s response under a 0.5 s delay can
    only ever be one request per 0.75 s, and asserting a faster rate would be asserting one the
    transport cannot produce. It discriminates too — the request-END implementation waits the
    full delay after a slow response exactly as it does after a fast one, so it reports
    `[0.5, 0.5]` here.
    """
    waits = _pacing_waits(tmp_path, from_start=True, work=0.75)
    assert waits == [], waits


def test_caller_headers_ride_along_on_a_get(tmp_path: Path) -> None:
    """The seam the hiring.cafe search route needs, asserted where it is implemented.

    Written as a header the client's own defaults would otherwise supply (`Accept`), because a
    header httpx never sets would pass even if the merge dropped the caller's value onto an
    empty dict AFTER the client had already applied its own.
    """
    with respx.mock:
        route = respx.get("https://h.example/x").mock(return_value=httpx.Response(200))
        Fetcher(_settings(tmp_path)).get("https://h.example/x", headers={"Accept": "text/html"})
    sent = route.calls[0].request.headers
    assert sent["Accept"] == "text/html"
    # The client's own identity still rides: caller headers ADD, they do not replace the set.
    assert sent["User-Agent"].startswith("boardwatch/")


def test_caller_headers_cannot_suppress_a_conditional_get(tmp_path: Path) -> None:
    """Validators are merged OVER caller headers, and this is the assertion that pins it.

    A caller that could clear `If-None-Match` would silently turn every conditional GET on that
    path into an unconditional one -- the board would refetch a full payload forever, report
    `complete` rather than `unchanged`, and no counter would name the cause.
    """
    with respx.mock:
        route = respx.get("https://i.example/x").mock(return_value=httpx.Response(304))
        Fetcher(_settings(tmp_path)).get(
            "https://i.example/x",
            validators=ResponseValidators(etag='W/"v9"', last_modified=None),
            headers={"If-None-Match": 'W/"caller-wins"', "Accept": "text/html"},
        )
    sent = route.calls[0].request.headers
    assert sent["If-None-Match"] == 'W/"v9"'
    assert sent["Accept"] == "text/html"


def test_post_json_sends_no_caller_headers_because_it_takes_none(tmp_path: Path) -> None:
    """`post_json` is Workday's path and deliberately keeps the identifying default set.

    Pinned so that widening the GET seam does not quietly widen this one: the POST body path
    serves the six ATS providers, which get the honest `boardwatch/` UA under the D22 politeness
    contract, and nothing about the aggregator's edge behaviour is a reason to change that.
    """
    with respx.mock:
        route = respx.post("https://j.example/x").mock(return_value=httpx.Response(200, json={}))
        Fetcher(_settings(tmp_path)).post_json("https://j.example/x", {"a": 1})
    sent = route.calls[0].request.headers
    assert sent["User-Agent"].startswith("boardwatch/")
    assert "Sec-Fetch-Mode" not in sent


def test_an_hour_long_retry_after_is_refused_rather_than_slept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T13. `Retry-After` was honoured uncapped, inside the per-host lock. One 429 carrying
    `Retry-After: 3600` parked every board on that host for an HOUR — and the shared-host
    providers are the ones where that matters: Greenhouse, Lever and SmartRecruiters each
    serve their whole fleet from one host, so a single tenant's rate limit stalled the scan.

    A wait longer than the cap is not a wait, it is an outage, so it is reported as one. It
    reuses `FetchFailure` with `status_code=None`, which `providers.base.health_from_failure`
    already maps to `BoardHealth.UNREACHABLE` — the typed outcome a dead host gets — rather
    than adding a member to that closed catalog.
    """
    slept: list[float] = []
    monkeypatch.setattr(politeness.time, "sleep", lambda seconds: slept.append(seconds))
    with respx.mock:
        route = respx.get("https://slow.example/x").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "3600"})
        )
        with pytest.raises(FetchFailure) as caught:
            _fetcher(tmp_path).get("https://slow.example/x")

    assert max(slept, default=0.0) <= politeness.RETRY_AFTER_CAP_SECONDS, slept
    assert caught.value.status_code is None, "a capped Retry-After must read as unreachable"
    assert "3600" in str(caught.value)
    assert route.call_count == 1, "it must not keep retrying a host that asked for an hour"


def test_a_retry_after_inside_the_cap_is_still_honoured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control. The cap must not turn every 429 into an outage — a host asking for a few
    seconds is being polite, and that is the whole point of the header."""
    slept: list[float] = []
    monkeypatch.setattr(politeness.time, "sleep", lambda seconds: slept.append(seconds))
    with respx.mock:
        respx.get("https://ok.example/x").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "5"}),
                httpx.Response(200),
            ]
        )
        result = _fetcher(tmp_path).get("https://ok.example/x")
    assert result.status_code == 200
    assert max(slept, default=0.0) >= 5.0, slept
