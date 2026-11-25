"""T343: what each host cost the scan's `Fetcher`, and how the funnel reports the longest chains."""

import threading
import time
from pathlib import Path

import httpx
import pytest
import respx

from boardwatch.core.politeness import Fetcher, FetchFailure, HostPacing
from boardwatch.core.settings import Settings
from boardwatch.reports.run_funnel import (
    HOST_COST_ROWS,
    HostFetchCost,
    ScanContext,
    _host_cost_markdown,
    funnel_to_dict,
    funnel_to_markdown,
)
from tests.unit.test_run_funnel import funnel

_SLOW = 0.3


def _fetcher(tmp_path: Path, retries: int = 3) -> Fetcher:
    settings = Settings(
        data_dir=tmp_path, config_dir=tmp_path, per_host_delay_seconds=0.25, retry_attempts=retries,
    )
    return Fetcher(settings, pacing=HostPacing())  # its own pacing: no state from other tests


def test_physical_sends_match_the_transports_own_count(tmp_path: Path) -> None:
    """The acceptance count, read through a different path: the transport's calls, not the meter."""
    with respx.mock:
        a = respx.get("https://a.hostcost.example/x").mock(
            side_effect=[httpx.Response(503), httpx.Response(200), httpx.Response(200)]
        )
        b = respx.get("https://b.hostcost.example/x").mock(return_value=httpx.Response(404))
        fetcher = _fetcher(tmp_path)
        fetcher.get("https://a.hostcost.example/x")  # 503, then 200: one request, two sends
        fetcher.get("https://a.hostcost.example/x")
        with pytest.raises(FetchFailure):
            fetcher.get("https://b.hostcost.example/x")  # a failed request costs the host too
    costs = fetcher.host_costs()
    assert costs["a.hostcost.example"].requests == 2
    assert costs["a.hostcost.example"].attempts == a.call_count == 3
    assert costs["b.hostcost.example"].requests == 1
    assert costs["b.hostcost.example"].attempts == b.call_count == 1
    assert sum(c.attempts for c in costs.values()) == a.call_count + b.call_count


def test_a_thread_queued_behind_a_sibling_shows_the_wait_outside_its_service(
    tmp_path: Path,
) -> None:
    def slow(_request: httpx.Request) -> httpx.Response:
        time.sleep(_SLOW)
        return httpx.Response(200)

    with respx.mock:
        respx.get("https://q.hostcost.example/x").mock(side_effect=slow)
        fetcher = _fetcher(tmp_path)
        threads = [
            threading.Thread(target=fetcher.get, args=("https://q.hostcost.example/x",))
            for _ in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    cost = fetcher.host_costs()["q.hostcost.example"]
    assert cost.requests == 2
    # each send slept _SLOW, and nothing else counts as service
    assert 2 * _SLOW <= cost.service_seconds < 2 * _SLOW + 0.5, cost
    # the second thread waited for the first's whole hold of the lock
    assert cost.lock_wait_seconds >= _SLOW, cost
    # the second request paced after the first ended (pacing from the request's end by default)
    assert cost.pace_seconds >= 0.2, cost
    # the chain is the two holds back to back; the queue wait is not added on top of it
    held = cost.service_seconds + cost.pace_seconds
    assert held <= cost.span_seconds < held + 0.5, cost


def test_a_copy_is_returned_so_a_reader_cannot_move_the_meter(tmp_path: Path) -> None:
    with respx.mock:
        respx.get("https://c.hostcost.example/x").mock(return_value=httpx.Response(200))
        fetcher = _fetcher(tmp_path)
        fetcher.get("https://c.hostcost.example/x")
    fetcher.host_costs()["c.hostcost.example"].requests = 99
    assert fetcher.host_costs()["c.hostcost.example"].requests == 1


def _row(host: str, span: float, requests: int = 1) -> HostFetchCost:
    return HostFetchCost(
        host=host, requests=requests, attempts=requests + 1, span_seconds=span,
        service_seconds=span / 2, pace_seconds=span / 4, lock_wait_seconds=0.0,
    )


def test_markdown_names_the_longest_chain_first_and_says_how_many_were_cut() -> None:
    rows = tuple(_row(f"h{i}.example", float(i)) for i in range(HOST_COST_ROWS + 5))
    lines = _host_cost_markdown(rows)
    table = [line for line in lines if line.startswith("| `")]
    assert len(table) == HOST_COST_ROWS
    assert table[0].startswith(f"| `h{HOST_COST_ROWS + 4}.example` |")
    assert f"({HOST_COST_ROWS} of {HOST_COST_ROWS + 5} hosts)" in "\n".join(lines)
    assert "| 1 |" in table[0]  # retries = attempts - requests


def test_markdown_tells_not_measured_from_measured_and_empty() -> None:
    assert "not measured" in "\n".join(_host_cost_markdown(None))
    assert "no request was sent" in "\n".join(_host_cost_markdown(()))


def test_the_funnel_carries_the_cut_and_the_host_count() -> None:
    rows = tuple(_row(f"h{i}.example", float(i)) for i in range(HOST_COST_ROWS + 2))
    measured = funnel(scan=ScanContext(ran=True, boards_attempted=1, host_cost=rows))
    block = funnel_to_dict(measured)["scan"]["host_cost"]  # type: ignore[index]
    assert block["hosts"] == HOST_COST_ROWS + 2
    assert [r["host"] for r in block["rows"]][:2] == [
        f"h{HOST_COST_ROWS + 1}.example", f"h{HOST_COST_ROWS}.example",
    ]
    assert len(block["rows"]) == HOST_COST_ROWS
    assert "**Longest host chains**" in funnel_to_markdown(measured)
    unmeasured = funnel(scan=ScanContext(ran=True, boards_attempted=1))
    assert funnel_to_dict(unmeasured)["scan"]["host_cost"] is None  # type: ignore[index]
