"""Typed issue codes, validation tiers, outcome categories, and exceptions.

Every condition the design names gets a code here, and every code declares one tier. A code
with no declared tier would default to something in the report layer, and the thing it defaults
to is what decides whether `validate` exits 0 or 1 — so `ISSUE_TIERS` is total and a test
asserts it.

Three categories are kept strictly apart, because conflating them is how a check that never ran
gets read as a check that passed:

- **error** — the revision is invalid. Structural, referential, evidential, semantic, or digest.
- **blocker** — the revision is valid but a named record cannot be used downstream. Reported
  only when completeness is requested.
- **warning / information** — never change the exit code.

The exit contract (design §21) is scoped to the `profile-bundle` command family and deliberately
does not match `scan`/`run`, which use exit 2 for lock contention. A *state refusal* the operator
can act on is a finding (exit 1); a check that could not complete is exit 3.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, Literal, TypeVar

JsonScalar = str | int | bool | None
JsonValue = JsonScalar | Sequence["JsonValue"] | Mapping[str, "JsonValue"]

IssueTier = Literal["error", "blocker", "warning", "information"]
OutcomeCategory = Literal["clean", "findings", "usage_error", "could_not_complete"]

_TIER_RANK: Mapping[IssueTier, int] = {
    "error": 0,
    "blocker": 1,
    "warning": 2,
    "information": 3,
}

_CATEGORY_EXIT: Mapping[OutcomeCategory, int] = {
    "clean": 0,
    "findings": 1,
    "usage_error": 2,
    "could_not_complete": 3,
}


class IssueCode(StrEnum):
    """The closed catalog of everything Gate A can report.

    Grouped by validation layer so a new condition lands beside its neighbours instead of at the
    end, where a reviewer cannot see which layer owns it.
    """

    # -- structural -----------------------------------------------------------------
    INVALID_UTF8 = "invalid_utf8"
    INVALID_YAML = "invalid_yaml"
    RESTRICTED_YAML_VIOLATION = "restricted_yaml_violation"
    UNKNOWN_FILE = "unknown_file"
    MISSING_REQUIRED_FILE = "missing_required_file"
    SYMLINK_REFUSED = "symlink_refused"
    MODEL_VALIDATION_ERROR = "model_validation_error"
    WRONG_OWNING_FILE = "wrong_owning_file"
    BASENAME_ID_MISMATCH = "basename_id_mismatch"
    DUPLICATE_RECORD_ID = "duplicate_record_id"
    RECORD_KIND_MISMATCH = "record_kind_mismatch"
    CATALOG_VERSION_MISMATCH = "catalog_version_mismatch"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"

    # -- referential ----------------------------------------------------------------
    BROKEN_REFERENCE = "broken_reference"
    WRONG_REFERENCE_KIND = "wrong_reference_kind"
    EVIDENCE_LINK_ASYMMETRY = "evidence_link_asymmetry"
    SUPERSESSION_CYCLE = "supersession_cycle"
    CONFLICT_CANDIDATE_MISMATCH = "conflict_candidate_mismatch"
    ACTIVE_RULING_MISMATCH = "active_ruling_mismatch"
    RELATION_KIND_MISMATCH = "relation_kind_mismatch"
    DUPLICATE_APPROVAL_ID = "duplicate_approval_id"
    SOURCE_LEDGER_ORDER_MISMATCH = "source_ledger_order_mismatch"

    # -- evidence -------------------------------------------------------------------
    MISSING_BLOB = "missing_blob"
    BLOB_DIGEST_MISMATCH = "blob_digest_mismatch"
    SECRET_DETECTED = "secret_detected"
    SECRET_DETECTED_BY_STRONGER_RULESET = "secret_detected_by_stronger_ruleset"
    UNSUPPORTED_SECRET_SCAN_RULESET_VERSION = "unsupported_secret_scan_ruleset_version"
    SECRET_RULESET_ROWS_DIVERGED = "secret_ruleset_rows_diverged"
    PROHIBITED_MEDIA_TYPE = "prohibited_media_type"
    CAPTURE_TOO_LARGE = "capture_too_large"
    EVIDENCE_BUDGET_EXCEEDED = "evidence_budget_exceeded"
    ABSOLUTE_PERSONAL_PATH = "absolute_personal_path"
    REDACTION_INVALID = "redaction_invalid"
    EVIDENCE_CLASS_CONTRACT_UNMET = "evidence_class_contract_unmet"
    EVIDENCE_CONTRACT_UNMET = "evidence_contract_unmet"
    VERIFICATION_BASIS_UNSUPPORTED = "verification_basis_unsupported"
    CONTRADICTION_WITHOUT_RULING = "contradiction_without_ruling"
    CONTEXTUAL_EVIDENCE_NOT_SUPPORT = "contextual_evidence_not_support"
    EVIDENCE_UNREVIEWED = "evidence_unreviewed"

    # -- semantic -------------------------------------------------------------------
    UNKNOWN_PREDICATE = "unknown_predicate"
    PREDICATE_SUBJECT_KIND_ILLEGAL = "predicate_subject_kind_illegal"
    PREDICATE_VALUE_TYPE_ILLEGAL = "predicate_value_type_illegal"
    PREDICATE_CARDINALITY_EXCEEDED = "predicate_cardinality_exceeded"
    PREDICATE_EXCLUSIVITY_VIOLATED = "predicate_exclusivity_violated"
    PREDICATE_CONTEXT_ILLEGAL = "predicate_context_illegal"
    PREDICATE_SURFACE_ILLEGAL = "predicate_surface_illegal"
    SURFACE_POLICY_VIOLATED = "surface_policy_violated"
    OWNER_ATTESTATION_NOT_PERMITTED = "owner_attestation_not_permitted"
    ENTITY_STATUS_ILLEGAL = "entity_status_illegal"
    FACT_STATE_INCONSISTENT = "fact_state_inconsistent"
    COMPETING_VALUES_OUTSIDE_CONFLICT = "competing_values_outside_conflict"
    APPLICATION_ONLY_LEAK = "application_only_leak"
    SKILL_SURFACE_UNSUPPORTED = "skill_surface_unsupported"
    SKILL_UNSUPPORTED = "skill_unsupported"
    UNKNOWN_SKILL_CATEGORY = "unknown_skill_category"
    METRIC_UNIT_UNKNOWN = "metric_unit_unknown"
    METRIC_UNIT_KIND_MISMATCH = "metric_unit_kind_mismatch"
    METRIC_PHRASING_MISSING = "metric_phrasing_missing"
    METRIC_FORBIDDEN_PHRASING = "metric_forbidden_phrasing"
    METRIC_PROTECTED_TOKEN_MISSING = "metric_protected_token_missing"
    METRIC_DISQUALIFYING_CAVEAT = "metric_disqualifying_caveat"
    UNKNOWN_ASSERTION_TAG = "unknown_assertion_tag"
    ASSERTION_TAG_SUBJECT_ILLEGAL = "assertion_tag_subject_illegal"
    ASSERTION_TAG_UNAUTHORIZED = "assertion_tag_unauthorized"
    CLAIM_WITHOUT_FACTS = "claim_without_facts"
    CLAIM_FACT_INELIGIBLE = "claim_fact_ineligible"
    CLAIM_SURFACE_UNSUPPORTED = "claim_surface_unsupported"
    CLAIM_UNTRACEABLE_FIGURE = "claim_untraceable_figure"
    CLAIM_METRIC_MENTION_MISSING = "claim_metric_mention_missing"
    CLAIM_PROTECTED_TOKEN_DROPPED = "claim_protected_token_dropped"

    # -- owner gates, history, imports ---------------------------------------------
    MISSING_OWNER_APPROVAL = "missing_owner_approval"
    APPROVAL_TARGET_DIGEST_MISMATCH = "approval_target_digest_mismatch"
    APPROVAL_RESULT_STATE_MISMATCH = "approval_result_state_mismatch"
    APPROVAL_ENTRY_UNEXPECTED = "approval_entry_unexpected"
    RULING_AUTHORIZATION_MISSING = "ruling_authorization_missing"
    LEDGER_PREFIX_CHANGED = "ledger_prefix_changed"
    CHANGE_LEDGER_LENGTH_MISMATCH = "change_ledger_length_mismatch"
    CHANGE_ENTRY_MISMATCH = "change_entry_mismatch"
    APPROVAL_STAMP_COUNT_MISMATCH = "approval_stamp_count_mismatch"
    IMPORT_DENOMINATOR_MISMATCH = "import_denominator_mismatch"
    IMPORT_MISSING_CANDIDATE = "import_missing_candidate"
    IMPORT_MISSING_EXCLUSION = "import_missing_exclusion"
    IMPORT_DUPLICATE_RECORD = "import_duplicate_record"
    IMPORT_ENUMERATOR_MISMATCH = "import_enumerator_mismatch"
    IMPORT_SCOPE_INVALID = "import_scope_invalid"
    IMPORT_RECORD_UNDISPOSITIONED = "import_record_undispositioned"
    IMPORT_UNEXPLAINED_RECORD = "import_unexplained_record"
    IMPORT_CANDIDATE_IDENTITY_MISMATCH = "import_candidate_identity_mismatch"

    # -- digest and history identity -----------------------------------------------
    BUNDLE_DIGEST_MISMATCH = "bundle_digest_mismatch"
    EVIDENCE_SET_DIGEST_MISMATCH = "evidence_set_digest_mismatch"
    CANDIDATE_DIGEST_MISMATCH = "candidate_digest_mismatch"
    #: Information, not a finding about the revision: the run could not recompute a candidate
    #: digest, so the approval-to-content comparison did not happen. Its absence is what made an
    #: unmeasured revision indistinguishable from a verified one in both renderings.
    CANDIDATE_DIGEST_UNVERIFIED = "candidate_digest_unverified"
    CURRENT_POINTER_MISMATCH = "current_pointer_mismatch"
    COMPLETE_MARKER_MISSING = "complete_marker_missing"
    MANIFEST_DIRECTORY_MISMATCH = "manifest_directory_mismatch"
    DRAFT_MANIFEST_INVALID = "draft_manifest_invalid"
    UNVERIFIABLE_ANCESTOR = "unverifiable_ancestor"

    # -- completeness ---------------------------------------------------------------
    #
    # Three of §20.5's "required profile field" clauses have no code here, deliberately (D-115):
    # `IdentityDocument.person` is one required field, every entity kind that §9 gives a status
    # declares it as a required closed enum, and a metric's `reviewed_at` is a required `date` while
    # `review_interval_days` belongs to a predicate a metric does not have. Each condition is
    # unrepresentable rather than unchecked, so a code for it could never fire and would read as
    # coverage. `tests/profile_bundle/test_profile_bundle_completeness.py` names where each of the
    # three guarantees actually lands.
    MISSING_CONTACT_CHANNEL = "missing_contact_channel"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    STALE_FACT = "stale_fact"
    EXPIRED_REVIEW = "expired_review"
    FACT_VALUE_EXPIRED = "fact_value_expired"
    MISSING_REVIEW_STATE = "missing_review_state"
    COMPLETENESS_COUNTS = "completeness_counts"
    ORPHANED_ARTEFACT = "orphaned_artefact"
    CORRUPT_BLOB_QUARANTINE = "corrupt_blob_quarantine"

    # -- operations -----------------------------------------------------------------
    BUNDLE_LOCK_HELD = "bundle_lock_held"
    STALE_DRAFT_PARENT = "stale_draft_parent"
    DRAFT_REBASE_CONFLICT = "draft_rebase_conflict"
    DRAFT_BACKUP_CONFLICT = "draft_backup_conflict"
    PROMOTION_TARGET_CONFLICT = "promotion_target_conflict"
    MISSING_APPROVAL_STAMP = "missing_approval_stamp"
    STALE_APPROVAL_STAMP = "stale_approval_stamp"
    DRAFT_NOT_FOUND = "draft_not_found"
    DRAFT_ALREADY_EXISTS = "draft_already_exists"
    CURRENT_ALREADY_EXISTS = "current_already_exists"
    NO_CURRENT_REVISION = "no_current_revision"
    RECORD_NOT_FOUND = "record_not_found"
    APPROVAL_REQUIRES_CONTROLLING_TTY = "approval_requires_controlling_tty"
    APPROVAL_DECLINED = "approval_declined"
    IO_ERROR = "io_error"
    INTERNAL_ERROR = "internal_error"


#: Codes reported as completeness blockers: the revision stays valid, the record is unusable.
_BLOCKER_CODES: frozenset[IssueCode] = frozenset(
    {
        IssueCode.EVIDENCE_UNREVIEWED,
        IssueCode.SECRET_DETECTED_BY_STRONGER_RULESET,
        IssueCode.METRIC_DISQUALIFYING_CAVEAT,
        IssueCode.IMPORT_RECORD_UNDISPOSITIONED,
        IssueCode.IMPORT_UNEXPLAINED_RECORD,
        IssueCode.UNVERIFIABLE_ANCESTOR,
        IssueCode.MISSING_CONTACT_CHANNEL,
        IssueCode.UNRESOLVED_CONFLICT,
        IssueCode.STALE_FACT,
        IssueCode.EXPIRED_REVIEW,
        IssueCode.FACT_VALUE_EXPIRED,
        IssueCode.MISSING_REVIEW_STATE,
        IssueCode.CORRUPT_BLOB_QUARANTINE,
    }
)

#: Codes that are reports about the bundle root, a run's own arithmetic, or what a run did not
#: measure — never about the selected revision's validity. `completeness_counts` is here rather than
#: in `_BLOCKER_CODES` because §20.5 puts counts, surfaces, status distribution and evidence
#: coverage in the `information` tier: a run whose only finding is a count is a clean run, and
#: giving it any other tier would make every complete bundle exit 1. `candidate_digest_unverified`
#: is here for the same reason from the other direction — §21 keeps a revision valid when its
#: ancestry is unavailable, so naming the comparison that did not happen must not change the exit
#: code, only make the gap visible.
_INFORMATION_CODES: frozenset[IssueCode] = frozenset(
    {
        IssueCode.ORPHANED_ARTEFACT,
        IssueCode.COMPLETENESS_COUNTS,
        IssueCode.CANDIDATE_DIGEST_UNVERIFIED,
    }
)

#: Typed state refusals: the check completed and the operator has an action. Exit 1.
STATE_REFUSAL_CODES: frozenset[IssueCode] = frozenset(
    {
        IssueCode.STALE_DRAFT_PARENT,
        IssueCode.DRAFT_REBASE_CONFLICT,
        IssueCode.DRAFT_BACKUP_CONFLICT,
        IssueCode.MISSING_APPROVAL_STAMP,
        IssueCode.STALE_APPROVAL_STAMP,
        IssueCode.DRAFT_NOT_FOUND,
        IssueCode.DRAFT_ALREADY_EXISTS,
        IssueCode.CURRENT_ALREADY_EXISTS,
        IssueCode.NO_CURRENT_REVISION,
        IssueCode.RECORD_NOT_FOUND,
        IssueCode.APPROVAL_REQUIRES_CONTROLLING_TTY,
        IssueCode.APPROVAL_DECLINED,
    }
)

#: The check could not run at all: I/O, contention, internal failure, unsupported input. Exit 3.
COULD_NOT_COMPLETE_CODES: frozenset[IssueCode] = frozenset(
    {
        IssueCode.BUNDLE_LOCK_HELD,
        IssueCode.PROMOTION_TARGET_CONFLICT,
        IssueCode.UNSUPPORTED_SCHEMA_VERSION,
        IssueCode.UNSUPPORTED_SECRET_SCAN_RULESET_VERSION,
        IssueCode.IO_ERROR,
        IssueCode.INTERNAL_ERROR,
    }
)


def tier_of(code: IssueCode) -> IssueTier:
    """The declared tier for `code`. Total over `IssueCode` by construction."""
    if code in _INFORMATION_CODES:
        return "information"
    if code in _BLOCKER_CODES:
        return "blocker"
    return "error"


def exit_code_for_category(category: OutcomeCategory) -> int:
    return _CATEGORY_EXIT[category]


@dataclass(frozen=True)
class Diagnostic:
    """One finding. `details` carries machine-readable context, never captured bytes.

    A diagnostic is rendered into JSON that an operator may paste into a bug report, so no
    contact value, evidence capture, or matched secret text may appear in `message` or
    `details`. Record IDs and byte ranges are enough to locate the problem in the bundle.
    """

    tier: IssueTier
    code: str
    path: str | None
    record_id: str | None
    message: str
    details: Mapping[str, JsonValue] = field(default_factory=dict)

    def sort_key(self) -> tuple[int, str, str, str, str]:
        return (
            _TIER_RANK[self.tier],
            self.code,
            self.path or "",
            self.record_id or "",
            self.message,
        )


def diagnostic(
    code: IssueCode,
    message: str,
    *,
    path: str | None = None,
    record_id: str | None = None,
    tier: IssueTier | None = None,
    **details: JsonValue,
) -> Diagnostic:
    """Build a diagnostic whose tier comes from the code unless deliberately overridden.

    The override exists for exactly one legitimate case: a condition that is an error during
    promotion and a blocker during read-only completeness (a broken ancestor, say). Everything
    else takes the declared tier, so a caller cannot quietly downgrade an error.
    """
    return Diagnostic(
        tier=tier if tier is not None else tier_of(code),
        code=str(code),
        path=path,
        record_id=record_id,
        message=message,
        details=dict(details),
    )


T = TypeVar("T")


@dataclass(frozen=True)
class OperationOutcome(Generic[T]):
    """A completed operation, its findings, and the exit code they imply."""

    category: OutcomeCategory
    value: T | None
    diagnostics: tuple[Diagnostic, ...]
    exit_code: int

    @classmethod
    def clean(cls, value: T) -> OperationOutcome[T]:
        return cls(category="clean", value=value, diagnostics=(), exit_code=0)

    @classmethod
    def from_diagnostics(
        cls, value: T | None, diagnostics: Sequence[Diagnostic]
    ) -> OperationOutcome[T]:
        """`clean` unless an error or blocker is present. Warnings never change the exit code."""
        ordered = tuple(sorted(diagnostics, key=lambda d: d.sort_key()))
        category: OutcomeCategory = (
            "findings" if any(d.tier in ("error", "blocker") for d in ordered) else "clean"
        )
        return cls(
            category=category,
            value=value,
            diagnostics=ordered,
            exit_code=_CATEGORY_EXIT[category],
        )


def outcome_with(
    value: T | None, diagnostics: Sequence[Diagnostic]
) -> OperationOutcome[T]:
    """`OperationOutcome.from_diagnostics`, with §21's could-not-complete precedence applied.

    A run that could not read the bundle has not found one error, it has found nothing at all, so
    reporting exit 1 would let a caller treat an unreadable bundle as a bundle with a small problem.
    One definition, used by every command and by the validation report, because two places
    implementing the same precedence is two places for it to drift.
    """
    if any(finding.code in COULD_NOT_COMPLETE_CODES for finding in diagnostics):
        return OperationOutcome(
            category="could_not_complete",
            value=value,
            diagnostics=tuple(sorted(diagnostics, key=lambda d: d.sort_key())),
            exit_code=_CATEGORY_EXIT["could_not_complete"],
        )
    return OperationOutcome.from_diagnostics(value, diagnostics)


def outcome_for(code: IssueCode, message: str | None = None, **details: JsonValue) -> (
    OperationOutcome[None]
):
    """The single-code refusal outcome, categorised from the code alone.

    `STATE_REFUSAL_CODES` and `COULD_NOT_COMPLETE_CODES` are disjoint (a test asserts it), so
    this mapping is not order-dependent. Any other code reaching here is a finding, because it
    is a validation result rather than an operational refusal.
    """
    category: OutcomeCategory = (
        "could_not_complete" if code in COULD_NOT_COMPLETE_CODES else "findings"
    )
    return OperationOutcome(
        category=category,
        value=None,
        diagnostics=(
            Diagnostic(
                tier="error",
                code=str(code),
                path=None,
                record_id=None,
                message=message or _default_message(code),
                details=dict(details),
            ),
        ),
        exit_code=_CATEGORY_EXIT[category],
    )


def _default_message(code: IssueCode) -> str:
    return str(code).replace("_", " ")


def io_reason(exc: OSError) -> str:
    """Why an I/O operation failed, without the absolute path a stringified `OSError` carries.

    A diagnostic is rendered into JSON an operator may paste elsewhere, and every path in this
    package's diagnostics is a logical one — an absolute `$HOME` path is neither theirs to publish
    nor the same on the next machine. The caller has already named the logical path it was working
    on, so only the reason is missing.
    """
    return exc.strerror or type(exc).__name__


class ProfileBundleError(Exception):
    """Base for every typed failure this package raises across a module boundary."""


class BundlePathError(ProfileBundleError):
    """A path could not be constructed inside the bundle root, or a digest was malformed."""


class RestrictedYamlError(ProfileBundleError):
    """A document violated the restricted-YAML authoring contract."""

    def __init__(self, code: IssueCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class BundleLayoutError(ProfileBundleError):
    """A file is outside the closed logical grammar, or in the wrong owning file."""


class BundleIoError(ProfileBundleError):
    """The bundle could not be read or written. Always `could_not_complete`."""


class UnsupportedSchemaVersionError(ProfileBundleError):
    """The bundle declares a schema version this build does not support."""

    def __init__(self, found: int, supported: Sequence[int]) -> None:
        super().__init__(
            f"bundle schema version {found} is not supported (supported: {sorted(supported)})"
        )
        self.found = found
        self.supported = tuple(sorted(supported))


class UnsupportedSecretRulesetError(ProfileBundleError):
    """A revision records a secret-scan ruleset version this build does not retain."""

    def __init__(self, found: int, supported: Sequence[int]) -> None:
        super().__init__(
            f"secret-scan ruleset version {found} is unavailable "
            f"(available: {sorted(supported)}); refusing to report a clean scan"
        )
        self.found = found
        self.supported = tuple(sorted(supported))
