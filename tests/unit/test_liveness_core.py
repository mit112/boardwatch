"""P6 item 6 — the liveness decision itself, with no network and no store.

The claim under test is one-directional and is the whole design: **only an explicit gone-status
withholds a lead.** Every other outcome is served. These cases are the boundary of that claim,
written so that widening `GONE_STATUSES` — the single most tempting change here — turns one red.
"""

from __future__ import annotations

import pytest

from boardwatch.core.liveness import (
    GONE_STATUSES,
    SIGNAL_VERDICTS,
    SIGNALS,
    VERDICTS,
    ContradictoryLiveness,
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
    # The URL survives: withholding a lead is the one outcome somebody will check by hand.
    assert result.detail == "HTTP 404 for https://x.test/j/1"


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


def test_a_gone_status_reached_THROUGH_A_REDIRECT_is_served() -> None:  # noqa: N802
    """The stored URL never answered gone — something it was sent to did. An employer migrating
    ATS whose old links point at a new host with a dead deep-link path would otherwise have every
    one of its live requisitions withheld, and the 404 in the message would look conclusive."""
    result = verdict_for_failure(
        7, 404, "HTTP 404 for https://new.example/careers", redirected=True
    )
    assert result.verdict == "unknown"
    assert result.signal == "refetch_gone_after_redirect"
    assert result.withholds is False


def test_a_redirect_is_only_forgiven_for_the_GONE_statuses() -> None:  # noqa: N802
    """A redirected 403 is already `unknown`; it must keep the transport-error signal rather than
    claim a gone-status was seen. The new signal means one thing or it means nothing."""
    assert verdict_for_failure(7, 403, "HTTP 403", redirected=True).signal == "refetch_error"


def test_the_catalogs_are_closed_and_pinned() -> None:
    """Turning any other status into a withholding one has to edit a test that says why it is
    not one. Same for inventing a verdict outside the catalog."""
    assert GONE_STATUSES == frozenset({404, 410})
    assert VERDICTS == ("alive", "dead", "unknown")
    assert set(SIGNALS) == {
        "refetch_gone",
        "refetch_gone_after_redirect",
        "refetch_ok",
        "refetch_error",
        "no_url",
    }
    # Every signal declares its verdict, and `dead` is reachable through exactly one of them.
    assert set(SIGNAL_VERDICTS) == set(SIGNALS)
    assert [s for s, v in SIGNAL_VERDICTS.items() if v == "dead"] == ["refetch_gone"]


def test_every_signal_in_the_catalog_is_actually_emitted() -> None:
    """A catalog entry nothing produces is a bucket that cannot be audited. `not_probed` was in
    this catalog and was emitted by nothing — an unprobed run reports `checked is None` instead."""
    emitted = {
        verdict_for_status(1, 200).signal,
        verdict_for_status(1, 404).signal,
        verdict_for_failure(1, None, "x").signal,
        verdict_for_failure(1, 404, "x", redirected=True).signal,
        verdict_without_url(1).signal,
    }
    assert emitted == set(SIGNALS)


def test_an_out_of_catalog_verdict_raises_and_names_the_VERDICT() -> None:  # noqa: N802
    """Typed at the raise site, so no caller downstream classifies a liveness outcome by
    string-matching a message (CLAUDE.md). The exception says WHICH field was wrong."""
    with pytest.raises(UnknownLivenessVerdict) as exc:
        Liveness(posting_id=1, verdict="gone", signal="refetch_ok")
    assert exc.value.verdict == "gone"
    assert exc.value.signal is None


def test_an_out_of_catalog_signal_raises_and_names_the_SIGNAL() -> None:  # noqa: N802
    """Asserted separately from the verdict case, because one exception class serving both is
    exactly how a traceback ends up saying "not a verdict" about a bad signal."""
    with pytest.raises(UnknownLivenessVerdict) as exc:
        Liveness(posting_id=1, verdict="alive", signal="body_says_closed")
    assert exc.value.signal == "body_says_closed"
    assert exc.value.verdict is None


def test_a_verdict_its_signal_does_not_sanction_cannot_be_BUILT() -> None:  # noqa: N802
    """Both fields catalogued and still wrong. `dead` + `refetch_error` is the dangerous pair: it
    passes both membership checks and withholds a posting that merely timed out, inverting the
    fail-open direction at a call site rather than in the catalog where it could be reviewed."""
    with pytest.raises(ContradictoryLiveness) as exc:
        Liveness(posting_id=1, verdict="dead", signal="refetch_error")
    assert exc.value.expected == "unknown"
    assert exc.value.signal == "refetch_error"


def test_only_dead_withholds() -> None:
    """The whole gate, in one assertion: `alive` and `unknown` both reach the lead list. Built
    through the signal catalog, since a verdict no signal carries can no longer be constructed."""
    withholding = {
        verdict
        for signal, verdict in SIGNAL_VERDICTS.items()
        if Liveness(posting_id=1, verdict=verdict, signal=signal).withholds
    }
    assert withholding == {"dead"}
