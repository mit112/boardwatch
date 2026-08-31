"""Delivery-time apply/review lane classification.

The queue already excludes ``ineligible`` (D-321); the gap is ``uncertain``, which
rides into the apply queue by failing open at a ranker gate — location ``unknown``
passes the hard US gate (fail-open on the unclassifiable, by the visa ruling) and
role ``uncertain`` passes the role gate. This re-checks both *positively*: an
``uncertain`` lead reaches the blindly-appliable queue only when it is confirmed US
and confirmed software. Anything else — a foreign/unknown location, a non-software
title, or an unevaluated (``None``) verdict — routes to the review lane instead.

Two further gates narrow the same fail-open from the other side. A lead can be US and
software and still carry a requirement the engine could not confirm: an experience bar it
does not meet or cannot resolve, or a hard-family (work_auth/clearance) rule that ABSTAINED.
Those rode into the apply queue as ``uncertain``, because the verdict alone cannot say which
requirement was unresolved. They now route to review — reviewable, NOT dropped, which is the
narrowing the owner asked for: an abstain is not evidence of ineligibility and must never be
spent as though it were (D-380).

Reading those two gates means this is no longer a pure re-derivation over the row's own
fields: it takes a two-boolean SUMMARY of the row's current requirement set, which the caller
reads under the SAME identity as the verdict it passes alongside. That is a deliberate
departure from D-323's "reads no stored eligibility state". The drift D-323 guarded against is
this module reaching into the DB on its own and disagreeing with the caller's verdict; the
summary travels WITH the verdict from one identity-scoped read, so the two cannot come from
different evaluations. Both flags default False, which is exactly the old behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, NamedTuple

from boardwatch.rank.location_gate import classify_location
from boardwatch.rank.role_gate import role_verdict

#: The review-lane drain directory. Registered in ``delivery.names.DRAIN_DIRS``.
REVIEW_DIR = "_review"

#: Why a lead is held. A CLOSED catalog: one member per branch of :func:`classify`, so a value
#: outside it is a bug rather than a new bucket, and the page's map over it stays exhaustive.
#:
#: ``role_vetoed`` and ``role_unconfirmed`` are separate members on purpose. The role gate returns
#: three answers and only ``not_swe`` is a veto; ``uncertain`` is an abstain, and reporting it as
#: "not software" would assert the decision the gate declined to make — the same error as folding
#: an abstain into a neighbour.
#:
#: ``experience_requirement`` and ``eligibility_unconfirmed`` are likewise separate, and neither is
#: folded into an existing member. They are held for OPPOSITE reasons and the reader acts on them
#: differently: an experience bar is a stated requirement the lead may still be worth applying to,
#: while a hard-family abstain means a blocking rule could not be decided at all and the JD needs
#: reading before anything is spent on it. Reporting either as ``role_unconfirmed`` would name the
#: wrong gate; adding one member for both would lose the distinction the reader needs.
ReviewReason = Literal[
    "ineligible_verdict",
    "non_us_location",
    "role_vetoed",
    "role_unconfirmed",
    "eligibility_unconfirmed",
    "experience_requirement",
]


class LaneDecision(NamedTuple):
    """One lane call: the drain directory (``""`` for the apply queue) and why.

    ``reason`` is non-``None`` **exactly** when ``lane`` is :data:`REVIEW_DIR`. The two travel as
    one value from one function so nothing downstream can pair a lane with a reason derived
    somewhere else.
    """

    lane: str
    reason: ReviewReason | None


def classify(
    *,
    verdict: str | None,
    locations: Sequence[str],
    title: str,
    experience_unconfirmed: bool = False,
    eligibility_unconfirmed: bool = False,
) -> LaneDecision:
    """Decide the lane AND, in the same pass, which of the six reasons held the lead.

    The single place either answer is computed. The reason is a by-product of the branch the
    lane decision already takes, never a re-derivation, which is why the two cannot disagree.

    ``eligible`` is blindly-appliable and always promotes. ``ineligible`` is excluded
    upstream and is not expected here; if one arrives it is held for review, never
    blind-applied. Everything else — ``uncertain`` or an unevaluated ``None`` verdict —
    is held for review when it is *confirmed* non-US, *confirmed* non-software, or carries
    an unconfirmed requirement (the two flags below).

    The two flags are read AFTER the ``eligible`` short-circuit, so they cannot move an
    ``eligible`` lead. That is not a gap under a policy that makes the families blockers: a
    ``work_auth``/``clearance``/``experience_years`` row resolving ``unmet`` or ``unknown``
    is blocking, so the verdict cannot be ``eligible`` in the first place — the flags are
    always False there. Under a policy that demotes one of those families below ``blocker``
    the row stops blocking and the verdict CAN be ``eligible`` with the flag set; routing
    that lead is a separate decision about whether ``eligible`` should face any gate at all,
    which is not settled here and is deliberately left where it is.

    Location fails OPEN on ``unknown``, exactly as the hard US gate does (the visa ruling:
    an unclassifiable location is never blind-dropped). Only a confirmed ``non_us`` lead is
    demoted; a bare ``"Remote"`` or any location the classifier cannot place stays in the
    apply queue. A genuinely foreign city the classifier does not recognise (e.g. an
    unlisted "Kaunas Office") reads ``unknown`` and is a classifier-coverage gap to close in
    ``rank/location_data`` (the D-294 pattern), not something to fix by demoting every
    remote lead here. Role, by contrast, is demoted on anything not positively ``swe`` — a
    title carrying no software signal is not blindly-appliable.

    An unevaluated (``None``) verdict is treated like ``uncertain`` rather than sent
    straight to review: a delivered lead is ``None`` only transiently (its evaluation went
    stale when the profile identity moved) or when it is body-less, and in both cases the
    location and title are the signals that decide whether the owner can open the link and
    apply. The eligibility verdict, when it returns, can only move such a lead to
    ``ineligible`` (excluded) — never make a foreign or non-software lead appliable.
    """
    if verdict == "eligible":
        return LaneDecision("", None)
    if verdict == "ineligible":
        return LaneDecision(REVIEW_DIR, "ineligible_verdict")
    if classify_location(list(locations)) == "non_us":
        return LaneDecision(REVIEW_DIR, "non_us_location")
    role = role_verdict(title)[0]
    if role == "not_swe":
        return LaneDecision(REVIEW_DIR, "role_vetoed")
    if role != "swe":
        return LaneDecision(REVIEW_DIR, "role_unconfirmed")
    # The hard-family abstain outranks the experience bar: it says a BLOCKING rule could not be
    # decided, which is a stronger reason to read the JD than a bar the engine did decide and the
    # lead simply may not clear. Reporting the weaker one when both hold would understate the hold.
    if eligibility_unconfirmed:
        return LaneDecision(REVIEW_DIR, "eligibility_unconfirmed")
    if experience_unconfirmed:
        return LaneDecision(REVIEW_DIR, "experience_requirement")
    return LaneDecision("", None)


def lane(
    *,
    verdict: str | None,
    locations: Sequence[str],
    title: str,
    experience_unconfirmed: bool = False,
    eligibility_unconfirmed: bool = False,
) -> str:
    """Return ``""`` for the apply queue or :data:`REVIEW_DIR` for the review lane.

    A one-line projection of :func:`classify`, and deliberately nothing more: the lane and the
    reason are ONE decision, so the only way to be sure the folder tree and the page never
    disagree about a lead is for both to read the same call. Re-deriving either here would be the
    second opinion ``_review`` exists to prevent (D-332).
    """
    return classify(
        verdict=verdict,
        locations=locations,
        title=title,
        experience_unconfirmed=experience_unconfirmed,
        eligibility_unconfirmed=eligibility_unconfirmed,
    ).lane
