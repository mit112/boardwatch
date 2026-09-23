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
from dataclasses import dataclass, field
from typing import Literal

from boardwatch.rank.leveling import DEFAULT_FIELD

TenantGate = Literal[
    "location", "foreign_ad", "role", "zero_signal", "seniority_field", "judge_seniority"
]

# The one band the final gate's `seniority_fit` question is written for ("is this an
# entry-level / new-grad / early-career role", `eligibility/oracle.py`).
_JUDGE_QUESTION_BAND = "entry"


def ungrounded_reasons(
    *, career_field: str | None, target_seniority_band: str, seniority_hold: bool
) -> dict[TenantGate, str | None]:
    """Per gate, why it has no tenant data to decide on, or ``None`` when it does.

    ``DEFAULT_FIELD`` is the field the role tables, the bundled taxonomy and the ranker's
    leveling tier were all written for; a gate keyed to it is grounded only when the profile's
    ``career_field`` names it.
    """
    role: str | None
    zero_signal: str | None
    seniority: str | None
    if career_field is None:
        role = zero_signal = seniority = "missing_profile_field:career_field"
    elif career_field != DEFAULT_FIELD:
        role = f"no_role_pack:{career_field}"
        zero_signal = f"taxonomy_field:{DEFAULT_FIELD}!={career_field}"
        seniority = f"field_tier:{DEFAULT_FIELD}!={career_field}"
    else:
        role = zero_signal = seniority = None
    if not seniority_hold:
        judge: str | None = "disarmed:gate.seniority_hold"
    elif target_seniority_band != _JUDGE_QUESTION_BAND:
        judge = f"question_band:{_JUDGE_QUESTION_BAND}!={target_seniority_band}"
    else:
        judge = None
    # No profile field names the countries a tenant targets (DESIGN-T183 B1 adds one), so the
    # US assumption in both location gates is never grounded.
    location = "missing_profile_field:target_countries"
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
