"""Import validation: the ledger's arithmetic, its scopes, and its derived identity (§18, §20).

This layer owns only what the models cannot see. A great deal of §18 is already enforced at parse
time and is deliberately not re-checked here, because a check that cannot fire reads as coverage
while providing none:

- `SourceLedger` already refuses a duplicate `source_record_id`, a record naming an unenumerated
  source, and any disagreement between `sources[].source_record_ids` and the records themselves —
  including order;
- `SourceLedgerRecord` already refuses `imported` with no candidate and a non-imported record that
  names one;
- `ExclusionLedger` already refuses two exclusions for one record;
- `validate_referential` already resolves candidate, exclusion, and record cross-references.

What is left needs two documents at once or a recomputation:

- `policy/sources.yaml` is authoritative for `source_kind`, and only it can say whether the ledger
  named the right enumerator and the right kind of approved scope;
- a record's identity is *derived*, so it can be recomputed and compared, which is the one check
  that makes "the importer, not the LLM, assigns identity" observable in a hand-edited bundle;
- the exclusion document's totals must reconcile with the ledger's `excluded` count, because Gate B
  reports both and a disagreement means one of the two numbers is wrong.

`owner_excluded` approval gating is *not* re-implemented here. It is derived in `approvals.py` and
enforced by `validate_history`, which binds it to the promotion diff and the target-content digest;
a second copy would report the same missing approval twice and could disagree about the digest.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from boardwatch.profile_bundle.enumerators import (
    ROOT_SEGMENT,
    SOURCE_KIND_ADAPTERS,
    derive_source_record_id,
    enumerator_for,
    is_normalized_locator,
    is_resolved_heading_path,
)
from boardwatch.profile_bundle.errors import Diagnostic, IssueCode, diagnostic
from boardwatch.profile_bundle.imports import (
    CandidateImportError,
    canonicalize_candidate_value,
    derive_candidate_id,
    uncanonical_value,
)
from boardwatch.profile_bundle.models.imports import (
    Disposition,
    ExclusionLedger,
    ExclusionReason,
    ExtractionReport,
    SourceLedger,
    SourceLedgerSource,
)
from boardwatch.profile_bundle.validation.context import ValidationContext

LEDGER_PATH = "imports/source-ledger.yaml"
EXCLUSIONS_PATH = "imports/exclusions.yaml"
CANDIDATES_PATH = "imports/candidates.yaml"
SOURCES_PATH = "policy/sources.yaml"
EXTRACTION_REPORT_PATH = "imports/extraction-report.yaml"


@dataclass(frozen=True)
class ImportTotals:
    """The Gate B measurement packet's numbers, derived from the two documents that own them."""

    denominator: int
    imported: int
    excluded: int
    review_required: int
    exclusions_by_reason: Mapping[ExclusionReason, int]

    @property
    def dispositioned(self) -> int:
        return self.imported + self.excluded + self.review_required


def import_totals(ledger: SourceLedger, exclusions: ExclusionLedger | None) -> ImportTotals:
    """`record_count` and its three parts, plus exclusion totals by closed reason."""
    counts = ledger.counts_by_disposition()
    return ImportTotals(
        denominator=ledger.record_count,
        imported=counts[Disposition.IMPORTED],
        excluded=counts[Disposition.EXCLUDED],
        review_required=counts[Disposition.REVIEW_REQUIRED],
        exclusions_by_reason=(
            exclusions.counts_by_reason()
            if exclusions is not None
            else dict.fromkeys(ExclusionReason, 0)
        ),
    )


def validate_imports(ctx: ValidationContext) -> tuple[Diagnostic, ...]:
    """Every import finding that makes the revision invalid (§18, §20)."""
    if ctx.index.source_ledger is None:
        return ()
    return tuple(
        finding
        for check in (
            _enumerators_pair_with_their_source_kind,
            _approved_scopes_match_the_source_kind,
            _record_identity_is_the_derived_one,
            _record_locators_are_shapes_their_adapter_can_emit,
            _candidate_identity_is_the_derived_one,
            _one_record_per_logical_unit,
            _dispositions_agree_with_the_exclusion_document,
            _imported_records_name_their_own_candidates,
            _every_candidate_is_named_by_its_record,
        )
        for finding in check(ctx)
    )


def imports_completeness(ctx: ValidationContext) -> tuple[Diagnostic, ...]:
    """Import completeness blockers: the revision is valid, the material is not usable yet."""
    if ctx.index.source_ledger is None:
        return ()
    return tuple(
        finding
        for check in (
            _undispositioned_records,
            _approved_sources_that_were_never_enumerated,
            _the_extraction_report_reconciles_with_dispositions,
        )
        for finding in check(ctx)
    )


# --------------------------------------------------------------------------------------
# The closed source-kind / adapter pairing (§18)
# --------------------------------------------------------------------------------------


def _enumerators_pair_with_their_source_kind(ctx: ValidationContext) -> Iterator[Diagnostic]:
    ledger = ctx.index.source_ledger
    assert ledger is not None
    catalogued = ctx.index.sources.by_id if ctx.index.sources is not None else {}

    for source in ledger.sources:
        spec = catalogued.get(source.source_id)
        if spec is None:
            yield diagnostic(
                IssueCode.IMPORT_ENUMERATOR_MISMATCH,
                f"{source.source_id} is enumerated but {SOURCES_PATH} does not declare it, so its "
                "source kind and approved enumerator cannot be checked",
                path=LEDGER_PATH,
                record_id=source.source_id,
            )
            continue
        binding = SOURCE_KIND_ADAPTERS[spec.source_kind]
        if (source.enumerator_id, source.enumerator_version) != (
            binding.enumerator_id,
            binding.enumerator_version,
        ):
            yield diagnostic(
                IssueCode.IMPORT_ENUMERATOR_MISMATCH,
                f"{source.source_id}: source kind {spec.source_kind.value} pairs with "
                f"{binding.enumerator_id} v{binding.enumerator_version}, not "
                f"{source.enumerator_id} v{source.enumerator_version}",
                path=LEDGER_PATH,
                record_id=source.source_id,
                expected=f"{binding.enumerator_id}@{binding.enumerator_version}",
            )


def _approved_scopes_match_the_source_kind(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """The discriminant is fixed by the source kind, and widening it costs a new owner approval.

    §18 allows `complete_file` for the first three kinds and `selected_sections` for repository
    Markdown, and nothing else. A repository source silently carrying `complete_file` would import
    an entire checkout under an approval the owner gave for two sections.
    """
    ledger = ctx.index.source_ledger
    assert ledger is not None
    catalogued = ctx.index.sources.by_id if ctx.index.sources is not None else {}

    for source in ledger.sources:
        spec = catalogued.get(source.source_id)
        if spec is None:
            continue
        expected = SOURCE_KIND_ADAPTERS[spec.source_kind].scope_kind
        if source.approved_scope.kind != expected:
            yield diagnostic(
                IssueCode.IMPORT_SCOPE_INVALID,
                f"{source.source_id}: source kind {spec.source_kind.value} is approved with a "
                f"{expected} scope, not {source.approved_scope.kind}",
                path=LEDGER_PATH,
                record_id=source.source_id,
                expected=expected,
            )
            continue
        if source.approved_scope.kind != "selected_sections":
            continue
        for locator in source.approved_scope.locators:
            # ONE check, asking the emitter's own question: is this a path a heading stack can
            # resolve to? It used to be two — "is it normalized?" and "is it `_root`?" — and
            # neither of them refused a section deeper than Markdown can nest, so a scope could
            # name a shape no enumeration produces. Validation has to agree with the adapter here,
            # or a bundle validates clean and then cannot be re-enumerated from its own source.
            #
            # The `_root` half is only sound because `_root` is RESERVED by the encoder. It was
            # added before the reservation was, and a heading literally named `_root` then
            # resolved to `_root` as well — so the refusal made that legitimate source
            # unimportable, which is the defect class it was written to prevent. Such a heading
            # now resolves to `%5Froot`.
            if is_resolved_heading_path(locator):
                continue
            reason = (
                "names pre-heading content, which no selected section can contain"
                if locator == ROOT_SEGMENT or locator.startswith(f"{ROOT_SEGMENT}/")
                else "is not a resolved heading path, so no enumeration can produce it"
            )
            yield diagnostic(
                IssueCode.IMPORT_SCOPE_INVALID,
                f"{source.source_id}: selected-section locator {locator!r} {reason}",
                path=LEDGER_PATH,
                record_id=source.source_id,
                locator=locator,
            )
        yield from _records_lie_inside_their_approved_scope(ctx, source)


# --------------------------------------------------------------------------------------
# Derived identity and the denominator (§18)
# --------------------------------------------------------------------------------------


def _record_identity_is_the_derived_one(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """A ledger record must carry a normalized locator and the ID that locator derives."""
    for record in ctx.index.ledger_records:
        if not is_normalized_locator(record.normalized_locator):
            yield diagnostic(
                IssueCode.IMPORT_ENUMERATOR_MISMATCH,
                f"{record.source_record_id}: locator {record.normalized_locator!r} is not "
                "normalized, so no adapter produced it",
                path=LEDGER_PATH,
                record_id=record.source_record_id,
                locator=record.normalized_locator,
            )
            continue
        derived = derive_source_record_id(record.source_id, record.normalized_locator)
        if derived != record.source_record_id:
            yield diagnostic(
                IssueCode.IMPORT_ENUMERATOR_MISMATCH,
                f"{record.source_record_id} is not the ID its source and locator derive; the "
                "importer assigns identity, so the denominator has been renumbered",
                path=LEDGER_PATH,
                record_id=record.source_record_id,
                expected=derived,
            )


def _candidate_identity_is_the_derived_one(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """A stored candidate must be one the importer could have produced.

    Three things, in order, because each depends on the last: the predicate must exist in this
    revision's own catalog; the stored value must already be the canonical form that catalog
    authorizes; and the ID must be the digest those two derive. A forged
    `candidate.ffff…` is otherwise invisible — every other layer only checks that references
    resolve, so an arbitrary identity reaches promotion and every later slice trusts it.
    """
    catalog = ctx.index.predicates.by_id if ctx.index.predicates is not None else {}
    for candidate in ctx.index.candidates:
        spec = catalog.get(candidate.predicate)
        if spec is None:
            yield diagnostic(
                IssueCode.UNKNOWN_PREDICATE,
                f"{candidate.candidate_id} asserts {candidate.predicate!r}, which "
                "policy/predicates.yaml does not define",
                path=CANDIDATES_PATH,
                record_id=candidate.candidate_id,
                predicate=candidate.predicate,
            )
            continue

        violation = uncanonical_value(candidate.canonicalized_typed_value)
        if violation is None:
            try:
                canonical = canonicalize_candidate_value(candidate.canonicalized_typed_value, spec)
            except CandidateImportError as exc:
                violation = str(exc)
            else:
                if canonical != candidate.canonicalized_typed_value:
                    violation = "stored value is not the canonical form its predicate authorizes"
        if violation is not None:
            yield diagnostic(
                IssueCode.IMPORT_CANDIDATE_IDENTITY_MISMATCH,
                f"{candidate.candidate_id}: {violation}",
                path=CANDIDATES_PATH,
                record_id=candidate.candidate_id,
            )
            continue

        derived = derive_candidate_id(
            candidate.source_record_id, candidate.predicate, candidate.canonicalized_typed_value
        )
        if derived != candidate.candidate_id:
            yield diagnostic(
                IssueCode.IMPORT_CANDIDATE_IDENTITY_MISMATCH,
                f"{candidate.candidate_id} is not the ID its record, predicate, and value derive; "
                "the importer assigns identity, so this candidate was not produced by one",
                path=CANDIDATES_PATH,
                record_id=candidate.candidate_id,
                expected=derived,
            )


def _records_lie_inside_their_approved_scope(
    ctx: ValidationContext, source: SourceLedgerSource
) -> Iterator[Diagnostic]:
    """Every record of a selected-sections source must sit inside one of its approved sections.

    §18 binds a repository approval to "the ledger's exact scope object", and an approval that does
    not constrain which records may appear constrains nothing: the scope could name one section
    while the records enumerate an entire checkout. This needs no source bytes — the scope and the
    record locators are both in the ledger.
    """
    if source.approved_scope.kind != "selected_sections":
        return
    sections = source.approved_scope.locators
    for record in ctx.index.ledger_records:
        if record.source_id != source.source_id:
            continue
        if any(
            record.normalized_locator == section
            or record.normalized_locator.startswith(f"{section}/")
            for section in sections
        ):
            continue
        yield diagnostic(
            IssueCode.IMPORT_SCOPE_INVALID,
            f"{record.source_record_id} enumerates {record.normalized_locator!r}, which lies "
            f"outside every section {source.source_id} is approved for",
            path=LEDGER_PATH,
            record_id=record.source_record_id,
            locator=record.normalized_locator,
        )


def _every_candidate_is_named_by_its_record(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """A candidate its own record does not name is counted nowhere.

    The ledger model refuses a non-imported record that names a candidate, and the ownership check
    only walks imported records, so a candidate hanging off a `review_required` record falls
    between the two: it exists, it derives correctly, and it is in no denominator.
    """
    named = {
        candidate_id
        for record in ctx.index.ledger_records
        for candidate_id in record.candidate_ids
    }
    known_records = {record.source_record_id for record in ctx.index.ledger_records}
    for candidate in ctx.index.candidates:
        if candidate.candidate_id in named:
            continue
        # A candidate naming a record the ledger does not define is `validate_referential`'s
        # finding, not a second report here.
        if candidate.source_record_id not in known_records:
            continue
        yield diagnostic(
            IssueCode.IMPORT_MISSING_CANDIDATE,
            f"{candidate.candidate_id} is defined but {candidate.source_record_id} does not name "
            "it, so it belongs to no disposition",
            path=CANDIDATES_PATH,
            record_id=candidate.candidate_id,
            source_record_id=candidate.source_record_id,
        )


def _record_locators_are_shapes_their_adapter_can_emit(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """A locator no adapter could have emitted is a hand-written record in the denominator.

    An earlier review finding was declined on the grounds that "could this adapter have emitted
    this locator?" needs the source bytes. Half of it does — which heading or key exists is a fact
    about the file. The other half does not: each adapter emits a closed set of SHAPES, and a
    locator matching none of them could not have come from any enumeration of any source. Checking
    the byte-free half also closes the relabelling forgery, where a source's kind and enumerator
    are both changed and every record it owns is silently reinterpreted under a different grammar.
    """
    catalog = ctx.index.sources
    if catalog is None:
        return
    for record in ctx.index.ledger_records:
        spec = catalog.by_id.get(record.source_id)
        if spec is None:
            # An unknown source is `validate_referential`'s finding, not a second report here.
            continue
        adapter = enumerator_for(spec.source_kind, source_id=record.source_id)
        if adapter.emits_locator(record.normalized_locator):
            continue
        yield diagnostic(
            IssueCode.IMPORT_ENUMERATOR_MISMATCH,
            f"{record.source_record_id}: {record.normalized_locator!r} is not a shape "
            f"{adapter.id} can emit, so no enumeration of {record.source_id} produced it",
            path=LEDGER_PATH,
            record_id=record.source_record_id,
            locator=record.normalized_locator,
            enumerator_id=adapter.id,
        )


def _one_record_per_logical_unit(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Two records for one `(source, locator)` pair count one unit twice.

    The model refuses a duplicate `source_record_id`; it cannot refuse two different IDs standing
    for the same logical unit, which is the shape a hand-edited ledger actually takes.
    """
    seen: dict[tuple[str, str], str] = {}
    for record in ctx.index.ledger_records:
        key = (record.source_id, record.normalized_locator)
        first = seen.get(key)
        if first is None:
            seen[key] = record.source_record_id
            continue
        yield diagnostic(
            IssueCode.IMPORT_DUPLICATE_RECORD,
            f"{record.source_record_id} and {first} both enumerate "
            f"{record.normalized_locator!r} of {record.source_id}",
            path=LEDGER_PATH,
            record_id=record.source_record_id,
            duplicate_of=first,
        )


def _dispositions_agree_with_the_exclusion_document(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """Every `excluded` record has an exclusion, and the two documents' totals reconcile."""
    ledger = ctx.index.source_ledger
    assert ledger is not None
    excluded_records = {
        record.source_record_id
        for record in ctx.index.ledger_records
        if record.disposition is Disposition.EXCLUDED
    }
    excused = {exclusion.source_record_id for exclusion in ctx.index.exclusions}

    for record_id in sorted(excluded_records - excused):
        yield diagnostic(
            IssueCode.IMPORT_MISSING_EXCLUSION,
            f"{record_id} is dispositioned excluded but {EXCLUSIONS_PATH} gives no reason",
            path=LEDGER_PATH,
            record_id=record_id,
        )
    for record_id in sorted(excused - excluded_records):
        yield diagnostic(
            IssueCode.IMPORT_MISSING_EXCLUSION,
            f"{record_id} is excluded in {EXCLUSIONS_PATH} but its ledger disposition is not "
            "`excluded`, so the exclusion-by-reason totals overcount",
            path=EXCLUSIONS_PATH,
            record_id=record_id,
        )

    counted = len(ctx.index.exclusions)
    excluded = ledger.counts_by_disposition()[Disposition.EXCLUDED]
    if counted != excluded:
        yield diagnostic(
            IssueCode.IMPORT_DENOMINATOR_MISMATCH,
            f"{excluded} record(s) are dispositioned excluded but {EXCLUSIONS_PATH} holds "
            f"{counted} exclusion(s)",
            path=EXCLUSIONS_PATH,
            excluded=excluded,
            exclusions=counted,
        )


def _the_extraction_report_reconciles_with_dispositions(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """§6.3a: the drain's durable carrier explains exactly the review_required records — the mirror
    of `_dispositions_agree_with_the_exclusion_document` for the report side.

    A COMPLETENESS check, not a validity one, because "every review_required record carries a closed
    reason" is a property of a *finished* extraction: a freshly imported, not-yet-extracted bundle
    has review_required records and no report, and is valid-but-incomplete (its records are the
    `_undispositioned_records` completeness blocker). Enforced here so the drain invariant binds
    where Gate B is measured and at promotion, without failing `import`'s validity revalidation.

    An absent report is read as an empty one — the same fail-safe as an absent exclusions document.
    """
    ledger = ctx.index.source_ledger
    assert ledger is not None
    report = ctx.index.extraction_report
    if report is None:
        report = ExtractionReport(report_version=1, entries=())
    yield from validate_extraction_report(ledger, report)


def validate_extraction_report(
    ledger: SourceLedger, report: ExtractionReport
) -> tuple[Diagnostic, ...]:
    """§6.3a: exactly one closed reason for every `review_required` record, and none for any other.

    The extraction report is the drain's durable carrier — it explains the *resulting* unresolved
    state and never asserts a disposition, which stays derived from candidates and exclusions
    (`_dispositions_agree_with_the_exclusion_document`). This is that same reconciliation for the
    `review_required` quarantine: a review_required record the report leaves unexplained, a reason
    attached to an already-dispositioned record, and a reason naming a record the ledger does not
    enumerate all break the 1:1 accounting the report must hold. "Two reasons for one record" is not
    reachable here — the model refuses a duplicate `source_record_id` at parse time.

    A pure function on the two documents so the reconciliation itself stays unit-testable in
    isolation. `_the_extraction_report_reconciles_with_dispositions` wires it into the imports
    COMPLETENESS lane over `ctx.index.extraction_report` (not validity — see that check).
    """
    findings: list[Diagnostic] = []
    disposition_by_record = {
        record.source_record_id: record.disposition for record in ledger.records
    }
    explained = report.by_record

    for record in ledger.records:
        entry = explained.get(record.source_record_id)
        if record.disposition is Disposition.REVIEW_REQUIRED:
            if entry is None:
                findings.append(
                    diagnostic(
                        IssueCode.IMPORT_DENOMINATOR_MISMATCH,
                        f"{record.source_record_id} is review_required but "
                        f"{EXTRACTION_REPORT_PATH} gives no reason; the drain must carry exactly "
                        "one closed reason for every unresolved record",
                        path=EXTRACTION_REPORT_PATH,
                        record_id=record.source_record_id,
                    )
                )
        elif entry is not None:
            findings.append(
                diagnostic(
                    IssueCode.IMPORT_DENOMINATOR_MISMATCH,
                    f"{record.source_record_id} is dispositioned {record.disposition.value} but "
                    f"{EXTRACTION_REPORT_PATH} carries reason {entry.reason.value!r}; §6.3a "
                    "forbids a report entry for an imported or excluded record",
                    path=EXTRACTION_REPORT_PATH,
                    record_id=record.source_record_id,
                )
            )

    for entry in report.entries:
        if entry.source_record_id not in disposition_by_record:
            findings.append(
                diagnostic(
                    IssueCode.IMPORT_DENOMINATOR_MISMATCH,
                    f"{entry.source_record_id} carries an extraction-report reason but "
                    f"{LEDGER_PATH} does not enumerate it",
                    path=EXTRACTION_REPORT_PATH,
                    record_id=entry.source_record_id,
                )
            )

    return tuple(findings)


def _imported_records_name_their_own_candidates(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """An imported record's candidates must be derived from that record.

    A candidate ID is derived from its `source_record_id`, so a record naming another record's
    candidate is claiming support it does not have — and the model's "imported names at least one
    candidate" rule would still be satisfied.
    """
    owner = {
        candidate.candidate_id: candidate.source_record_id for candidate in ctx.index.candidates
    }
    for record in ctx.index.ledger_records:
        if record.disposition is not Disposition.IMPORTED:
            continue
        # An unresolvable candidate ID is `validate_referential`'s finding, so it defaults to
        # "this record's own" here rather than being reported a second time as a missing candidate.
        foreign = [
            candidate_id
            for candidate_id in record.candidate_ids
            if owner.get(candidate_id, record.source_record_id) != record.source_record_id
        ]
        if not foreign:
            continue
        # EVERY named candidate must be this record's own, not merely one of them. A candidate ID
        # is derived from its `source_record_id`, so a foreign one is support the record does not
        # have — and owning a second, genuine candidate does not license the claim.
        yield diagnostic(
            IssueCode.IMPORT_MISSING_CANDIDATE,
            f"{record.source_record_id} names {len(foreign)} candidate(s) derived from another "
            "source record",
            path=LEDGER_PATH,
            record_id=record.source_record_id,
            foreign=sorted(foreign),
        )


# --------------------------------------------------------------------------------------
# Completeness blockers (§20.5)
# --------------------------------------------------------------------------------------


def _undispositioned_records(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """`review_required` is the undispositioned Gate B blocker (§18).

    A blocker, not an error: the revision is a truthful record of work not yet done, and Gate B is
    unmet while the count is above zero.
    """
    for record in ctx.index.ledger_records:
        if record.disposition is not Disposition.REVIEW_REQUIRED:
            continue
        yield diagnostic(
            IssueCode.IMPORT_RECORD_UNDISPOSITIONED,
            f"{record.source_record_id} awaits review; Gate B requires zero undispositioned "
            "source records",
            path=LEDGER_PATH,
            record_id=record.source_record_id,
            locator=record.normalized_locator,
        )


def _approved_sources_that_were_never_enumerated(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """An owner-approved source with no ledger entry is material nothing accounts for.

    §18's staged migration registers a source *and* enumerates it. A registered source the ledger
    never mentions contributes nothing to the denominator while being approved, which is exactly
    the "unexplained" state Gate B requires to be zero.
    """
    ledger = ctx.index.source_ledger
    assert ledger is not None
    if ctx.index.sources is None:
        return
    enumerated = {source.source_id for source in ledger.sources}
    for spec in ctx.index.sources.sources:
        if spec.source_id in enumerated:
            continue
        yield diagnostic(
            IssueCode.IMPORT_UNEXPLAINED_RECORD,
            f"{spec.source_id} is an approved source that {LEDGER_PATH} never enumerates",
            path=SOURCES_PATH,
            record_id=spec.source_id,
        )
