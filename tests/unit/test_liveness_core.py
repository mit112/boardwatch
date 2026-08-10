"""P6 item 6 — the liveness decision itself, with no network and no store.

The claim under test is one-directional and is the whole design: **only an explicit gone-status
withholds a lead.** Every other outcome is served. These cases are the boundary of that claim,
written so that widening `GONE_STATUSES` — the single most tempting change here — turns one red.
"""

from __future__ import annotations

import pytest

from boardwatch.core.liveness import (
    GONE_STATUSES,
    SIGNALS,
    VERDICTS,
    Liveness,
    UnknownLivenessVerdict,
    verdict_for_failure,
    verdict_for_status,
    verdict_without_url,
)


@pytest.mark.parametrize("status", [404, 410])
def test_a_gone_status_withholds_the_lead(status: int) -> None:
    result = verdict_for_status(7, status)
    assert result.verdict == "dead"
    assert result.signal == "refetch_gone"
    assert result.withholds is True


@pytest.mark.parametrize("status", [200, 301, 302, 401, 403, 429, 500, 502, 503])
def test_every_other_status_is_served(status: int) -> None:
    """403 is the one that matters most and is measured, not hypothetical: on 2026-08-10
    `pinterestcareers.com` answered 403 to an unfamiliar user agent for a live posting. Reading
    403 as gone would blacklist whole employers silently."""
    assert verdict_for_status(7, status).withholds is False


def test_a_gone_status_arriving_as_a_FAILURE_still_withholds() -> None:  # noqa: N802
    """The path that actually runs. `Fetcher._send_once` raises `FetchFailure` for EVERY
    non-200, so in production a 404 never reaches `verdict_for_status` — reading only the happy
    path would make the probe find nothing at all while every test still passed."""
    result = verdict_for_failure(7, 404, "HTTP 404 for https://x.test/j/1")
    assert result.verdict == "dead"
    assert result.signal == "refetch_gone"


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (None, "ConnectTimeout: timed out"),
        (None, "ConnectError: refused"),
        (403, "HTTP 403 for https://x.test/j/1"),
        (500, "HTTP 500 for https://x.test/j/1"),
    ],
)
def test_an_unknown_outcome_fails_OPEN(status: int | None, detail: str) -> None:  # noqa: N802
    """Fail-open is the direction chosen per gate (CLAUDE.md): the cost of serving a dead
    posting is one wasted résumé; the cost of withholding a live one is a job nobody ever
    sees and nobody can know was missed."""
    result = verdict_for_failure(7, status, detail)
    assert result.verdict == "unknown"
    assert result.withholds is False
    assert result.detail == detail  # the reason survives, so a run can be diagnosed


def test_a_posting_with_no_url_claims_nothing() -> None:
    """`postings.url` is nullable. Nothing was asked, so nothing is asserted."""
    result = verdict_without_url(7)
    assert result.verdict == "unknown"
    assert result.signal == "no_url"
    assert result.withholds is False


def test_the_catalogs_are_closed_and_pinned() -> None:
    """Turning any other status into a withholding one has to edit a test that says why it is
    not one. Same for inventing a verdict outside the catalog."""
    assert GONE_STATUSES == frozenset({404, 410})
    assert VERDICTS == ("alive", "dead", "unknown")
    assert set(SIGNALS) == {
        "refetch_gone", "refetch_ok", "refetch_error", "no_url", "not_probed"
    }


@pytest.mark.parametrize(
    ("verdict", "signal"),
    [("gone", "refetch_ok"), ("alive", "body_says_closed")],
)
def test_an_out_of_catalog_value_raises_at_the_construction_site(
    verdict: str, signal: str
) -> None:
    """Typed at the raise site, so no caller downstream classifies a liveness outcome by
    string-matching a message (CLAUDE.md)."""
    with pytest.raises(UnknownLivenessVerdict):
        Liveness(posting_id=1, verdict=verdict, signal=signal)


def test_only_dead_withholds() -> None:
    """The whole gate, in one assertion: `alive` and `unknown` both reach the lead list."""
    withholding = {
        verdict
        for verdict in VERDICTS
        if Liveness(posting_id=1, verdict=verdict, signal="refetch_ok").withholds
    }
    assert withholding == {"dead"}
