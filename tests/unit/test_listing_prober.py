"""The PRODUCTION listing probe, driven through the real `Fetcher` (T89).

`tests/unit/test_death_probe.py` injects a fake listing prober, which is right for the sweep's
seam and blind to the two things most likely to break here.

The first is the same silent-None class `test_liveness_prober.py` exists for: `Fetcher._send_once`
raises `FetchFailure` for every non-200, so a 500 or a dead board arrives as an exception rather
than a return value. If that path ever stopped producing `ids is None`, every row on every
answering board would read as ABSENT and this mechanism would close the fleet.

The second is the URL itself. Membership is the only thing asked for, so these are deliberately
NOT each provider's `board_url`: those carry `?includeCompensation=true` (ashby) and
`?content=true&pay_transparency=true` (greenhouse), which fetch every JD body on the board —
ashby payloads reach 1.7 MB (D26). A copy-paste of `board_url` into the catalog would work, pass
every behavioural test, and multiply the sweep's bandwidth by the size of a JD corpus.

respx + a real `Fetcher` is the repo's standard network seam (see `tests/contract/`).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from boardwatch.core.settings import Settings
from boardwatch.pipeline.death_probe import (
    LISTING_ENDPOINTS,
    UnlistableProvider,
    build_listing_prober,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, config_dir=tmp_path, per_host_delay_seconds=0.25)


@respx.mock
def test_ashby_membership_is_read_without_pulling_every_jd_body(tmp_path: Path) -> None:
    url = "https://api.ashbyhq.com/posting-api/job-board/acme"
    route = respx.get(url).mock(return_value=httpx.Response(200, json={"jobs": [{"id": "a-1"}]}))

    result = build_listing_prober(_settings(tmp_path))(7, "ashby", "acme")

    assert result.ids == frozenset({"a-1"})
    assert route.called
    # The compensation flag the board scan sends is deliberately absent: it is what makes a
    # Ramp-scale payload 1.7 MB, and a membership test needs none of it.
    assert "includeCompensation" not in str(route.calls[0].request.url)


@respx.mock
def test_greenhouse_membership_is_read_without_the_content_flag(tmp_path: Path) -> None:
    url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
    # Greenhouse ids are JSON numbers; `provider_posting_id` holds what `parse_job` wrote, which
    # is `str(job["id"])`. A membership test comparing an int would miss every row.
    route = respx.get(url).mock(return_value=httpx.Response(200, json={"jobs": [{"id": 4242}]}))

    result = build_listing_prober(_settings(tmp_path))(7, "greenhouse", "acme")

    assert result.ids == frozenset({"4242"})
    assert route.called
    assert "content=true" not in str(route.calls[0].request.url)


@respx.mock
def test_lever_publishes_a_bare_array_and_is_read_as_one(tmp_path: Path) -> None:
    """The one shape difference in the catalog: no `jobs` key, the payload IS the list."""
    url = "https://api.lever.co/v0/postings/acme"
    route = respx.get(url).mock(return_value=httpx.Response(200, json=[{"id": "l-1"}]))

    assert build_listing_prober(_settings(tmp_path))(7, "lever", "acme").ids == frozenset(
        {"l-1"}
    )
    assert route.called
    assert route.calls[0].request.url.params["mode"] == "json"


@respx.mock
def test_a_500_from_the_real_fetcher_is_UNKNOWN_not_an_empty_board(  # noqa: N802
    tmp_path: Path,
) -> None:
    """The path production actually takes, and the one that decides the fail-safe direction: a
    non-200 never reaches `parse_listing` because the `Fetcher` raises first. If that arrived as
    `frozenset()` instead of `None`, every open row on the board would read as absent and two
    bad hours at a provider would retire its whole fleet."""
    respx.get("https://api.ashbyhq.com/posting-api/job-board/acme").mock(
        return_value=httpx.Response(500)
    )

    result = build_listing_prober(_settings(tmp_path))(7, "ashby", "acme")

    assert result.ids is None
    assert result.company_id == 7


@respx.mock
def test_a_dead_board_is_UNKNOWN_rather_than_evidence_about_its_postings(  # noqa: N802
    tmp_path: Path,
) -> None:
    """Deliberately conservative, and measured: 1 of the 30 unwatched ashby companies sampled
    live 2026-09-17 answered 404 for its whole board. A 404 from a LIST endpoint is evidence
    about the board, not about each requisition on it, and reading it the other way would retire
    an entire employer on one answer — the same argument narrowing 1 makes for a redirected
    gone-status on the URL path."""
    respx.get("https://api.ashbyhq.com/posting-api/job-board/gone").mock(
        return_value=httpx.Response(404)
    )

    assert build_listing_prober(_settings(tmp_path))(7, "ashby", "gone").ids is None


@respx.mock
def test_a_transport_fault_is_UNKNOWN_rather_than_raising(tmp_path: Path) -> None:  # noqa: N802
    """A sweep that raises loses the rest of the class. `runner.py` catches it and reports the
    whole sweep as unmeasured, so one unreachable host would cost every other company its turn."""
    respx.get("https://api.lever.co/v0/postings/acme").mock(
        side_effect=httpx.ConnectError("no route to host")
    )

    assert build_listing_prober(_settings(tmp_path))(7, "lever", "acme").ids is None


@respx.mock
def test_an_unparseable_body_from_the_real_fetcher_is_UNKNOWN(tmp_path: Path) -> None:  # noqa: N802
    """A bot-check or an error page served with a 200 — the shape that would otherwise sail past
    the exception path and be read as a board listing nothing."""
    respx.get("https://api.ashbyhq.com/posting-api/job-board/acme").mock(
        return_value=httpx.Response(200, text="<html>are you a robot?</html>")
    )

    assert build_listing_prober(_settings(tmp_path))(7, "ashby", "acme").ids is None


@respx.mock
def test_a_slug_is_percent_encoded_into_the_endpoint(tmp_path: Path) -> None:
    """The slug arrives from the store, where a lane wrote it. A slash in it would otherwise
    address a DIFFERENT board's listing, and every row of the real company would read absent.

    Asserted on `raw_path`, not on the route matching: respx normalises `%2F` back to `/` when
    it matches a pattern, so a route assertion passes either way — the mutation of dropping
    `quote()` survived a version of this test that only checked `route.called`.
    """
    route = respx.get(url__regex=r".*job-board.*").mock(
        return_value=httpx.Response(200, json={"jobs": []})
    )

    build_listing_prober(_settings(tmp_path))(7, "ashby", "acme/other")

    assert route.calls[0].request.url.raw_path == (
        b"/posting-api/job-board/acme%2Fother"
    )


@respx.mock
def test_a_client_fault_that_is_not_a_FetchFailure_is_UNKNOWN(tmp_path: Path) -> None:  # noqa: N802
    """The broad `except Exception` earns its keep here rather than being decoration. `Fetcher`
    wraps transport faults in `FetchFailure`, but anything it does NOT wrap — a client bug, a
    library change, a bad URL built from a strange slug — would otherwise escape into
    `runner.py`'s sweep handler and cost every remaining company its turn this run."""
    respx.get("https://api.ashbyhq.com/posting-api/job-board/acme").mock(
        side_effect=RuntimeError("something nobody anticipated")
    )

    result = build_listing_prober(_settings(tmp_path))(7, "ashby", "acme")

    assert result.ids is None
    assert "RuntimeError" in result.detail


def test_an_out_of_catalog_provider_is_a_failure_not_a_new_bucket(tmp_path: Path) -> None:
    """CLAUDE.md: out-of-catalog is a failure, never a new bucket. Raised at the lookup as a
    TYPED error naming the provider, rather than as a `KeyError` whose message a caller would
    have to parse. Reachable only from a catalog/query disagreement — the sweep asks about a
    company only when its provider is IN `LISTING_ENDPOINTS` — which is exactly why it must be
    loud rather than silently `unknown`."""
    with pytest.raises(UnlistableProvider) as caught:
        build_listing_prober(_settings(tmp_path))(1, "workday", "acme")

    assert caught.value.provider == "workday"
    assert "workday" in str(caught.value)


def test_the_catalog_names_only_hosts_the_registry_already_knows() -> None:
    """Every listing endpoint belongs to a provider this repo already fetches boards from. A
    catalog entry for a provider the registry does not know would mean rows leaving the URL path
    for an API nothing else in the codebase has ever spoken to."""
    from boardwatch.providers.registry import PROVIDER_NAMES

    assert set(LISTING_ENDPOINTS) <= set(PROVIDER_NAMES)
    for provider, (template, root) in LISTING_ENDPOINTS.items():
        assert template.startswith("https://"), provider
        assert root in (None, "jobs"), provider
        json.dumps({"probe": template})  # a template must be a plain, loggable string
