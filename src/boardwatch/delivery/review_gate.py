"""Delivery-time apply/review lane classification.

The queue already excludes ``ineligible`` (D-321); the gap is every verdict that
rides into the apply queue by failing open at a ranker gate — location ``unknown``
passes the hard US gate (fail-open on the unclassifiable, by the visa ruling) and
role ``uncertain`` passes the role gate. This re-checks both *positively*: an
lead reaches the blindly-appliable queue only when it is confirmed US and confirmed
software. Anything else — a foreign/unknown location, a non-software title, or an
unevaluated (``None``) verdict — routes to the review lane instead. That includes an
``eligible`` lead: eligibility answers the six blocker families, and says nothing about
whether the role is software or the office is in the US.

Three further gates narrow the same fail-open from the other side. A lead can be US and
software and still carry a requirement the engine could not confirm: an experience bar it
does not meet or cannot resolve, or a hard-family (work_auth/clearance) rule that ABSTAINED.
Those rode into the apply queue as ``uncertain``, because the verdict alone cannot say which
requirement was unresolved. They now route to review — reviewable, NOT dropped, which is the
narrowing the owner asked for: an abstain is not evidence of ineligibility and must never be
spent as though it were (D-380).

The third gate is not the same shape as those two, and it is **not a bug fix — it is what the
apply lane MEANS.** A lead whose current evaluation produced NO requirement row at all was in
the blind-apply queue because the eligibility catalog found nothing in its job description,
never because a rule cleared anything: a clear by silence with an empty evidence chain, which
is the one thing the keystone forbids ("No flags" ≠ cleared). MEASURED on the live store on
2026-09-03 through ``delivered_unapplied`` + :func:`lane`, before and after on ONE snapshot:
521 of 646 apply-lane leads (81%) were there for that reason alone, and a blind two-judge
audit priced that population at 32% unapplyable. They now route to review, and the apply lane
means "a rule read this JD and cleared it". A lead nothing has evaluated at all is the same
silence one step earlier and goes the same way, under its own reason.

Reading those gates means this is no longer a pure re-derivation over the row's own
fields: it takes a three-boolean SUMMARY of the row's current requirement set, which the caller
reads under the SAME identity as the verdict it passes alongside. That is a deliberate
departure from D-323's "reads no stored eligibility state". The drift D-323 guarded against is
this module reaching into the DB on its own and disagreeing with the caller's verdict; the
summary travels WITH the verdict from one identity-scoped read, so the two cannot come from
different evaluations. All three flags default False, which is exactly the old behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, NamedTuple, get_args

from boardwatch.rank.location_gate import classify_location
from boardwatch.rank.role_gate import role_verdict

#: The review-lane drain directory. Registered in ``delivery.names.DRAIN_DIRS``.
REVIEW_DIR = "_review"

#: The closed-posting drain directory. Registered in ``delivery.names.DRAIN_DIRS``.
#:
#: Its OWN drain rather than a share of :data:`REVIEW_DIR`, because the two ask the reader for
#: opposite things: a review lead is work to look at, and a closed one is work that no longer
#: exists. Folding them together would put a dead posting in the same folder as live work and
#: leave the reader to tell them apart by opening each one — which is the cost this drain exists
#: to remove. Keeping it out of ``_ineligible`` matters for the same reason in reverse: closed is
#: a fact about the world, not a verdict the eligibility gate reached, and blending the two would
#: corrupt the lane-split numbers every precision report is read against.
CLOSED_DIR = "_closed"

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
#:
#: ``no_requirements_found`` and ``unevaluated`` are the two absences, and they are separate from
#: each other for the same test: what the reader does next differs. A zero-row lead HAS a current
#: evaluation and the catalog found nothing in its body — that will not change until the catalog
#: does, so the JD needs a human read. An ``unevaluated`` lead has no current evaluation at all,
#: which is transient: the next eligibility run may well decide it. Folding them would also lose
#: the split the change is measured on (521 zero-row against 34 unevaluated on 2026-09-03).
#: Neither is folded into the two flags above, which both presuppose a ROW the engine could not
#: resolve; these two say there is no row, and no evaluation, respectively.
#:
#: ``seniority_above_band`` (T44) is TITLE-only, never a re-derivation over the JD body: D-477
#: explicitly rejected a deterministic body-seniority verdict family. The caller derives it from
#: `rank.seniority_gate.seniority_verdict` and passes the one bit that ever moves a lead —
#: ``uncertain``/``in_band`` are indistinguishable to this gate on purpose, matching how the two
#: requirement flags above already travel as a summary rather than a re-derivation.
ReviewReason = Literal[
    "ineligible_verdict",
    "non_us_location",
    "role_vetoed",
    "role_unconfirmed",
    "unevaluated",
    "no_requirements_found",
    "eligibility_unconfirmed",
    "experience_requirement",
    "seniority_above_band",
]


#: The same catalog at runtime, for a caller that PERSISTS a reason and must refuse an unknown
#: one rather than publish it. `get_args` rather than a restated tuple: a hand-copied list would
#: keep validating against a stale catalog the moment a member is added above.
REVIEW_REASONS: frozenset[str] = frozenset(get_args(ReviewReason))


class LaneDecision(NamedTuple):
    """One lane call: the drain directory (``""`` for the apply queue) and why.

    ``reason`` is non-``None`` **exactly** when ``lane`` is :data:`REVIEW_DIR` — :data:`CLOSED_DIR`
    carries ``None`` like the apply queue does, because a closed posting is not being held for a
    reason drawn from the review catalog; it is simply gone. The two travel as one value from one
    function so nothing downstream can pair a lane with a reason derived somewhere else.
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
    no_requirement_rows: bool = False,
    posting_closed: bool = False,
    seniority_above_band: bool = False,
) -> LaneDecision:
    """Decide the lane AND, in the same pass, which of the nine reasons held the lead.

    The single place either answer is computed. The reason is a by-product of the branch the
    lane decision already takes, never a re-derivation, which is why the two cannot disagree.

    ``eligible`` is blindly-appliable and always promotes. ``ineligible`` is excluded
    upstream and is not expected here; if one arrives it is held for review, never
    blind-applied. Everything else — ``uncertain`` or an unevaluated ``None`` verdict —
    is held for review when it is *confirmed* non-US, *confirmed* non-software, or the
    requirement summary says no rule cleared anything (the three flags below).

    The three flags are read AFTER the ``eligible`` short-circuit, so they cannot move an
    ``eligible`` lead. For the two unconfirmed flags that is not a gap under a policy that makes
    the families blockers: a ``work_auth``/``clearance``/``experience_years`` row resolving
    ``unmet`` or ``unknown`` is blocking, so the verdict cannot be ``eligible`` in the first
    place — the flags are always False there. Under a policy that demotes one of those families
    below ``blocker`` the row stops blocking and the verdict CAN be ``eligible`` with the flag
    set; routing that lead is a separate decision about whether ``eligible`` should face any gate
    at all, which is not settled here and is deliberately left where it is.

    ``no_requirement_rows`` sits below the short-circuit for a stronger reason than safety, and it
    was MEASURED rather than assumed: of the 646 apply-lane leads on 2026-09-03, all 521 zero-row
    ones were ``uncertain`` and NONE were ``eligible``, so the placement holds nothing back today.
    It is also nearly empty by construction. ``engine.evaluate``'s own zero-row branch already
    returns ``uncertain`` whenever no family — enabled or user-EXCLUDED — could have found a
    requirement, which is exactly the clear-by-silence this gate is for. ``eligible`` with zero
    rows is what is left: an excluded family WOULD have detected a requirement, i.e. the JD stated
    one and the user's own policy opted out of it. That is a decision, not silence, so holding it
    would re-open a settled question — and unlike the two flags above, this gate cannot be caught
    out by family SEVERITY, because a lead with no rows has no rows of any severity (D-380's R2
    gap is untouched by it).

    Location fails OPEN on ``unknown``, exactly as the hard US gate does (the visa ruling:
    an unclassifiable location is never blind-dropped). Only a confirmed ``non_us`` lead is
    demoted; a bare ``"Remote"`` or any location the classifier cannot place stays in the
    apply queue. A genuinely foreign city the classifier does not recognise (e.g. an
    unlisted "Kaunas Office") reads ``unknown`` and is a classifier-coverage gap to close in
    ``rank/location_data`` (the D-294 pattern), not something to fix by demoting every
    remote lead here. Role, by contrast, is demoted on anything not positively ``swe`` — a
    title carrying no software signal is not blindly-appliable.

    An unevaluated (``None``) verdict is held for review, and REVERSES the reading that it be
    treated like ``uncertain``. ``eligibility_evaluations.verdict`` is ``NOT NULL`` under a
    three-value CHECK, so ``None`` here means exactly one thing: no current evaluation exists
    under this identity (a stale one after the profile identity moved, or a body-less lead the
    engine never saw). Nothing cleared anything for such a lead either, which is the same silence
    the zero-row gate refuses — so it goes the same way rather than resting on location and title
    alone. It is reviewable, NOT dropped, and it is the transient case: the next eligibility run
    can return a real verdict and move it back.
    """
    # ABOVE every other branch, and the ordering is the point: a closed posting cannot be applied
    # to, so no verdict, location or role below can make it work again. Reaching this first is also
    # what stops a dead lead consuming a review slot it can never be released from.
    #
    # `posting_closed` is `status == "closed"`, NEVER `status != "open"`. The third rendered status
    # is `unverifiable` — open, but on a board nothing enumerates (D-324) — and draining it here
    # would bury live postings whose only fault is that boardwatch cannot currently see their
    # board. That is the fail-open direction a liveness judge is owed.
    if posting_closed:
        return LaneDecision(CLOSED_DIR, None)
    if verdict == "ineligible":
        return LaneDecision(REVIEW_DIR, "ineligible_verdict")
    if classify_location(list(locations)) == "non_us":
        return LaneDecision(REVIEW_DIR, "non_us_location")
    role = role_verdict(title)[0]
    if role == "not_swe":
        return LaneDecision(REVIEW_DIR, "role_vetoed")
    if role != "swe":
        return LaneDecision(REVIEW_DIR, "role_unconfirmed")
    # T44. TITLE-only, like the two gates just above, and for the same reason it sits here rather
    # than below the `eligible` short-circuit: eligibility answers the six blocker families and
    # says nothing about whether the title is above the operator's target band, so an `eligible`
    # verdict must not let a senior title ride straight into the blind-apply queue either. The
    # caller derives the bit from `rank.seniority_gate.seniority_verdict` — never from the JD
    # body (D-477 rejected a deterministic body-seniority family) — and this gate does not
    # distinguish `uncertain` from `in_band`: both leave the lead exactly where every earlier
    # gate already put it.
    if seniority_above_band:
        return LaneDecision(REVIEW_DIR, "seniority_above_band")
    # R1. `eligible` used to short-circuit ABOVE the two gates above, so an eligible posting was
    # blindly-appliable however foreign or however far from software it was — the 2026-08-30 audit
    # found a "Field Auto Adjuster" marked eligible sitting in the apply queue, and an independent
    # blind judge scored 5 role-family mismatches in 80 apply-lane items against job-apps' 0 in 80.
    # It now falls through location and role like every other verdict.
    #
    # IT STILL SHORT-CIRCUITS HERE, above the two requirement-flag gates, and that placement is the
    # whole of the change's scope. `eligible` means the blocking families were DECIDED and cleared,
    # so an unconfirmed-requirement hold below would be re-opening a settled question rather than
    # narrowing a fail-open. It is also what keeps D-380's known R2 gap shut: those flags ignore
    # family SEVERITY, which is policy-level and not stored per row, so a `preference`-family row
    # that could never block would hold an eligible lead for review. D-380 records that gap as
    # reachable ONLY once this short-circuit moves below the flags. It does not move below them.
    if verdict == "eligible":
        return LaneDecision("", None)
    # The two ABSENCES rank above the two unconfirmed-row flags, and above each other in this
    # order, because each one EXPLAINS the silence of the ones below it: with no evaluation there
    # are no rows, and with no rows there is no unconfirmed row either. Reporting a row-derived
    # reason for a lead that has no row would name evidence that does not exist — the same error
    # as reporting the experience bar when a hard-family rule abstained. The combination is in any
    # case unreachable from the production read, which derives all three from one query, so the
    # ranking's only job is to decide what a caller who passes both is told.
    if verdict is None:
        return LaneDecision(REVIEW_DIR, "unevaluated")
    if no_requirement_rows:
        return LaneDecision(REVIEW_DIR, "no_requirements_found")
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
    no_requirement_rows: bool = False,
    posting_closed: bool = False,
    seniority_above_band: bool = False,
) -> str:
    """Return ``""`` for the apply queue, :data:`REVIEW_DIR`, or :data:`CLOSED_DIR`.

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
        no_requirement_rows=no_requirement_rows,
        posting_closed=posting_closed,
        seniority_above_band=seniority_above_band,
    ).lane
