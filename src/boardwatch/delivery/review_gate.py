"""Delivery-time apply/review lane classification.

The queue already excludes ``ineligible`` (D-321); the gap is ``uncertain``, which
rides into the apply queue by failing open at a ranker gate — location ``unknown``
passes the hard US gate (fail-open on the unclassifiable, by the visa ruling) and
role ``uncertain`` passes the role gate. This re-checks both *positively*: an
``uncertain`` lead reaches the blindly-appliable queue only when it is confirmed US
and confirmed software. Anything else — a foreign/unknown location, a non-software
title, or an unevaluated (``None``) verdict — routes to the review lane instead.

Pure re-derivation over the row's own fields; reads no stored eligibility state, so
it introduces no state that can drift from the DB (D-323).
"""

from __future__ import annotations

from collections.abc import Sequence

from boardwatch.rank.location_gate import classify_location
from boardwatch.rank.role_gate import role_verdict

#: The review-lane drain directory. Registered in ``delivery.names.DRAIN_DIRS``.
REVIEW_DIR = "_review"


def lane(*, verdict: str | None, locations: Sequence[str], title: str) -> str:
    """Return ``""`` for the apply queue or ``REVIEW_DIR`` for the review lane.

    ``ineligible`` is excluded upstream and is not expected here; if one arrives it
    is treated as review (never blind-apply).
    """
    if verdict == "eligible":
        return ""
    if verdict != "uncertain":
        return REVIEW_DIR
    if classify_location(list(locations)) != "us":
        return REVIEW_DIR
    if role_verdict(title)[0] != "swe":
        return REVIEW_DIR
    return ""
