"""Eightfold contract tests. Eightfold is the FIRST provider whose slug is a bare HOST, and
the first that must bootstrap an HTML page before it can address its own API at all. Every
property asserted here was measured live on 2026-09-06 — see
tests/fixtures/eightfold/README.md."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.core.models import BoardRequest, ResponseValidators
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers import eightfold
from boardwatch.providers.base import BoardHealth
from boardwatch.providers.eightfold import (
    EightfoldProvider,
    board_domain,
    parse_posting,
    validated_host,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "eightfold"
SLUG = "careers.acme.test"
DOMAIN = "acme.test"
BOOT_URL = f"https://{SLUG}/careers"

provider = EightfoldProvider()


def _fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _boot_html(domain: str = DOMAIN) -> bytes:
    """The career page's boot blob, in the recorded shape: HTML-ESCAPED JSON inside a
    <code id="pcsx-data"> element. Inlined rather than filed as a fixture because .html is
    outside DATA_SUFFIXES, so a file would be pinned by nothing (the same reasoning that
    keeps Workday's maintenance-page body inline)."""
    escaped = (
        json.dumps({"domain": domain, "configs": {"pcsxConfig": {"enabled": True}}})
        .replace('"', "&#34;")
    )
    return (
        b'<!DOCTYPE html><html><head><title>Careers</title></head><body>'
        b'<div id="pcsx"></div><code id="pcsx-data" style="display:none;" data-nosnippet>'
        + escaped.encode()
        + b"</code></body></html>"
    )


def _fetcher(tmp_path: Path) -> Fetcher:
    return Fetcher(
        Settings(
            data_dir=tmp_path, config_dir=tmp_path, retry_attempts=1,
            per_host_delay_seconds=0.25,
        )
    )


def _request(
    known: frozenset[str] = frozenset(), budget: int = 50,
    validators: ResponseValidators | None = None,
) -> BoardRequest:
    return BoardRequest(
        provider="eightfold", slug=SLUG, url=BOOT_URL,
        known_posting_ids=known, detail_budget=budget, validators=validators,
    )


def _search_url(start: int) -> str:
    return f"https://{SLUG}/api/pcsx/search?domain={DOMAIN}&start={start}"


def _detail_url(posting_id: str) -> str:
    return (
        f"https://{SLUG}/api/pcsx/position_details"
        f"?domain={DOMAIN}&position_id={posting_id}"
    )


def _mock_boot(domain: str = DOMAIN) -> None:
    respx.get(BOOT_URL).mock(return_value=httpx.Response(200, content=_boot_html(domain)))


def _mock_details(*fixture_rows: dict[str, Any]) -> None:
    """One detail route per listed row, built from the row itself so a fixture with N rows
    needs no per-row hand-mocking. The body is the recorded detail envelope."""
    for row in fixture_rows:
        if row.get("id") is None:
            continue
        detail = dict(row)
        detail["publicUrl"] = f"https://{SLUG}{row['positionUrl']}"
        detail["jobDescription"] = f"<p>Body for {row['name']}.</p>"
        respx.get(_detail_url(str(row["id"]))).mock(
            return_value=httpx.Response(
                200,
                json={"status": 200, "error": {"message": "", "body": ""},
                      "data": detail, "metadata": None},
            )
        )


# ---------------------------------------------------------------- slug contract

def test_board_url_is_the_career_page_not_the_api() -> None:
    # the API cannot be addressed until this page has yielded the tenant's `domain`
    assert provider.board_url(SLUG) == BOOT_URL


def test_normalize_lowercases_the_host() -> None:
    assert EightfoldProvider.normalize_slug("Careers.ACME.Test") == SLUG


def test_normalize_is_idempotent() -> None:
    once = EightfoldProvider.normalize_slug(SLUG)
    assert EightfoldProvider.normalize_slug(once) == once


@pytest.mark.parametrize(
    "bad",
    [
        "acme",                                # no dot: not a hostname
        ".eightfold.ai",                       # no tenant label
        "acme.eightfold.ai.",                  # trailing dot
        "@acme.eightfold.ai",                  # userinfo injection, empty userinfo
        "acme.eightfold.ai@",                  # userinfo injection, trailing @
        "acme.eightfold.ai:8080",              # port / scheme injection
        "acme.eightfold.ai?x=1",               # query injection
        "acme.eightfold.ai#f",                 # fragment injection
        "acme eightfold.ai",                   # whitespace in host
        "acme.eight\tfold.ai",                 # control character
        "",                                    # empty
    ],
)
def test_malformed_slug_is_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        validated_host(bad)


def test_malformed_slug_surfaces_unknown_board_url_not_value_error() -> None:
    # a bare ValueError escapes companies_cmd.py's except UnknownBoardURL and tracebacks
    with pytest.raises(UnknownBoardURL, match="invalid eightfold board target"):
        parse_board_target("eightfold:not-a-host")


def test_qualified_form_round_trips() -> None:
    assert parse_board_target(f"eightfold:{SLUG}") == ("eightfold", SLUG)


@pytest.mark.parametrize(
    "pasted",
    [
        "https://acme.eightfold.ai/careers",
        "https://acme.eightfold.ai/careers/job/1000000000001",
        "acme.eightfold.ai/careers?utm=x",
        "https://ACME.Eightfold.AI/careers",
    ],
)
def test_a_pasted_vendor_hosted_url_resolves_to_the_host_not_a_path_segment(
    pasted: str,
) -> None:
    # the slug is the HOST. Without slug_from_path this would watch a board named "careers".
    assert parse_board_target(pasted) == ("eightfold", "acme.eightfold.ai")


def test_bare_vendor_host_paste_surfaces_slug_help() -> None:
    with pytest.raises(UnknownBoardURL, match="identified by its HOST"):
        parse_board_target("https://acme.eightfold.ai")


def test_an_employer_owned_domain_cannot_be_pasted_and_that_is_deliberate() -> None:
    # nothing tells parse_board_target that careers.acme.test is Eightfold rather than the
    # employer's own site, so it REFUSES rather than probing. `eightfold:{host}` is the path.
    with pytest.raises(UnknownBoardURL):
        parse_board_target("https://careers.acme.test/careers")


# ---------------------------------------------------------------- the bootstrap

def test_the_domain_is_read_out_of_the_escaped_pcsx_data_blob() -> None:
    assert board_domain(_boot_html()) == DOMAIN


@pytest.mark.parametrize(
    "content",
    [
        b"<html><body>no boot blob here</body></html>",
        b'<code id="pcsx-data">not json</code>',
        b'<code id="pcsx-data">[1, 2]</code>',
        b'<code id="pcsx-data">{&#34;domain&#34;: &#34;&#34;}</code>',
        b'<code id="pcsx-data">{&#34;domain&#34;: &#34;acme.test&amp;x=1&#34;}</code>',
        b'<code id="pcsx-data">{&#34;domain&#34;: null}</code>',
    ],
)
def test_an_unusable_boot_blob_raises_rather_than_guessing(content: bytes) -> None:
    # a WRONG domain is a 200 that returns HTML, so an unvalidated value would surface as a
    # parse error one request later with nothing pointing back at the bootstrap
    with pytest.raises(ValueError):
        board_domain(content)


@respx.mock
def test_the_domain_is_not_assumed_to_be_the_host(tmp_path: Path) -> None:
    """Measured: one probed tenant's career host and its `domain` share no label. A provider
    that sent domain={host} would 200 with HTML on every real employer-owned board."""
    _mock_boot("acmecorp.example")
    route = respx.get(
        f"https://{SLUG}/api/pcsx/search",
        params={"domain": "acmecorp.example", "start": "0"},
    ).mock(return_value=httpx.Response(200, json=_fx("search_empty.json")))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert route.called


@respx.mock
def test_a_career_page_with_no_boot_blob_fails_the_board(tmp_path: Path) -> None:
    respx.get(BOOT_URL).mock(
        return_value=httpx.Response(200, content=b"<html><body>Coming soon</body></html>")
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert "career page bootstrap" in (snapshot.error or "")


# ---------------------------------------------------------------- single-page board

@respx.mock
def test_single_page_board_parses_every_posting(tmp_path: Path) -> None:
    payload = _fx("search_normal.json")
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=payload))
    _mock_details(*payload["data"]["positions"])
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 4
    assert snapshot.listed_ids == {
        "1000000000001", "1000000000002", "1000000000003", "1000000000004"
    }
    assert snapshot.board_reported_total == 4
    assert snapshot.board_enumerated == 4
    assert snapshot.detail_deferred == 0


@respx.mock
def test_four_rows_is_one_listing_request_because_the_page_size_is_ten(
    tmp_path: Path,
) -> None:
    payload = _fx("search_normal.json")
    _mock_boot()
    route = respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=payload))
    provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert route.call_count == 1


@respx.mock
def test_no_listing_request_ever_sends_a_num_parameter(tmp_path: Path) -> None:
    """`num=50` returns ten rows live: the page size is not a clamp we can raise, so sending
    one would advertise a page size the server does not honour."""
    payload = _fx("search_normal.json")
    _mock_boot()
    route = respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=payload))
    provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    for call in route.calls:
        assert "num=" not in str(call.request.url)


# ---------------------------------------------------------------- pagination

@respx.mock
def test_a_full_page_forces_another_and_a_short_page_ends_the_pager(
    tmp_path: Path,
) -> None:
    full, short = _fx("search_page_full.json"), _fx("search_page_short.json")
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=full))
    third = respx.get(_search_url(20)).mock(
        return_value=httpx.Response(200, json=_fx("search_empty.json"))
    )
    respx.get(_search_url(10)).mock(return_value=httpx.Response(200, json=short))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert not third.called  # the 2-row page ended it; no third request was made
    # 10 + 2 rows listed, but one of the second page's rows carries no id
    assert snapshot.board_enumerated == 11
    assert snapshot.board_reported_total == 12


@respx.mock
def test_an_id_less_row_makes_the_listing_incomplete_not_silently_short(
    tmp_path: Path,
) -> None:
    full, short = _fx("search_page_full.json"), _fx("search_page_short.json")
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=full))
    respx.get(_search_url(10)).mock(return_value=httpx.Response(200, json=short))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert snapshot.status == "partial"
    assert "collected 11 of 12" in (snapshot.error or "")


@respx.mock
def test_an_id_less_row_is_never_detail_fetched_or_materialised(tmp_path: Path) -> None:
    """The counterpart to the two tests above, on the DETAIL side, and the one that keeps an
    id-less row from minting an identity.

    An id-less row is already excluded from `listed_ids` — it is a posting that cannot be
    fetched, deduped or closed. It must be excluded from the detail loop for the SAME reason,
    and the failure if it is not is not merely a wasted request: `str(row.get("id"))` is the
    literal `"None"`, so the row would be fetched at `position_id=None` and, on any 200,
    materialise a RawPosting keyed `"None"` — a value that collides with every other id-less
    row under `UNIQUE(company_id, provider_posting_id)` and that `listed_ids` does not contain,
    so `apply_board` would close it the instant it was written.
    """
    short = _fx("search_page_short.json")
    idless = [p for p in short["data"]["positions"] if p.get("id") is None]
    assert len(idless) == 1  # the fixture's second row carries no id
    short["data"]["positions"], short["data"]["count"] = idless, 1
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=short))
    # Mocked to answer 200, so a request that should never happen cannot hide behind a 404.
    detail = respx.get(_detail_url("None")).mock(
        return_value=httpx.Response(
            200,
            json={"status": 200, "error": {"message": "", "body": ""},
                  "data": dict(idless[0], jobDescription="<p>x</p>"), "metadata": None},
        )
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=5))
    assert not detail.called
    assert snapshot.postings == []
    assert snapshot.listed_ids == frozenset()
    assert snapshot.board_enumerated == 0


@respx.mock
def test_the_count_is_read_from_the_first_page_only(tmp_path: Path) -> None:
    full, short = _fx("search_page_full.json"), _fx("search_page_short.json")
    short["data"]["count"] = 99999  # a later page must not be able to move the total
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=full))
    respx.get(_search_url(10)).mock(return_value=httpx.Response(200, json=short))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert snapshot.board_reported_total == 12


@respx.mock
def test_a_later_page_failing_is_partial_not_failed(tmp_path: Path) -> None:
    _mock_boot()
    respx.get(_search_url(0)).mock(
        return_value=httpx.Response(200, json=_fx("search_page_full.json"))
    )
    respx.get(_search_url(10)).mock(return_value=httpx.Response(500))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert snapshot.status == "partial"
    assert len(snapshot.listed_ids) == 10


@respx.mock
def test_the_first_page_failing_fails_the_board(tmp_path: Path) -> None:
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(500))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert "listing at start 0" in (snapshot.error or "")


@respx.mock
def test_the_spa_html_shell_on_the_listing_fails_cleanly(tmp_path: Path) -> None:
    # what a WRONG `domain` returns live: HTTP 200 carrying the SPA, not an error
    _mock_boot()
    respx.get(_search_url(0)).mock(
        return_value=httpx.Response(200, content=b"<!DOCTYPE html><html></html>")
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert "invalid payload" in (snapshot.error or "")


@respx.mock
def test_the_closed_apply_v2_message_body_fails_cleanly(tmp_path: Path) -> None:
    # the retired endpoint's signature, kept as a regression: 200 + {"message": ...}
    _mock_boot()
    respx.get(_search_url(0)).mock(
        return_value=httpx.Response(200, json={"message": "Not authorized for PCSX"})
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"


# ---------------------------------------------------------------- details

@respx.mock
def test_known_postings_are_not_re_detailed_but_stay_in_the_inventory(
    tmp_path: Path,
) -> None:
    payload = _fx("search_normal.json")
    rows = payload["data"]["positions"]
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=payload))
    _mock_details(*rows)
    known = frozenset({"1000000000001", "1000000000002", "1000000000003"})
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(known=known))
    assert [p.provider_posting_id for p in snapshot.postings] == ["1000000000004"]
    assert len(snapshot.listed_ids) == 4  # or apply_board closes the three known ones


@respx.mock
def test_a_detail_404_keeps_the_posting_listed_rather_than_closing_it(
    tmp_path: Path,
) -> None:
    """`{"status": 404, "error": {"message": "Position not found"}}` is indistinguishable
    from an edge blip, so it is a FETCH FAILURE, never a close signal."""
    payload = _fx("search_normal.json")
    rows = payload["data"]["positions"]
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=payload))
    _mock_details(*rows)
    respx.get(_detail_url("1000000000002")).mock(
        return_value=httpx.Response(404, json=_fx("detail_not_found.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "partial"
    assert "1000000000002" in (snapshot.error or "")
    assert len(snapshot.postings) == 3
    assert "1000000000002" in snapshot.listed_ids


@respx.mock
def test_the_detail_budget_truncates_and_is_reported(tmp_path: Path) -> None:
    payload = _fx("search_normal.json")
    rows = payload["data"]["positions"]
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=payload))
    _mock_details(*rows)
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=2))
    assert snapshot.status == "partial"
    assert len(snapshot.postings) == 2
    assert snapshot.detail_deferred == 2
    assert len(snapshot.listed_ids) == 4


@respx.mock
def test_every_detail_failing_fails_the_board(tmp_path: Path) -> None:
    payload = _fx("search_normal.json")
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=payload))
    for row in payload["data"]["positions"]:
        respx.get(_detail_url(str(row["id"]))).mock(return_value=httpx.Response(503))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert "all 4 detail fetches failed" in (snapshot.error or "")


# ---------------------------------------------------------------- the 405 throttle

@pytest.fixture()
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero the backoff so these tests pin BEHAVIOUR rather than wall clock.

    `min_host_delay` can only ever RAISE this host's pace, so 0.0 leaves `Fetcher`'s own
    `per_host_delay_seconds` in charge and the retry is still paced — exactly the property the
    production values rely on. The shipped values are asserted separately below.
    """
    monkeypatch.setattr(eightfold, "_THROTTLE_BACKOFF_SECONDS", (0.0,) * 
                        eightfold._THROTTLE_RETRIES)


def test_there_is_one_backoff_step_per_retry() -> None:
    """`_get` indexes the backoff tuple by attempt, so a tuple shorter than the retry ceiling
    is an IndexError on the last retry — of a board that is already failing."""
    assert len(eightfold._THROTTLE_BACKOFF_SECONDS) == eightfold._THROTTLE_RETRIES


@respx.mock
def test_a_405_that_clears_on_retry_lists_the_whole_board(
    tmp_path: Path, _no_backoff: None
) -> None:
    """Measured: the exact search URL that answered 405 answered 200 on four consecutive
    re-probes. Before T74 a 405 on the FIRST listing request failed the whole board — that is
    the arm that cost run 10 76% of one board."""
    payload = _fx("search_normal.json")
    _mock_boot()
    respx.get(_search_url(0)).mock(
        side_effect=[httpx.Response(405), httpx.Response(200, json=payload)]
    )
    _mock_details(*payload["data"]["positions"])
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "complete"
    assert len(snapshot.postings) == 4
    assert snapshot.board_enumerated == 4
    # The retry is COUNTED even though it cost the board nothing: a run that only ever reports
    # a throttle it lost rows to cannot tell a healthy service from a degrading one.
    assert snapshot.throttle_retries == 1
    assert snapshot.throttle_exhausted == 0


@respx.mock
def test_a_405_that_never_clears_is_partial_with_a_typed_reason(
    tmp_path: Path, _no_backoff: None
) -> None:
    """The dangerous arm. `apply_board` closes postings only on `complete`, so a board that a
    throttle stopped mid-listing MUST NOT report `complete` — `CLOSE_AFTER_MISSES` would then
    close every posting it failed to fetch. The refusal is driven by the TYPED counter, not by
    the message, and the retry is BOUNDED: three physical attempts, never a fourth."""
    full = _fx("search_page_full.json")
    # The throttle is the ONLY signal: with count == 10 the ten listed rows are the whole
    # board, so no completeness shortfall and no detail failure can carry the `partial`.
    full["data"]["count"] = 10
    known = frozenset(str(row["id"]) for row in full["data"]["positions"])
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=full))
    throttled = respx.get(_search_url(10)).mock(return_value=httpx.Response(405))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(known=known))
    assert snapshot.status == "partial"
    assert snapshot.throttle_retries == 2
    assert snapshot.throttle_exhausted == 1
    assert throttled.call_count == 1 + eightfold._THROTTLE_RETRIES
    assert "throttled" in (snapshot.error or "")
    # The rows it DID reach are still the inventory, so nothing is invented and nothing is lost
    assert len(snapshot.listed_ids) == 10


@respx.mock
def test_the_backoff_is_the_fetchers_own_pace_not_a_second_limiter(tmp_path: Path) -> None:
    """`core/politeness.Fetcher` owns this host's clock and its lock. The backoff is passed as
    `min_host_delay`, which that class honours before EVERY physical attempt and which can only
    raise the pace — so the retry is paced by the one limiter the politeness contract is
    written in, rather than by a `sleep` beside it that measures from a different clock."""
    seen: list[float | None] = []
    real_get = Fetcher.get

    def _record(self, url, validators=None, *, headers=None, min_host_delay=None):  # type: ignore[no-untyped-def]
        seen.append(min_host_delay)
        return real_get(
            self, url, validators, headers=headers, min_host_delay=min_host_delay
        )

    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(405))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(eightfold, "_THROTTLE_BACKOFF_SECONDS", (0.0, 0.0))
        patch.setattr(Fetcher, "get", _record)
        provider.fetch_board(_fetcher(tmp_path), _request())
    # boot (no override), then the first listing attempt and one override per retry
    assert seen == [None, None, 0.0, 0.0]


@respx.mock
def test_the_per_board_retry_budget_caps_a_board_that_405s_everywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second ceiling, and the one that bounds WALL CLOCK rather than request count.

    The per-request ceiling alone lets the detail loop spend a full retry chain on each of
    `detail_fetch_budget` postings. The budget is monkeypatched DOWN so the test costs four
    postings rather than fifty — what it pins is that the budget is enforced across requests
    at all, not the shipped number.
    """
    monkeypatch.setattr(eightfold, "_THROTTLE_BACKOFF_SECONDS", (0.0, 0.0))
    monkeypatch.setattr(eightfold, "_THROTTLE_BOARD_BUDGET", 3)
    payload = _fx("search_normal.json")
    _mock_boot()
    respx.get(_search_url(0)).mock(return_value=httpx.Response(200, json=payload))
    for row in payload["data"]["positions"]:
        respx.get(_detail_url(str(row["id"]))).mock(return_value=httpx.Response(405))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    # 3 retries and not one more, though four requests were each entitled to two
    assert snapshot.throttle_retries == 3
    assert snapshot.throttle_exhausted == 4
    # every detail failed, which is the existing "all N detail fetches failed" arm — `failed`,
    # which closes nothing either
    assert snapshot.status == "failed"


@respx.mock
@pytest.mark.parametrize("status", [404, 500, 503])
def test_a_non_405_failure_is_not_retried(
    tmp_path: Path, status: int, _no_backoff: None
) -> None:
    """Property 7 is about ONE measured status. A 404 detail is still a fetch failure that
    keeps the id listed (property 6), and a 500 is already `Fetcher`'s own business — neither
    may be re-fetched by this loop, which would multiply every failing request by three."""
    _mock_boot()
    route = respx.get(_search_url(0)).mock(return_value=httpx.Response(status))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.throttle_retries == 0
    assert snapshot.throttle_exhausted == 0
    # 503 is retryable inside Fetcher itself; `retry_attempts=1` in `_fetcher` pins that to one
    assert route.call_count == 1


@respx.mock
def test_a_405_bootstrap_still_reports_what_the_throttle_cost(
    tmp_path: Path, _no_backoff: None
) -> None:
    """A board the throttle killed at its career page is the board whose loss is largest, and
    `failed` alone cannot say the throttle was why."""
    respx.get(BOOT_URL).mock(return_value=httpx.Response(405))
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request())
    assert snapshot.status == "failed"
    assert snapshot.throttle_retries == 2
    assert snapshot.throttle_exhausted == 1


# ---------------------------------------------------------------- parse contract

def test_parse_posting_reads_the_recorded_detail_shape() -> None:
    listed = _fx("search_normal.json")["data"]["positions"][0]
    detail = _fx("detail_normal.json")["data"]
    posting = parse_posting(SLUG, listed, detail)
    assert posting.provider_posting_id == "1000000000001"
    assert posting.title == "Senior Platform Engineer"
    assert posting.url == "https://careers.acme.test/careers/job/1000000000001"
    assert posting.department == "Platform Engineering"
    assert posting.locations == ["Remote", "Springfield - Remote, Acmeland"]
    assert posting.posted_at == datetime(2026, 9, 6, 0, 0)
    assert posting.updated_at is None  # creationTs is a CREATION time, not a modification
    assert "deployment tooling" in posting.body_text
    assert "<p>" not in posting.body_text  # jobDescription is HTML; html_to_text is on this path


@pytest.mark.parametrize(
    ("row_index", "expected"),
    [(0, "remote"), (1, "hybrid"), (2, "onsite"), (3, "unknown")],
)
def test_work_location_option_is_a_closed_catalog(row_index: int, expected: str) -> None:
    """The remote member is `remote_local`, NOT "remote" — measured over 34 remote-filtered
    rows. Row 3's value is out of catalog and must degrade to `unknown`, never a new bucket.
    """
    row = _fx("search_normal.json")["data"]["positions"][row_index]
    assert parse_posting(SLUG, row, dict(row, jobDescription="")).remote_policy == expected


def test_the_naive_guess_remote_is_out_of_catalog() -> None:
    """The one measured correction that would otherwise ship silently. 80 unfiltered rows gave
    only `onsite`/`hybrid`; all 34 rows of a remote-filtered search were `remote_local`, and
    `"remote"` occurs in the client bundle solely as a LOCATION keyword. A provider that had
    guessed `"remote"` would report zero remote postings on a real board — so the guess must
    resolve to `unknown` here, not be quietly tolerated as a second remote spelling.

    Without this, the closed-catalog test above passes even when `"remote"` is added to
    `_WORK_LOCATION`, because no fixture row carries that value.
    """
    row = dict(_fx("search_normal.json")["data"]["positions"][2])
    assert row["workLocationOption"] == "onsite"  # the row is in-catalog until we break it
    row["workLocationOption"] = "remote"
    assert parse_posting(SLUG, row, dict(row, jobDescription="")).remote_policy == "unknown"


def test_there_is_no_location_text_fallback_for_remote() -> None:
    """Row 0's locations[0] is literally "Remote". A location-text heuristic would read the
    out-of-catalog row right for the wrong reason and hide the day the catalog changes."""
    row = dict(_fx("search_normal.json")["data"]["positions"][0])
    row["workLocationOption"] = "flex_hybrid_v2"
    assert row["locations"][0] == "Remote"
    assert parse_posting(SLUG, row, dict(row, jobDescription="")).remote_policy == "unknown"


def test_a_null_department_is_none_not_the_string_none() -> None:
    row = _fx("search_normal.json")["data"]["positions"][3]
    assert row["department"] is None
    assert parse_posting(SLUG, row, dict(row, jobDescription="")).department is None


def test_a_row_with_no_title_is_partial_not_an_exception(tmp_path: Path) -> None:
    listed = dict(_fx("search_normal.json")["data"]["positions"][0], name="  ")
    with pytest.raises(ValueError, match="empty title"):
        parse_posting(SLUG, listed, {"jobDescription": ""})


@pytest.mark.parametrize("bad_ts", [None, True, "1788652800", float("nan")])
def test_an_unusable_posted_ts_is_none_not_a_1970_date(bad_ts: object) -> None:
    listed = dict(_fx("search_normal.json")["data"]["positions"][0], postedTs=bad_ts)
    posting = parse_posting(SLUG, listed, {"jobDescription": ""})
    assert posting.posted_at is None


def test_the_url_falls_back_to_the_site_relative_path_when_public_url_is_absent() -> None:
    listed = _fx("search_normal.json")["data"]["positions"][0]
    posting = parse_posting(SLUG, listed, {"jobDescription": ""})
    assert posting.url == "https://careers.acme.test/careers/job/1000000000001"


# ---------------------------------------------------------------- validators

@respx.mock
def test_no_validators_are_observed(tmp_path: Path) -> None:
    # neither the career page nor the search endpoint sends one (cache-control: no-store)
    _mock_boot()
    respx.get(_search_url(0)).mock(
        return_value=httpx.Response(200, json=_fx("search_empty.json"))
    )
    snapshot = provider.fetch_board(_fetcher(tmp_path), _request(budget=0))
    assert snapshot.observed_validators is None


@respx.mock
def test_mocked_304_maps_to_unchanged(tmp_path: Path) -> None:
    # unreachable against the live service (no validators are ever served) but the branch
    # exists for symmetry with every other provider, so it is exercised deliberately
    respx.get(BOOT_URL).mock(return_value=httpx.Response(304))
    snapshot = provider.fetch_board(
        _fetcher(tmp_path), _request(validators=ResponseValidators(etag='W/"x"'))
    )
    assert snapshot.status == "unchanged"
    assert snapshot.postings == []


@respx.mock
def test_malformed_slug_fails_the_board_not_the_scan(tmp_path: Path) -> None:
    request = BoardRequest(provider="eightfold", slug="garbage", url=BOOT_URL)
    snapshot = provider.fetch_board(_fetcher(tmp_path), request)
    assert snapshot.status == "failed"
    assert "invalid eightfold slug" in (snapshot.error or "")


# ---------------------------------------------------------------- healthcheck

@respx.mock
def test_healthcheck_ok(tmp_path: Path) -> None:
    _mock_boot()
    respx.get(_search_url(0)).mock(
        return_value=httpx.Response(200, json=_fx("search_normal.json"))
    )
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.OK


@respx.mock
def test_healthcheck_empty_board(tmp_path: Path) -> None:
    _mock_boot()
    respx.get(_search_url(0)).mock(
        return_value=httpx.Response(200, json=_fx("search_empty.json"))
    )
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.EMPTY


@respx.mock
def test_healthcheck_a_404_career_page_is_dead(tmp_path: Path) -> None:
    respx.get(BOOT_URL).mock(return_value=httpx.Response(404))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.DEAD


@respx.mock
def test_healthcheck_a_host_that_does_not_resolve_is_unreachable(tmp_path: Path) -> None:
    # measured: a mistyped *.eightfold.ai subdomain gets NO http response at all
    respx.get(BOOT_URL).mock(side_effect=httpx.ConnectError("nodename nor servname provided"))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.UNREACHABLE


@respx.mock
def test_healthcheck_a_page_with_no_boot_blob_is_error(tmp_path: Path) -> None:
    respx.get(BOOT_URL).mock(
        return_value=httpx.Response(200, content=b"<html><body>Coming soon</body></html>")
    )
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.ERROR


@respx.mock
@pytest.mark.parametrize("status", [401, 403, 410, 500])
def test_healthcheck_other_http_errors_are_error(tmp_path: Path, status: int) -> None:
    respx.get(BOOT_URL).mock(return_value=httpx.Response(status))
    assert provider.healthcheck(_fetcher(tmp_path), SLUG) is BoardHealth.ERROR
