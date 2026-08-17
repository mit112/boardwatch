"""Typed projection failures. Every arm of the fidelity contract has a member here.

A reason is a `StrEnum` member carried as a keyword-only payload on the exception, following
`LLMLaneDeadError` (`llm/client.py:41-53`) — never a message a caller string-matches. The catalog
is CLOSED: a condition it does not name is a defect in this file, not a new bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn


class ProjectionIssue(StrEnum):
    """Everything projection can refuse for. Closed."""

    # -- declaration ------------------------------------------------------------------
    DECLARATION_UNREADABLE = "declaration_unreadable"
    #: `projection.yaml` is absent. Distinct from DECLARATION_UNREADABLE because "you have not
    #: opted into projection" and "your declaration is corrupt" are different operator problems,
    #: and the availability catalog may not tell them apart by inspecting a message.
    DECLARATION_MISSING = "declaration_missing"
    MALFORMED_DECLARATION = "malformed_declaration"
    UNKNOWN_ENTRY_KIND = "unknown_entry_kind"
    DUPLICATE_ENTITY_ID = "duplicate_entity_id"
    #: An entry lists the same predicate twice in `bullet_predicates`, which would emit two bullets
    #: carrying one fact's id as their shared `bullet_id` — colliding in the downstream
    #: `bullet_id`-keyed maps and silently collapsing to one bullet.
    DUPLICATE_BULLET_PREDICATE = "duplicate_bullet_predicate"
    UNRESOLVED_PLACEHOLDER = "unresolved_placeholder"
    MALFORMED_PLACEHOLDER = "malformed_placeholder"
    MISSING_OPEN_RANGE_LABEL = "missing_open_range_label"
    # -- fallback ---------------------------------------------------------------------
    FALLBACK_ID_NOT_A_CANDIDATE = "fallback_id_not_a_candidate"
    FALLBACK_ID_DUPLICATED = "fallback_id_duplicated"
    FALLBACK_OVERLAPS_PINNED = "fallback_overlaps_pinned"
    # -- bundle -------------------------------------------------------------------------
    BUNDLE_UNREADABLE = "bundle_unreadable"
    # -- bundle references ------------------------------------------------------------
    UNKNOWN_BUNDLE_ID = "unknown_bundle_id"
    FACT_NOT_RESUME_SURFACED = "fact_not_resume_surfaced"
    FACT_NOT_EFFECTIVE = "fact_not_effective"
    FACT_EXPIRED = "fact_expired"
    FACT_VALUE_KIND_NOT_ADMITTED = "fact_value_kind_not_admitted"
    CLAIM_NOT_APPROVED = "claim_not_approved"
    CLAIM_NOT_RESUME_SURFACED = "claim_not_resume_surfaced"
    CLAIM_SUBJECT_MISMATCH = "claim_subject_mismatch"
    SKILL_NOT_RESUME_SURFACED = "skill_not_resume_surfaced"
    BULLET_TEXT_ALTERED = "bullet_text_altered"
    #: An entry declared a `bullet_predicates` entry that resolves to no résumé-surfaced fact on
    #: the entity. A silently bulletless entry would drop the owner's accomplishments into a
    #: document that becomes Tier A's ground truth, so a mistyped or empty predicate fails loudly.
    BULLET_PREDICATE_NO_FACTS = "bullet_predicate_no_facts"
    # -- shell ------------------------------------------------------------------------
    SHELL_SOURCE_UNREADABLE = "shell_source_unreadable"
    # -- persona ----------------------------------------------------------------------
    PERSONA_DECLARES_ENTRIES = "persona_declares_entries"
    # -- owner gate -------------------------------------------------------------------
    MISSING_PROJECTION_APPROVAL = "missing_projection_approval"
    #: The approval on file is for the right `projection_digest`, but the stamp's own
    #: `bundle_digest` no longer matches the bundle's CURRENT revision. The declaration the owner
    #: reviewed did not change, but the bundle facts it resolved against did — so the literal
    #: résumé text the owner approved may not be the text that would render today. Raised by
    #: `project_pool` itself, unconditionally, on every path that reaches it (D-167) — there is
    #: no opt-in flag gating this check.
    STALE_PROJECTION_APPROVAL = "stale_projection_approval"
    # -- selection --------------------------------------------------------------------
    PINNED_SET_EXCEEDS_BUDGET = "pinned_set_exceeds_budget"
    COMPILE_INFRASTRUCTURE_FAILURE = "compile_infrastructure_failure"
    NO_JD_EXTRACTION = "no_jd_extraction"
    # -- posting ------------------------------------------------------------------------
    POSTING_NOT_OPEN = "posting_not_open"
    POSTING_NO_CURRENT_VERSION = "posting_no_current_version"


@dataclass(frozen=True)
class ProjectionViolation:
    """One refusal. `where` locates it — a declaration line, a record id, or an option name."""

    issue: ProjectionIssue
    message: str
    where: str


class ProjectionError(Exception):
    """Base for every typed projection failure. Carries the violation, never just prose."""

    def __init__(self, violation: ProjectionViolation) -> None:
        super().__init__(f"{violation.issue}: {violation.message} ({violation.where})")
        self.violation = violation


def raise_violation(issue: ProjectionIssue, message: str, *, where: str) -> NoReturn:
    """The one construction site, so a caller cannot invent an untyped refusal."""
    raise ProjectionError(ProjectionViolation(issue=issue, message=message, where=where))
