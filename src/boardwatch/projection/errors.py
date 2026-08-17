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
    #: `COMPILE_FAILED` while compiling a prefix that includes a CANDIDATE entry, when the same
    #: document WITHOUT that candidate compiled `OK` moments earlier. The failure is therefore
    #: ATTRIBUTABLE to that one entry, which is the whole of the claim — this member does not assert
    #: a cause. `CompileReason.COMPILE_FAILED` folds a non-zero `tectonic` exit, a missing PDF and
    #: an unreadable page count into one value, and `reports/resume_gate.py:87-90` reasons such an
    #: exit is typically ENVIRONMENTAL (cold support-file cache with no network, disk full, OOM,
    #: killed subprocess), so nothing typed anywhere distinguishes content from environment.
    #: Attribution is what is observable; the cause is not.
    #: Distinct from COMPILE_INFRASTRUCTURE_FAILURE, which means the toolchain is absent (typed
    #: separately at the source as `BINARY_MISSING`) or the gate reason is unclassified. Folding
    #: them reported "toolchain unavailable" for a working tectonic. Split at the raise site
    #: (`select._fatal_if_infrastructure`), not downstream: telling the two call sites apart later
    #: would mean re-reading a compile log.
    CANDIDATE_COMPILE_FAILED = "candidate_compile_failed"
    #: `COMPILE_FAILED` on the PINNED-ONLY prefix, before any candidate exists. Nothing can be
    #: attributed: no smaller prefix has compiled, so the environment and the pinned content are
    #: equally implicated, and either way the pinned set comes from the frozen declaration and the
    #: cause is run-invariant. Its own member rather than COMPILE_INFRASTRUCTURE_FAILURE because
    #: that one resolves to `TOOLCHAIN_UNAVAILABLE`, and telling an operator to reinstall a working
    #: tectonic is the exact misdiagnosis this split exists to remove — the remedy here is to read
    #: the compile log, then look at the pinned entries.
    PINNED_SET_COMPILE_FAILED = "pinned_set_compile_failed"
    NO_JD_EXTRACTION = "no_jd_extraction"
    # -- posting ------------------------------------------------------------------------
    POSTING_NOT_OPEN = "posting_not_open"
    POSTING_NO_CURRENT_VERSION = "posting_no_current_version"
    # -- run configuration --------------------------------------------------------------
    #: The `scorer_id` a run asked for is not in `SCORERS`. A misconfiguration of the run itself,
    #: distinct from every declaration and bundle member above: nothing about the owner's data is
    #: wrong, so an unattended caller must be able to tell "your config names a scorer that does
    #: not exist" from "your bundle cannot be read" without inspecting a message.
    UNKNOWN_SCORER = "unknown_scorer"


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
