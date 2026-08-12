"""Layer 3: captures are safe to keep, blobs are the bytes they claim, evidence carries authority.

The split between the two entry points here is the whole point of the module and is easy to collapse
by accident.

`validate_evidence_structural` scans with **exactly the ruleset version the revision's manifest
records**. That is what makes a revision's verdict stable: the same bytes get the same structural
answer in a year, whatever this build has since learned to detect.

`evidence_completeness` additionally scans with the **stronger installed** ruleset and reports hits
as *blockers*, never errors. §12.2 is explicit that a newer catalog "does not retroactively make the
selected revision structurally invalid or rewrite the old manifest's assertion" — the owner
recaptures and promotes, and until they do the record is unusable but the revision is still valid.

An unavailable recorded version is `could_not_complete`, never a clean scan. "We cannot check" and
"we checked and found nothing" must never look alike.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Final

from boardwatch.profile_bundle import secret_scan
from boardwatch.profile_bundle.blobs import (
    MAX_CAPTURE_BYTES,
    MAX_REVISION_EVIDENCE_BYTES,
    BlobDigestMismatchError,
    BlobNotFoundError,
    blob_size,
    read_blob,
)
from boardwatch.profile_bundle.errors import (
    Diagnostic,
    IssueCode,
    UnsupportedSecretRulesetError,
    diagnostic,
)
from boardwatch.profile_bundle.models.evidence import (
    NON_VERIFYING_CLASSES,
    AnyEvidence,
    BlobCapture,
    EvidenceClass,
    InlineCapture,
    Redaction,
    SufficiencyState,
)
from boardwatch.profile_bundle.models.facts import FactRecord
from boardwatch.profile_bundle.secret_scan import InvalidUtf8CaptureError
from boardwatch.profile_bundle.validation.context import ValidationContext

# `secret_scan` is imported as a MODULE and its catalog set is read at call time, not bound here.
# Binding `SUPPORTED_RULESET_VERSIONS` by name snapshots it at import, which left the
# stronger-installed-ruleset path unable to observe a newly retained version at all — precisely the
# mechanism §12.2 requires to work when a v2 catalog ships.

#: §12.2's absolute-home-path rejection. Matched against decoded capture text and against YAML
#: scalars. Deliberately covers the three shapes a real home path takes on the platforms this runs
#: on, because "there is no silent private-bundle exception" — a bundle that leaked
#: `/Users/<name>/...` would not be portable to the person it was handed to.
_ABSOLUTE_PERSONAL_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[\s\"'(=:])(?:/(?:Users|home)/[^/\s\"')]+|/root|[A-Za-z]:\\Users\\[^\\\s\"')]+)"
)


def validate_evidence_structural(ctx: ValidationContext) -> tuple[Diagnostic, ...]:
    """Every evidence finding that makes the revision invalid, using the RECORDED ruleset."""
    return tuple(
        finding
        for check in (
            _recorded_ruleset_is_the_builtin_catalog,
            _blobs_exist_and_match_their_digests,
            _captures_are_within_the_per_capture_limit,
            _revision_is_within_the_aggregate_budget,
            _redactions_are_complete_and_marked,
            _captures_pass_the_recorded_secret_ruleset,
            _no_absolute_personal_paths,
            _contradictions_have_a_conflict_or_ruling,
            _verification_bases_are_supported_by_their_evidence,
        )
        for finding in check(ctx)
    )


def evidence_completeness(
    ctx: ValidationContext, *, installed_ruleset_version: int
) -> tuple[Diagnostic, ...]:
    """Completeness-only evidence findings: unreviewed sufficiency, and stronger-ruleset hits.

    `installed_ruleset_version` is passed in rather than read from a module constant so a caller
    can ask "what would today's catalog say?" about an old revision without this layer deciding.
    """
    return tuple(
        [
            *_unreviewed_evidence_blocks_its_dependents(ctx),
            *_stronger_ruleset_hits_are_blockers(
                ctx, installed_ruleset_version=installed_ruleset_version
            ),
        ]
    )


# --------------------------------------------------------------------------------------
# Capture access
# --------------------------------------------------------------------------------------


def _capture_bytes(ctx: ValidationContext, record: AnyEvidence) -> bytes | None:
    """The capture's raw bytes, or `None` when a blob is missing or corrupt.

    `None` rather than an exception because a missing blob is already reported by
    `_blobs_exist_and_match_their_digests`; every later check skips the record instead of reporting
    the same broken blob a second time under a different code.
    """
    capture = record.capture
    if isinstance(capture, InlineCapture):
        return capture.text.encode("utf-8")
    if ctx.bundle_root is None:
        return None
    try:
        return read_blob(ctx.bundle_root, capture.sha256)
    except (BlobNotFoundError, BlobDigestMismatchError, OSError):
        return None


def _inline_size(record: AnyEvidence) -> int:
    capture = record.capture
    return len(capture.text.encode("utf-8")) if isinstance(capture, InlineCapture) else 0


# --------------------------------------------------------------------------------------
# Ruleset identity
# --------------------------------------------------------------------------------------


def _recorded_ruleset_is_the_builtin_catalog(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """A revision recording v1 must carry rows canonically equal to the built-in v1 rows.

    §12.2 forbids removing, adding, reordering, renaming, or weakening them: the recorded catalog
    is the revision's assertion about what it passed, so a weakened local copy would let a bundle
    claim a v1 scan it never had.
    """
    recorded = ctx.index.secret_ruleset
    if recorded is None:
        return  # absent file is a structural finding
    if recorded.ruleset_version not in secret_scan.SUPPORTED_RULESET_VERSIONS:
        yield diagnostic(
            IssueCode.UNSUPPORTED_SECRET_SCAN_RULESET_VERSION,
            f"policy/secret-scan.yaml records ruleset version {recorded.ruleset_version}, which "
            "this build does not retain; refusing to report a clean scan",
            path="policy/secret-scan.yaml",
            recorded_version=recorded.ruleset_version,
            supported=sorted(secret_scan.SUPPORTED_RULESET_VERSIONS),
        )
        return
    if not secret_scan.ruleset_matches_builtin(recorded):
        yield diagnostic(
            IssueCode.SECRET_RULESET_ROWS_DIVERGED,
            f"policy/secret-scan.yaml claims ruleset version {recorded.ruleset_version} but its "
            "rows are not canonically equal to the built-in catalog for that version",
            path="policy/secret-scan.yaml",
            recorded_version=recorded.ruleset_version,
        )


# --------------------------------------------------------------------------------------
# Blob integrity
# --------------------------------------------------------------------------------------


def _blobs_exist_and_match_their_digests(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§20.3: every blob exists and matches its digest.

    A mismatch is reported and NOTHING is moved, renamed, or deleted (§12.1). The finding IS the
    quarantine: the bytes stay put so an owner restoring the exact digest from backup makes the
    revision usable again without any history being rewritten.
    """
    for record in ctx.index.evidence:
        capture = record.capture
        if not isinstance(capture, BlobCapture):
            continue
        if ctx.bundle_root is None:
            # A bare tree handed in for inspection has no blob store. Reported once, as an
            # unverifiable state, rather than as a missing blob per record.
            yield diagnostic(
                IssueCode.MISSING_BLOB,
                f"{record.evidence_id} names a blob but no bundle root was supplied, so blob "
                "integrity could not be checked",
                path="evidence/records.yaml",
                record_id=record.evidence_id,
            )
            continue
        try:
            read_blob(ctx.bundle_root, capture.sha256)
        except BlobNotFoundError:
            yield diagnostic(
                IssueCode.MISSING_BLOB,
                f"{record.evidence_id} names blob sha256:{capture.sha256}, which is not stored",
                path="evidence/records.yaml",
                record_id=record.evidence_id,
                blob_digest=capture.sha256,
            )
        except BlobDigestMismatchError as exc:
            yield diagnostic(
                IssueCode.BLOB_DIGEST_MISMATCH,
                f"{record.evidence_id}: stored blob does not hash to sha256:{capture.sha256}; "
                "the bytes are quarantined in place, not moved or deleted",
                path="evidence/records.yaml",
                record_id=record.evidence_id,
                expected_digest=exc.expected,
                actual_digest=exc.actual,
            )


# --------------------------------------------------------------------------------------
# Byte budgets
# --------------------------------------------------------------------------------------


def _captures_are_within_the_per_capture_limit(ctx: ValidationContext) -> Iterator[Diagnostic]:
    for record in ctx.index.evidence:
        capture = record.capture
        if isinstance(capture, InlineCapture):
            size = len(capture.text.encode("utf-8"))
        elif ctx.bundle_root is None:
            continue
        else:
            try:
                size = blob_size(ctx.bundle_root, capture.sha256)
            except (BlobNotFoundError, OSError):
                continue  # missing blob already reported
        if size <= MAX_CAPTURE_BYTES:
            continue
        yield diagnostic(
            IssueCode.CAPTURE_TOO_LARGE,
            f"{record.evidence_id}: capture is {size} bytes, over the "
            f"{MAX_CAPTURE_BYTES}-byte per-capture limit",
            path="evidence/records.yaml",
            record_id=record.evidence_id,
            size=size,
            limit=MAX_CAPTURE_BYTES,
        )


def _revision_is_within_the_aggregate_budget(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Inline UTF-8 lengths plus the raw sizes of UNIQUE referenced blobs.

    Deduplicated by full digest, so two records citing one blob count its bytes once — the same rule
    §7 step 2 uses to build the evidence-set digest, and for the same reason: the revision holds one
    copy of those bytes.
    """
    total = sum(_inline_size(record) for record in ctx.index.evidence)
    unique = {
        record.capture.sha256
        for record in ctx.index.evidence
        if isinstance(record.capture, BlobCapture)
    }
    if ctx.bundle_root is not None:
        for digest in sorted(unique):
            try:
                total += blob_size(ctx.bundle_root, digest)
            except (BlobNotFoundError, OSError):
                continue  # missing blob already reported
    if total <= MAX_REVISION_EVIDENCE_BYTES:
        return
    yield diagnostic(
        IssueCode.EVIDENCE_BUDGET_EXCEEDED,
        f"the revision's evidence totals {total} bytes, over the "
        f"{MAX_REVISION_EVIDENCE_BYTES}-byte limit",
        path="evidence/records.yaml",
        total_bytes=total,
        limit=MAX_REVISION_EVIDENCE_BYTES,
        unique_blobs=len(unique),
    )


# --------------------------------------------------------------------------------------
# Redactions
# --------------------------------------------------------------------------------------


def _marker_for(redaction: Redaction) -> bytes:
    return f"[REDACTED:{redaction.reason}]".encode("ascii")


def _redactions_are_complete_and_marked(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Each `{start, end, reason}` must span exactly `[REDACTED:<reason>]` in the STORED bytes.

    §12.2 puts the range over the post-redaction capture, which is what makes a redaction verifiable
    "against retained bytes without storing the removed content": the marker is present, so the
    validator can confirm the region was replaced rather than having to know what was removed.

    Non-overlap and range validity are enforced by `Redaction` and `_redactions_do_not_overlap` at
    parse time, so only the marker check lives here — it is the part that needs the bytes.
    """
    for record in ctx.index.evidence:
        if not record.redactions:
            continue
        raw = _capture_bytes(ctx, record)
        if raw is None:
            continue  # blob missing or corrupt; already reported
        for redaction in record.redactions:
            expected = _marker_for(redaction)
            if redaction.end > len(raw):
                yield diagnostic(
                    IssueCode.REDACTION_INVALID,
                    f"{record.evidence_id}: redaction [{redaction.start}, {redaction.end}) runs "
                    f"past the {len(raw)}-byte capture",
                    path="evidence/records.yaml",
                    record_id=record.evidence_id,
                    start=redaction.start,
                    end=redaction.end,
                    capture_bytes=len(raw),
                )
                continue
            if raw[redaction.start : redaction.end] == expected:
                continue
            # The finding names the expected marker and the range — never the bytes actually found,
            # which are the redacted region's neighbourhood and may be exactly what was hidden.
            yield diagnostic(
                IssueCode.REDACTION_INVALID,
                f"{record.evidence_id}: redaction [{redaction.start}, {redaction.end}) does not "
                f"contain exactly the marker {expected.decode('ascii')}",
                path="evidence/records.yaml",
                record_id=record.evidence_id,
                start=redaction.start,
                end=redaction.end,
                reason=str(redaction.reason),
            )


# --------------------------------------------------------------------------------------
# Secret scanning
# --------------------------------------------------------------------------------------


def _scan_all(
    ctx: ValidationContext, *, ruleset_version: int
) -> Iterator[tuple[AnyEvidence, tuple[str, int, int] | None]]:
    """Every capture scanned once. Yields `(record, None)` for a capture that will not decode."""
    for record in ctx.index.evidence:
        raw = _capture_bytes(ctx, record)
        if raw is None:
            continue
        try:
            hits = secret_scan.scan_capture(
                raw, media_type=record.capture.media_type, ruleset_version=ruleset_version
            )
        except InvalidUtf8CaptureError:
            yield record, None
            continue
        for hit in hits:
            yield record, (hit.rule_id, hit.start, hit.end)


def _captures_pass_the_recorded_secret_ruleset(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """Fail closed on a hit from the ruleset version the manifest records.

    Diagnostics carry the rule ID, the evidence ID, and a byte range — never the matched text. A
    scanner whose own report leaks the credential it found has contained nothing.
    """
    recorded = ctx.manifest.secret_scan_ruleset_version
    if recorded not in secret_scan.SUPPORTED_RULESET_VERSIONS:
        return  # reported once by `_recorded_ruleset_is_the_builtin_catalog`
    for record, hit in _scan_all(ctx, ruleset_version=recorded):
        if hit is None:
            yield diagnostic(
                IssueCode.INVALID_UTF8,
                f"{record.evidence_id}: capture is not valid UTF-8, so the secret ruleset could "
                "not be evaluated against it",
                path="evidence/records.yaml",
                record_id=record.evidence_id,
            )
            continue
        rule_id, start, end = hit
        yield diagnostic(
            IssueCode.SECRET_DETECTED,
            f"{record.evidence_id}: rule {rule_id} matched bytes [{start}, {end}) of the capture",
            path="evidence/records.yaml",
            record_id=record.evidence_id,
            rule_id=rule_id,
            start=start,
            end=end,
            ruleset_version=recorded,
        )


def _stronger_ruleset_hits_are_blockers(
    ctx: ValidationContext, *, installed_ruleset_version: int
) -> Iterator[Diagnostic]:
    """Hits a NEWER installed catalog finds, reported as blockers requiring recapture.

    Never errors: §12.2 says a stronger catalog "does not retroactively make the selected revision
    structurally invalid or rewrite the old manifest's assertion". Only hits the recorded ruleset
    did not already report are new, so an operator is not told twice about one secret.
    """
    recorded = ctx.manifest.secret_scan_ruleset_version
    if installed_ruleset_version <= recorded:
        return
    if installed_ruleset_version not in secret_scan.SUPPORTED_RULESET_VERSIONS:
        yield diagnostic(
            IssueCode.UNSUPPORTED_SECRET_SCAN_RULESET_VERSION,
            f"ruleset version {installed_ruleset_version} was requested for a stronger rescan but "
            "is not retained by this build",
            requested_version=installed_ruleset_version,
            supported=sorted(secret_scan.SUPPORTED_RULESET_VERSIONS),
        )
        return
    try:
        already = {
            (record.evidence_id, hit)
            for record, hit in _scan_all(ctx, ruleset_version=recorded)
            if hit is not None
        }
    except UnsupportedSecretRulesetError:
        return  # the recorded version is unavailable; reported by the structural layer
    for record, hit in _scan_all(ctx, ruleset_version=installed_ruleset_version):
        if hit is None or (record.evidence_id, hit) in already:
            continue
        rule_id, start, end = hit
        yield diagnostic(
            IssueCode.SECRET_DETECTED_BY_STRONGER_RULESET,
            f"{record.evidence_id}: rule {rule_id} of ruleset {installed_ruleset_version} matched "
            f"bytes [{start}, {end}); recapture, rescan, and promote a new revision",
            path="evidence/records.yaml",
            record_id=record.evidence_id,
            rule_id=rule_id,
            start=start,
            end=end,
            ruleset_version=installed_ruleset_version,
            recorded_version=recorded,
        )


# --------------------------------------------------------------------------------------
# Absolute personal paths
# --------------------------------------------------------------------------------------


def _no_absolute_personal_paths(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§12.2: absolute home paths are rejected in revision YAML and in decoded capture bytes.

    Checked in both places because they fail differently: a locator in YAML makes the bundle
    unportable, and a path inside a capture leaks the owner's account name to whoever reads the
    evidence. "There is no silent private-bundle exception."

    The finding never quotes the matched path — that string is the personal material.
    """
    for record in ctx.index.evidence:
        for field, value in _portable_text_fields(record):
            if _ABSOLUTE_PERSONAL_PATH_RE.search(value):
                yield diagnostic(
                    IssueCode.ABSOLUTE_PERSONAL_PATH,
                    f"{record.evidence_id}.{field} contains an absolute home or user-directory "
                    "path; replace it with a portable relative locator",
                    path="evidence/records.yaml",
                    record_id=record.evidence_id,
                    field=field,
                )
        raw = _capture_bytes(ctx, record)
        if raw is None:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue  # reported by the secret-scan pass
        match = _ABSOLUTE_PERSONAL_PATH_RE.search(text)
        if match is None:
            continue
        yield diagnostic(
            IssueCode.ABSOLUTE_PERSONAL_PATH,
            f"{record.evidence_id}: the capture contains an absolute home or user-directory path "
            f"at bytes [{match.start()}, {match.end()}); redact it as `personal_path` or recapture "
            "with a portable locator",
            path="evidence/records.yaml",
            record_id=record.evidence_id,
            start=match.start(),
            end=match.end(),
        )


def _portable_text_fields(record: AnyEvidence) -> Iterator[tuple[str, str]]:
    """The evidence fields that may carry a path. Enumerated rather than reflected over every string
    field, so adding a locator-bearing field is a deliberate addition here."""
    yield "title", record.title
    locator = getattr(record, "locator", None)
    if locator is not None:
        yield "locator.value", locator.value
    origin = getattr(record, "origin", None)
    if origin is not None:
        yield "origin.reference", origin.reference
    path = getattr(record, "path", None)
    if isinstance(path, str):
        yield "path", path


# --------------------------------------------------------------------------------------
# Evidence authority
# --------------------------------------------------------------------------------------


def _contradictions_have_a_conflict_or_ruling(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§20.3: contradictory evidence requires a conflict or ruling.

    Evidence that contradicts a fact with nothing recorded about the dispute leaves the fact usable
    while the bundle already holds a reason to doubt it — the exact state the conflict machinery
    exists to make visible.
    """
    ruled_facts = {
        fact_id
        for ruling in ctx.index.rulings
        for fact_id in (*ruling.rejected_fact_ids, ruling.selected_fact_id or "")
        if fact_id
    }
    grouped = {
        fact_id
        for conflict in ctx.index.conflicts
        for fact_id in conflict.candidate_fact_ids
    }
    for record in ctx.index.evidence:
        for target in record.contradicts_record_ids:
            if target in grouped or target in ruled_facts:
                continue
            if ctx.index.get(target) is None:
                continue  # broken reference, reported by the referential layer
            yield diagnostic(
                IssueCode.CONTRADICTION_WITHOUT_RULING,
                f"{record.evidence_id} contradicts {target}, which belongs to no conflict group "
                "and is named by no ruling",
                path="evidence/records.yaml",
                record_id=record.evidence_id,
                target=target,
            )


def _verification_bases_are_supported_by_their_evidence(
    ctx: ValidationContext,
) -> Iterator[Diagnostic]:
    """A fact's `verification_basis` must be backed by evidence of a class that can carry it.

    Two distinct failures share this check because they are the same mistake seen from two sides: a
    basis with no evidence of the right class, and a basis resting only on a non-verifying class.
    §12.1 makes a secondary summary "import evidence, not final verification", so a fact claiming
    `public_record_verified` while citing only a summary is asserting a check that never happened.
    """
    from boardwatch.profile_bundle.models.evidence import BASIS_EVIDENCE_CLASSES

    by_id = {record.evidence_id: record for record in ctx.index.evidence}
    for fact in ctx.index.facts:
        acceptable = BASIS_EVIDENCE_CLASSES.get(str(fact.verification_basis))
        if acceptable is None:
            continue  # an unknown basis is a closed-enum failure at parse time
        if not any(evidence_id in by_id for evidence_id in fact.evidence_ids):
            continue  # a fact with no resolvable evidence is a referential finding
        # Of the citations that resolve, only the SUPPORTING ones can carry a basis. Kept separate
        # from the check above on purpose: "cites nothing that resolves" is somebody else's finding,
        # but "cites only evidence that contradicts or contextualizes it" is this one's, and folding
        # them together would let a fact claim `public_record_verified` on the strength of a source
        # that merely mentions it and report nothing at all (D-144).
        classes = {record.evidence_class for record in supporting_evidence(fact, by_id)}
        if classes & acceptable:
            continue
        yield diagnostic(
            IssueCode.VERIFICATION_BASIS_UNSUPPORTED,
            f"{fact.fact_id} declares basis {fact.verification_basis} but "
            + (
                f"cites only {', '.join(sorted(str(c) for c in classes))} evidence"
                if classes
                else "cites no evidence that supports it"
            ),
            path=ctx.index.path_of(fact.fact_id),
            record_id=fact.fact_id,
            basis=str(fact.verification_basis),
            cited_classes=sorted(str(c) for c in classes),
        )


def _unreviewed_evidence_blocks_its_dependents(ctx: ValidationContext) -> Iterator[Diagnostic]:
    """§12.1: "Unreviewed evidence is structurally valid but a completeness blocker for every
    dependent accepted record."

    A blocker, not an error, and the distinction is the design's: the revision is a valid,
    promotable statement of what has been captured; the records leaning on unreviewed evidence are
    the part that cannot be used yet.
    """
    for record in ctx.index.evidence:
        if record.sufficiency_review.state is not SufficiencyState.UNREVIEWED:
            continue
        dependents = sorted(
            record_id
            for record_id, cited in ctx.index.evidence_links.items()
            if record.evidence_id in cited
        )
        yield diagnostic(
            IssueCode.EVIDENCE_UNREVIEWED,
            f"{record.evidence_id} has an unreviewed sufficiency state; "
            f"{len(dependents)} dependent record(s) cannot be used until an owner approves it",
            path="evidence/records.yaml",
            record_id=record.evidence_id,
            dependents=dependents,
        )


#: Evidence classes that cannot on their own satisfy a verification requirement (§12.1). Re-exported
#: so the semantic layer can reason about grounding without importing the models package directly.
NON_VERIFYING_EVIDENCE_CLASSES: Final[frozenset[EvidenceClass]] = NON_VERIFYING_CLASSES


def supporting_evidence(
    fact: FactRecord, by_evidence_id: Mapping[str, AnyEvidence]
) -> list[AnyEvidence]:
    """The evidence a fact cites that also **supports** it (§12). The grounding question's input.

    `evidence_ids` is not a statement that the evidence backs the fact. §12 makes the relationship a
    closed choice of three, and requires the citation to be symmetric over all three, so a fact
    legitimately cites the source that *contradicts* it and the one that merely *contextualizes* it.
    Verification is a different question, and only `supports` answers it: a source arguing against a
    fact cannot be what verifies it, and a contextual source explicitly "cannot satisfy a
    verification requirement".

    Read raw, `evidence_ids` conflated the two, so one capture that contextualized a fact cleared
    that fact's predicate `minimum_evidence` and its `verification_basis` — silently, with no
    compensating diagnostic. Reachable by hand before, and automatic once `add_evidence` began
    writing the back-citation, which is what surfaced it (D-144).

    One definition for both grounding checks, because two restatements of "cited *and* supporting"
    is how they come to disagree about which facts are verified.
    """
    return [
        record
        for evidence_id in fact.evidence_ids
        if (record := by_evidence_id.get(evidence_id)) is not None
        and fact.fact_id in record.supports_record_ids
    ]
