"""The tenant-assumption report: which ranker and review gates decided on the TENANT's data.

The eligibility engine abstains when a rule's profile field is missing. The ranker's and the
review gate's six gates cannot: each one hard-codes a US, software, entry-level tenant
(DESIGN-T183 §1), so a second tenant's postings are dropped or held on an assumption their
profile never made, and no counter says so. This module changes no decision. It REPORTS, per
gate and per run, whether each decision was grounded in a profile field the gate should read:

- ``fired``: the gate fired, and the profile field it reads backs the built-in assumption.
- ``abstained``: counts by reason. ``missing_profile_field:X`` (or a named mismatch) means the
  gate had no tenant data to decide on, and EVERY posting it saw is counted there, whatever it
  did. The gate's own abstains (``role_uncertain``, ``uncertain_band``, ...) are counted there
  only when it WAS grounded.
- ``fired_on_default``: the subset of the ungrounded abstains the built-in default still
  dropped or held. The existing drop counters say what the code did; this says how much of it
  rested on nothing the tenant declared.

``considered`` is the postings (ranker) or delivered leads (review) the gate was applied to, so
``considered == fired + passed + sum(abstained)`` and ``fired_on_default <= sum(abstained)``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Literal

from boardwatch.rank.location_gate import location_target
from boardwatch.rank.role_taxonomy import MISSING_ROLE_TAXONOMY

TenantGate = Literal[
    "location", "foreign_ad", "role", "zero_signal", "seniority_field", "judge_seniority"
]


def ungrounded_reasons(
    *,
    field: str | None,
    taxonomy_field: str | None,
    field_tiers: Collection[str],
    target_seniority_band: str,
    seniority_hold: bool,
    target_countries: Sequence[str],
) -> dict[TenantGate, str | None]:
    """Per gate, why it has no tenant data to decide on, or ``None`` when it does.

    ``field`` is the user's field as the ranker knows it, the one their role taxonomy declares
    (``role_taxonomy.declared_field``) and the key every field-dependent ranker gate reads; it
    is not ``Facts.career_field``, an eligibility input none of these gates reads. The role gate
    is grounded whenever the user HAS a taxonomy, bundled or gathered (T184). The zero-signal
    rule is grounded only when the skill taxonomy's declared field (``taxonomy_field``) is the
    user's, and it abstains itself otherwise (T187 C2). The seniority gate is grounded only
    when ``leveling.yaml`` has a word tier for the field (``field_tiers``, its field names), and
    abstains itself otherwise (T187 C4).
    """
    role: str | None
    zero_signal: str | None
    seniority: str | None
    if field is None:
        role = zero_signal = seniority = MISSING_ROLE_TAXONOMY
    else:
        role = None
        zero_signal = (
            None if taxonomy_field == field
            else f"taxonomy_field:{taxonomy_field or 'undeclared'}!={field}"
        )
        seniority = None if field in field_tiers else f"missing_field_tier:{field}"
    if not seniority_hold:
        judge: str | None = "disarmed:gate.seniority_hold"
    elif target_seniority_band == "any":
        # The final gate's `seniority_fit` question is asked against the declared band
        # (`oracle.judging_policy`); `any` declares none, so it is not asked (T188).
        judge = "not_asked:target_seniority_band=any"
    else:
        judge = None
    # Both location gates read the profile's `target_countries` (DESIGN-T183 B3) and are INERT
    # when it is undeclared or a target has no positive pack — the same reason either way.
    location = location_target(target_countries).abstain
    return {
        "location": location,
        "foreign_ad": location,
        "role": role,
        "zero_signal": zero_signal,
        "seniority_field": seniority,
        "judge_seniority": judge,
    }


@dataclass
class GateTally:
    considered: int = 0
    fired: int = 0
    fired_on_default: int = 0
    abstained: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, object]:
        return {
            "considered": self.considered,
            "fired": self.fired,
            "fired_on_default": self.fired_on_default,
            "abstained": dict(sorted(self.abstained.items())),
        }


@dataclass
class TenantAssumptionTally:
    """One site's counts (the ranker's or the review gate's), keyed by gate."""

    grounding: dict[TenantGate, str | None]
    gates: dict[TenantGate, GateTally] = field(default_factory=dict)

    def observe(self, gate: TenantGate, *, fired: bool, own_abstain: str | None = None) -> None:
        """Count one posting the gate was applied to: what it did, and on whose data."""
        tally = self.gates.setdefault(gate, GateTally())
        tally.considered += 1
        ungrounded = self.grounding[gate]
        if ungrounded is not None:
            tally.abstained[ungrounded] += 1
            tally.fired_on_default += fired
        elif fired:
            tally.fired += 1
        elif own_abstain is not None:
            tally.abstained[own_abstain] += 1

    def to_dict(self) -> dict[str, object]:
        return {gate: tally.to_dict() for gate, tally in sorted(self.gates.items())}


#: `delivery/review_gate.classify`'s reasons in ITS order, up to and including each tenant gate. A
#: lead an earlier clause held never reached the later gate, so it is not "considered" there — a
#: report that counted it would claim a location abstain for a lead the form question stopped
#: (T185 review). Kept beside the tally rather than inside `classify` so the gate stays
#: decision-only; the review-gate test pins this list against the classifier's own order.
_REVIEW_REASONS_BEFORE: dict[str, frozenset[str]] = {
    "location": frozenset({"form_question_hard_stop", "ineligible_verdict"}),
    "role": frozenset({"form_question_hard_stop", "ineligible_verdict", "non_us_location"}),
    "judge_seniority": frozenset({
        "form_question_hard_stop", "ineligible_verdict", "non_us_location", "role_vetoed",
        "role_gate_unmeasured", "role_unconfirmed", "seniority_above_band",
        "judged_ineligible_verdict",
    }),
}


def review_gate_reached(gate: TenantGate, reason: str | None) -> bool:
    """Whether `classify` ran `gate` for a lead whose decision carried `reason`.

    `None` (the apply lane, or a hold below every tenant gate) reached all of them; a reason
    from a clause above the gate means the gate never ran.
    """
    return reason not in _REVIEW_REASONS_BEFORE[gate]


@dataclass(frozen=True)
class TenantAssumptionReport:
    ranker: TenantAssumptionTally
    # `None` when the lane split did not run this run (no leads reached it).
    review: TenantAssumptionTally | None


def tenant_assumptions_to_dict(report: TenantAssumptionReport | None) -> dict[str, object] | None:
    """`None` means NOT MEASURED, never a run whose gates saw nothing."""
    if report is None:
        return None
    return {
        "ranker": report.ranker.to_dict(),
        "review": None if report.review is None else report.review.to_dict(),
    }
