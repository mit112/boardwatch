"""The closed catalog of JD-acquisition outcomes (design §4.4).

Every outcome is a distinct typed value with its own counter, recorded at the site that knows
which one applies. The specification for this is the prior art's failure mode inverted: job-apps'
`fetch_rendered_jd` wraps everything in `except Exception: return ""`, so a missing browser
dependency, a timeout and a login wall are one empty string. Its browser tier then ran 11
consecutive scheduled runs recovering exactly zero, and nothing failed.

`is_silent_outage` exists so that condition is reportable. A tier that attempted work and resolved
nothing is not a benign zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, get_args

AcquisitionOutcome = Literal[
    # A body arrived with the listing itself, at no extra request.
    "body_inline",
    # A body arrived from a second request against a resolvable posting URL.
    "body_fetched",
    # 401 / 403. The host knows who we are and said no.
    "fetch_refused",
    # 404 / 410. The posting is gone; that is not a fetch defect.
    "fetch_gone",
    # Timeout, 5xx, transport error. Retryable in principle, absent in fact.
    "fetch_unavailable",
    # A dependency the tier needs is not installed. NEVER folded into a fetch failure — that
    # exact confusion is what hid the prior art's outage for 11 days.
    "dependency_missing",
    # A response arrived and extraction produced nothing substantive.
    "extracted_empty",
    # The two-sided login-wall test fired (design §4.5): >=2 wall markers AND zero real-JD
    # section markers. One-sided fails — nearly every real posting says "Sign in" in a footer.
    "rejected_login_wall",
    # Extracted, but below the quality floor, or the body declared a different role family.
    "rejected_quality_gate",
    # No resolvable posting URL existed to attempt. Counted, never skipped silently.
    "not_attemptable",
]

ACQUISITION_OUTCOMES: tuple[str, ...] = get_args(AcquisitionOutcome)

# The only two outcomes that produced a usable body. Named rather than derived by exclusion, so
# that adding an outcome cannot silently make it count as a success.
_RESOLVED: frozenset[str] = frozenset({"body_inline", "body_fetched"})


class UnknownAcquisitionOutcome(ValueError):
    """Raised at the recording site for an outcome outside the closed catalog."""

    def __init__(self, name: str) -> None:
        super().__init__(f"unknown acquisition outcome: {name!r}")
        self.name = name


class AcquisitionTally:
    """Counts every acquisition attempt by outcome, with all ten keys always present.

    All ten are instrumented, so a 0 here is a measured zero rather than an absence. That
    distinction is the whole point: an absent key reads as "not measured", and D-022/D-023 record
    a naive attribution of exactly that kind as nearly having cost job-apps a working adapter.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = dict.fromkeys(ACQUISITION_OUTCOMES, 0)

    def record(self, outcome: str) -> None:
        if outcome not in self._counts:
            raise UnknownAcquisitionOutcome(outcome)
        self._counts[outcome] += 1

    @property
    def counts(self) -> Mapping[str, int]:
        return dict(self._counts)

    @property
    def attempted(self) -> int:
        return sum(self._counts.values())

    @property
    def resolved(self) -> int:
        return sum(count for name, count in self._counts.items() if name in _RESOLVED)

    @property
    def is_silent_outage(self) -> bool:
        """Attempts were made and none produced a body.

        Not `resolved == 0` alone: a tier with nothing to do is not an outage, and reporting one
        would train the reader to ignore the signal.
        """
        return self.attempted > 0 and self.resolved == 0
