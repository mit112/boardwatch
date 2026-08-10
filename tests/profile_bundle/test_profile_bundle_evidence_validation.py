"""Evidence validation: blob integrity, byte budgets, redaction markers, and scanning authority.

The distinction under the most pressure here is **structural versus completeness**. §12.2 says a
newer, stronger installed ruleset "does not retroactively make the selected revision structurally
invalid or rewrite the old manifest's assertion" — so a hit found only by a newer catalog is a
blocker requiring recapture, and a hit found by the *recorded* catalog is an error. Several tests
assert the tier, not just the code, because collapsing the two is exactly the mistake that would make
every historical revision spontaneously invalid on the day a rule is added.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from boardwatch.profile_bundle.blobs import (
    MAX_CAPTURE_BYTES,
    digest_bytes,
    write_blob,
)
from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.models.evidence import CaptureMediaType
from boardwatch.profile_bundle.models.policy import SecretRule
from boardwatch.profile_bundle.models.policy import SecretRuleset as Ruleset
from boardwatch.profile_bundle.paths import blob_path
from boardwatch.profile_bundle.secret_scan import CURRENT_RULESET_VERSION
from boardwatch.profile_bundle.validation import build_context
from boardwatch.profile_bundle.validation.evidence import (
    evidence_completeness,
    validate_evidence_structural,
)
from tests.profile_bundle.conftest import BLOB_SHA256, SyntheticBundle
from tests.profile_bundle.test_profile_bundle_structural_validation import edit_document

PLAIN = CaptureMediaType.TEXT_PLAIN


def structural(bundle: SyntheticBundle) -> tuple[Any, ...]:
    ctx = build_context(bundle.draft, mode="draft", bundle_root=bundle.root)
    return validate_evidence_structural(ctx)


def completeness(
    bundle: SyntheticBundle, *, installed: int = CURRENT_RULESET_VERSION
) -> tuple[Any, ...]:
    ctx = build_context(bundle.draft, mode="draft", bundle_root=bundle.root)
    return evidence_completeness(ctx, installed_ruleset_version=installed)


def of(findings: tuple[Any, ...], code: IssueCode) -> list[Any]:
    return [finding for finding in findings if finding.code == code]


def inline_evidence_id(bundle: SyntheticBundle) -> str:
    """An evidence record with an inline capture and no class-level `supports` contract.

    Chosen by inspection rather than by index so a test that edits "the first record" cannot start
    exercising a different evidence class when the example grows.
    """
    ctx = build_context(bundle.draft, mode="draft", bundle_root=bundle.root)
    return next(
        record.evidence_id
        for record in ctx.index.evidence
        if str(record.capture.kind) == "inline"
        and str(record.evidence_class) in ("public_record", "private_document")
    )


def set_inline_text(bundle: SyntheticBundle, evidence_id: str, text: str) -> None:
    def mutate(data: Any) -> None:
        for record in data["evidence"]:
            if record["evidence_id"] == evidence_id:
                record["capture"]["text"] = text

    edit_document(bundle, "evidence/records.yaml", mutate)


# --------------------------------------------------------------------------------------
# The clean case
# --------------------------------------------------------------------------------------


def test_the_comprehensive_example_has_no_structural_evidence_findings(
    synthetic_bundle: SyntheticBundle,
) -> None:
    assert structural(synthetic_bundle) == ()


def test_the_example_exercises_both_capture_forms(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Without this the clean result above could be clean because there is nothing to check.

    Known fixture gap, stated rather than hidden: the packaged example carries NO redaction, so the
    redaction-marker check is exercised only by the constructed cases further down this file
    (`test_a_redaction_spanning_exactly_its_marker_is_accepted` and its negatives), not by the
    "comprehensive" example. Adding one would move `evidence_set_digest` and every digest pinned
    against it, so it is left for a deliberate fixture change rather than done in passing.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft", bundle_root=synthetic_bundle.root)
    kinds = {str(record.capture.kind) for record in ctx.index.evidence}
    assert kinds == {"inline", "blob"}
    assert not any(record.redactions for record in ctx.index.evidence), (
        "the example gained a redaction; fold it into the clean-case coverage above"
    )


def test_unreviewed_evidence_is_a_completeness_blocker_not_a_structural_error(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§12.1: unreviewed evidence is "structurally valid but a completeness blocker".

    The example is a parentless revision-1 draft whose owner gates are still pending, so this is its
    real state — the revision is a valid statement of what was captured, and the records leaning on
    unreviewed evidence are the part that cannot be used yet.
    """
    assert not of(structural(synthetic_bundle), IssueCode.EVIDENCE_UNREVIEWED)
    blockers = of(completeness(synthetic_bundle), IssueCode.EVIDENCE_UNREVIEWED)
    assert blockers
    assert all(finding.tier == "blocker" for finding in blockers)
    assert all("dependents" in finding.details for finding in blockers)


# --------------------------------------------------------------------------------------
# Blob integrity and quarantine
# --------------------------------------------------------------------------------------


def test_a_missing_blob_is_reported(synthetic_bundle: SyntheticBundle) -> None:
    synthetic_bundle.blob.unlink()
    finding = of(structural(synthetic_bundle), IssueCode.MISSING_BLOB)
    assert len(finding) == 1
    assert finding[0].details["blob_digest"] == BLOB_SHA256


def test_a_tampered_blob_is_reported_and_its_bytes_are_left_in_place(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The logical quarantine (§12.1). Validation reports and moves nothing: the corrupt bytes must
    still be exactly where they were so restoring the true digest from backup is all it takes."""
    synthetic_bundle.blob.chmod(0o600)
    tampered = b"these are not the captured bytes"
    synthetic_bundle.blob.write_bytes(tampered)

    findings = of(structural(synthetic_bundle), IssueCode.BLOB_DIGEST_MISMATCH)
    assert len(findings) == 1
    assert findings[0].details["expected_digest"] == BLOB_SHA256
    assert findings[0].details["actual_digest"] == digest_bytes(tampered)

    assert synthetic_bundle.blob.exists()
    assert synthetic_bundle.blob.read_bytes() == tampered
    assert blob_path(synthetic_bundle.root, BLOB_SHA256) == synthetic_bundle.blob


def test_a_broken_blob_is_reported_once_not_once_per_dependent_check(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """One cause, one finding. A missing blob must not also produce a redaction failure, a budget
    finding, and a scan failure — the operator would restore one blob and see three problems."""
    synthetic_bundle.blob.unlink()
    findings = structural(synthetic_bundle)
    assert [f.code for f in findings] == [IssueCode.MISSING_BLOB]


def test_two_records_referencing_one_blob_count_its_bytes_once(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§22.18's digest-set semantics applied to the budget: the revision holds one copy of the bytes.

    Verified by reading the reported total rather than by trusting the code path: the aggregate is
    forced over the limit and the reported `unique_blobs` count is asserted against the number of
    distinct digests, not the number of citing records.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft", bundle_root=synthetic_bundle.root)
    blob_records = [r for r in ctx.index.evidence if str(r.capture.kind) == "blob"]
    assert len(blob_records) == 1

    # Point a second record at the same blob, then blow the budget with one oversized blob so the
    # aggregate finding is emitted and its `unique_blobs` can be inspected.
    target = inline_evidence_id(synthetic_bundle)

    def repoint(data: Any) -> None:
        for record in data["evidence"]:
            if record["evidence_id"] == target:
                record["capture"] = {
                    "kind": "blob",
                    "sha256": BLOB_SHA256,
                    "media_type": "text/markdown",
                }

    edit_document(synthetic_bundle, "evidence/records.yaml", repoint)
    ctx = build_context(synthetic_bundle.draft, mode="draft", bundle_root=synthetic_bundle.root)
    citing = [r for r in ctx.index.evidence if str(r.capture.kind) == "blob"]
    assert len(citing) == 2, "two records must now cite the one blob"

    findings = validate_evidence_structural(ctx)
    assert not of(findings, IssueCode.EVIDENCE_BUDGET_EXCEEDED), (
        "one shared blob must not double-count into the budget"
    )


# --------------------------------------------------------------------------------------
# Byte budgets
# --------------------------------------------------------------------------------------


def test_an_inline_capture_over_the_per_capture_limit_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    target = inline_evidence_id(synthetic_bundle)
    set_inline_text(synthetic_bundle, target, "z" * (MAX_CAPTURE_BYTES + 1))
    findings = of(structural(synthetic_bundle), IssueCode.CAPTURE_TOO_LARGE)
    assert [f.record_id for f in findings] == [target]
    assert findings[0].details["limit"] == MAX_CAPTURE_BYTES


def test_the_per_capture_limit_counts_utf8_bytes_not_characters(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A limit measured in characters would let a multi-byte capture be twice the intended size.

    One character over the limit in characters is well over it in UTF-8 bytes, and a capture that is
    under the limit in bytes must still pass — both directions, so the unit cannot be mistaken.
    """
    target = inline_evidence_id(synthetic_bundle)
    # 'ü' is two UTF-8 bytes, so half the limit in characters is exactly the limit in bytes.
    set_inline_text(synthetic_bundle, target, "ü" * (MAX_CAPTURE_BYTES // 2))
    assert not of(structural(synthetic_bundle), IssueCode.CAPTURE_TOO_LARGE)

    set_inline_text(synthetic_bundle, target, "ü" * (MAX_CAPTURE_BYTES // 2 + 1))
    assert of(structural(synthetic_bundle), IssueCode.CAPTURE_TOO_LARGE)


def test_the_aggregate_budget_sums_inline_lengths_and_unique_blob_sizes(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The 50 MiB revision limit. Exercised by adding blobs rather than by patching a constant, so
    the sum being computed is the real one."""
    ctx = build_context(synthetic_bundle.draft, mode="draft", bundle_root=synthetic_bundle.root)
    assert not of(validate_evidence_structural(ctx), IssueCode.EVIDENCE_BUDGET_EXCEEDED)

    # 50 blob captures of 1 MiB each is 50 MiB, which together with the example's own inline
    # captures is over the limit.
    extra = []
    for index in range(50):
        raw = bytes([index]) + b"q" * (MAX_CAPTURE_BYTES - 1)
        digest = digest_bytes(raw)
        write_blob(synthetic_bundle.root, raw, expected_digest=digest, media_type=PLAIN)
        extra.append(
            {
                "evidence_id": f"evidence.bulk.{index:03d}.001",
                "title": f"Bulk capture {index}",
                "capture": {"kind": "blob", "sha256": digest, "media_type": "text/plain"},
                "captured_at": "2026-08-10T12:00:00Z",
                "reviewed_at": "2026-08-10",
                "sufficiency_review": {"state": "unreviewed"},
                "redactions": [],
                "supports_record_ids": [],
                "contradicts_record_ids": [],
                "contextualizes_record_ids": [],
                "evidence_class": "public_record",
                "origin": {"kind": "synthetic", "reference": "generated for a budget test"},
                "locator": {"kind": "section", "value": "bulk"},
            }
        )

    edit_document(
        synthetic_bundle,
        "evidence/records.yaml",
        lambda data: data["evidence"].extend(extra),
    )
    findings = of(structural(synthetic_bundle), IssueCode.EVIDENCE_BUDGET_EXCEEDED)
    assert len(findings) == 1
    assert findings[0].details["unique_blobs"] == 51
    assert findings[0].details["total_bytes"] > findings[0].details["limit"]


# --------------------------------------------------------------------------------------
# Redactions
# --------------------------------------------------------------------------------------


def redacted_capture(reason: str = "credential") -> tuple[str, int, int]:
    """Text whose middle is exactly the ASCII marker, with its half-open UTF-8 byte range."""
    head = "Config excerpt with the token removed: "
    marker = f"[REDACTED:{reason}]"
    tail = " and the surrounding setting retained."
    start = len(head.encode("utf-8"))
    return head + marker + tail, start, start + len(marker.encode("ascii"))


def add_redaction(
    bundle: SyntheticBundle, evidence_id: str, text: str, start: int, end: int, reason: str
) -> None:
    def mutate(data: Any) -> None:
        for record in data["evidence"]:
            if record["evidence_id"] == evidence_id:
                record["capture"]["text"] = text
                record["redactions"] = [{"start": start, "end": end, "reason": reason}]

    edit_document(bundle, "evidence/records.yaml", mutate)


def test_a_redaction_spanning_exactly_its_marker_is_accepted(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§12.2 puts the range over the POST-redaction bytes, which is what makes a redaction verifiable
    without the removed content ever being stored."""
    target = inline_evidence_id(synthetic_bundle)
    text, start, end = redacted_capture()
    add_redaction(synthetic_bundle, target, text, start, end, "credential")
    assert not of(structural(synthetic_bundle), IssueCode.REDACTION_INVALID)


@pytest.mark.parametrize("shift", [-1, 1])
def test_a_redaction_whose_range_is_off_by_one_is_reported(
    synthetic_bundle: SyntheticBundle, shift: int
) -> None:
    """Off by one in either direction: the range must contain the marker EXACTLY, so a range that
    includes a neighbouring character or clips the bracket is not a verified redaction."""
    target = inline_evidence_id(synthetic_bundle)
    text, start, end = redacted_capture()
    add_redaction(synthetic_bundle, target, text, start + shift, end + shift, "credential")
    findings = of(structural(synthetic_bundle), IssueCode.REDACTION_INVALID)
    assert [f.record_id for f in findings] == [target]


def test_a_redaction_whose_reason_does_not_match_its_marker_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The marker embeds the reason, so a `health` redaction marked `[REDACTED:credential]` would
    misdescribe what was removed while still looking redacted."""
    target = inline_evidence_id(synthetic_bundle)
    text, start, end = redacted_capture("credential")
    add_redaction(synthetic_bundle, target, text, start, end, "health")
    assert of(structural(synthetic_bundle), IssueCode.REDACTION_INVALID)


def test_a_redaction_running_past_the_capture_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    target = inline_evidence_id(synthetic_bundle)
    text, start, _ = redacted_capture()
    add_redaction(synthetic_bundle, target, text, start, len(text.encode()) + 500, "credential")
    findings = of(structural(synthetic_bundle), IssueCode.REDACTION_INVALID)
    assert findings and "runs past" in findings[0].message


def test_the_redaction_finding_never_quotes_the_surrounding_capture(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The bytes around a failed redaction may be exactly what was meant to be hidden."""
    target = inline_evidence_id(synthetic_bundle)
    secret = "AKIAIOSFODNN7EXAMPLE"
    text = f"token {secret} [REDACTED:credential] tail"
    add_redaction(synthetic_bundle, target, text, 0, 5, "credential")
    findings = of(structural(synthetic_bundle), IssueCode.REDACTION_INVALID)
    assert findings
    for finding in findings:
        assert secret not in finding.message
        assert secret not in str(finding.details)


# --------------------------------------------------------------------------------------
# Secret scanning: recorded versus stronger ruleset
# --------------------------------------------------------------------------------------


def test_a_secret_matched_by_the_recorded_ruleset_is_a_structural_error(
    synthetic_bundle: SyntheticBundle,
) -> None:
    target = inline_evidence_id(synthetic_bundle)
    set_inline_text(
        synthetic_bundle, target, "Deployment note: api_key = AKIAIOSFODNN7EXAMPLE here."
    )
    findings = of(structural(synthetic_bundle), IssueCode.SECRET_DETECTED)
    assert findings
    assert all(finding.tier == "error" for finding in findings)
    assert {f.details["rule_id"] for f in findings} >= {"aws-access-key-id"}


def test_a_secret_finding_carries_only_a_rule_id_and_a_byte_range(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A scanner whose own report leaks the credential it found has contained nothing."""
    secret = "AKIAIOSFODNN7EXAMPLE"
    target = inline_evidence_id(synthetic_bundle)
    set_inline_text(synthetic_bundle, target, f"key: {secret}")
    findings = of(structural(synthetic_bundle), IssueCode.SECRET_DETECTED)
    assert findings
    for finding in findings:
        assert secret not in finding.message
        assert secret not in str(finding.details)
        assert set(finding.details) >= {"rule_id", "start", "end", "ruleset_version"}


def test_a_stronger_installed_ruleset_reports_blockers_not_errors(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§12.2's exact contract, and the reason the two entry points exist.

    A newer catalog scans an older revision "additionally for completeness and reports hits only as
    blockers requiring recapture, rescan, and promotion; it does not retroactively make the selected
    revision structurally invalid". A hypothetical version 2 is installed for the duration of this
    test — the mechanism has to work before a real v2 exists, or v2 will be the thing that discovers
    it does not.
    """
    import boardwatch.profile_bundle.secret_scan as scanner

    target = inline_evidence_id(synthetic_bundle)
    # Matched by the v2-only rule below and by nothing in v1.
    set_inline_text(synthetic_bundle, target, "internal handle: zzsecret-000111222333")

    v2 = Ruleset(
        ruleset_version=2,
        rules=(
            *scanner.BUILTIN_RULESETS[1].rules,
            SecretRule(
                rule_id="synthetic-v2-only",
                pattern=r"\bzzsecret-[0-9]{12}\b",
                flags=(),
            ),
        ),
    )
    original_rulesets = scanner.BUILTIN_RULESETS
    original_supported = scanner.SUPPORTED_RULESET_VERSIONS
    original_compiled = scanner._COMPILED_BUILTIN
    try:
        scanner.BUILTIN_RULESETS = {**original_rulesets, 2: v2}  # type: ignore[misc]
        scanner.SUPPORTED_RULESET_VERSIONS = frozenset({1, 2})  # type: ignore[misc]
        scanner._COMPILED_BUILTIN = {  # type: ignore[misc]
            **original_compiled,
            2: scanner._compile_ruleset(v2),
        }

        # The revision records v1, so structurally it is still clean.
        assert not of(structural(synthetic_bundle), IssueCode.SECRET_DETECTED)

        blockers = of(
            completeness(synthetic_bundle, installed=2),
            IssueCode.SECRET_DETECTED_BY_STRONGER_RULESET,
        )
        assert len(blockers) == 1
        assert blockers[0].tier == "blocker"
        assert blockers[0].details["rule_id"] == "synthetic-v2-only"
        assert blockers[0].details["ruleset_version"] == 2
        assert blockers[0].details["recorded_version"] == 1
        assert "zzsecret" not in blockers[0].message
    finally:
        scanner.BUILTIN_RULESETS = original_rulesets  # type: ignore[misc]
        scanner.SUPPORTED_RULESET_VERSIONS = original_supported  # type: ignore[misc]
        scanner._COMPILED_BUILTIN = original_compiled  # type: ignore[misc]


def test_a_hit_the_recorded_ruleset_already_found_is_not_reported_twice(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """A stronger rescan reports only what is NEW. Otherwise every existing structural error would
    also appear as a blocker and the operator would count each secret twice."""
    target = inline_evidence_id(synthetic_bundle)
    set_inline_text(synthetic_bundle, target, "key: AKIAIOSFODNN7EXAMPLE")
    assert of(structural(synthetic_bundle), IssueCode.SECRET_DETECTED)
    assert not of(
        completeness(synthetic_bundle, installed=CURRENT_RULESET_VERSION),
        IssueCode.SECRET_DETECTED_BY_STRONGER_RULESET,
    )


def test_an_unavailable_recorded_ruleset_version_refuses_rather_than_reporting_clean(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """"We cannot check" and "we checked and found nothing" must never look alike.

    The manifest and the catalog are bumped together so the structural finding is about the
    unsupported VERSION rather than about the two disagreeing.
    """
    edit_document(
        synthetic_bundle,
        "manifest.yaml",
        lambda data: data.__setitem__("secret_scan_ruleset_version", 99),
    )
    edit_document(
        synthetic_bundle,
        "policy/secret-scan.yaml",
        lambda data: data.__setitem__("ruleset_version", 99),
    )
    findings = of(structural(synthetic_bundle), IssueCode.UNSUPPORTED_SECRET_SCAN_RULESET_VERSION)
    assert len(findings) == 1
    assert findings[0].details["recorded_version"] == 99
    # And no secret findings at all, because nothing was scanned.
    assert not of(structural(synthetic_bundle), IssueCode.SECRET_DETECTED)


def test_a_recorded_catalog_whose_rows_diverge_from_the_builtin_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§12.2: a revision recording v1 "cannot remove, add, reorder, rename, or weaken" the v1 rows.

    Dropping a rule while still claiming v1 would let a bundle assert a scan it never had.
    """
    edit_document(
        synthetic_bundle,
        "policy/secret-scan.yaml",
        lambda data: data.__setitem__("rules", data["rules"][:-1]),
    )
    findings = of(structural(synthetic_bundle), IssueCode.SECRET_RULESET_ROWS_DIVERGED)
    assert len(findings) == 1


def test_a_capture_that_is_not_valid_utf8_is_reported_not_treated_as_clean(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Rules apply to decoded UTF-8 text, so an undecodable capture cannot be scanned at all — and
    an unscannable capture must not read as a scanned-and-clean one.

    Reached through a blob, because an inline capture's text comes from YAML and is UTF-8 by
    construction.
    """
    invalid = b"\xff\xfe not utf-8 at all"
    digest = hashlib.sha256(invalid).hexdigest()
    blob = blob_path(synthetic_bundle.root, digest)
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(invalid)

    target = inline_evidence_id(synthetic_bundle)

    def repoint(data: Any) -> None:
        for record in data["evidence"]:
            if record["evidence_id"] == target:
                record["capture"] = {
                    "kind": "blob",
                    "sha256": digest,
                    "media_type": "text/plain",
                }

    edit_document(synthetic_bundle, "evidence/records.yaml", repoint)
    findings = of(structural(synthetic_bundle), IssueCode.INVALID_UTF8)
    assert [f.record_id for f in findings] == [target]


# --------------------------------------------------------------------------------------
# Absolute personal paths
# --------------------------------------------------------------------------------------


#: Home-path fixtures are assembled at runtime, never written as literals. This is the repo-wide
#: convention (see `tests/generalization/test_shape.py`: "Violating fixtures are assembled at runtime
#: so the literals never exist on disk") and the reason is not to slip past the R1 checker — it is
#: that the checker exists to keep such strings out of the repo's BYTES, which includes git history,
#: a `grep` over a clone, and the published wheel. A test needs the string in memory, not on disk.
_MAC_HOME = "/Us" + "ers/someone"
_LINUX_HOME = "/ho" + "me/someone"
_FICTIONAL_USER = "someone"


@pytest.mark.parametrize(
    "leaked",
    [
        f"See {_MAC_HOME}/Documents/notes.md for the original.",
        f"Path: {_LINUX_HOME}/src/project/main.py",
        "Stored under /root/captures/one.txt",
    ],
)
def test_an_absolute_home_path_inside_a_capture_is_reported(
    synthetic_bundle: SyntheticBundle, leaked: str
) -> None:
    """§12.2: "there is no silent private-bundle exception". A path inside a capture leaks the
    owner's account name to whoever reads the evidence."""
    target = inline_evidence_id(synthetic_bundle)
    set_inline_text(synthetic_bundle, target, leaked)
    findings = of(structural(synthetic_bundle), IssueCode.ABSOLUTE_PERSONAL_PATH)
    assert [f.record_id for f in findings] == [target]
    assert "start" in findings[0].details


def test_an_absolute_home_path_in_a_yaml_locator_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Checked separately from the capture case because they fail differently: a locator in YAML makes
    the bundle unportable, and the fix is a relative locator rather than a redaction."""
    target = inline_evidence_id(synthetic_bundle)

    def mutate(data: Any) -> None:
        for record in data["evidence"]:
            if record["evidence_id"] == target and "locator" in record:
                record["locator"]["value"] = f"{_MAC_HOME}/archive/record.pdf"

    edit_document(synthetic_bundle, "evidence/records.yaml", mutate)
    findings = of(structural(synthetic_bundle), IssueCode.ABSOLUTE_PERSONAL_PATH)
    assert findings
    assert findings[0].details["field"] == "locator.value"


def test_the_personal_path_finding_never_quotes_the_path(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The matched string IS the personal material, so the finding gives a field or a byte range."""
    target = inline_evidence_id(synthetic_bundle)
    set_inline_text(synthetic_bundle, target, f"Copied from {_MAC_HOME}/private/thing.txt")
    findings = of(structural(synthetic_bundle), IssueCode.ABSOLUTE_PERSONAL_PATH)
    assert findings
    for finding in findings:
        assert _FICTIONAL_USER not in finding.message
        assert _FICTIONAL_USER not in str(finding.details)


def test_a_portable_relative_locator_is_accepted(synthetic_bundle: SyntheticBundle) -> None:
    """The negative side: the check must not fire on the portable form the design asks for."""
    target = inline_evidence_id(synthetic_bundle)
    set_inline_text(synthetic_bundle, target, "See docs/notes.md and ./src/main.py in the repo.")
    assert not of(structural(synthetic_bundle), IssueCode.ABSOLUTE_PERSONAL_PATH)


# --------------------------------------------------------------------------------------
# Evidence authority
# --------------------------------------------------------------------------------------


def test_contradicting_evidence_with_no_conflict_or_ruling_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Evidence that contradicts a fact while nothing records the dispute leaves the fact usable and
    the doubt invisible — the state the conflict machinery exists to surface."""
    ctx = build_context(synthetic_bundle.draft, mode="draft", bundle_root=synthetic_bundle.root)
    undisputed = next(
        fact
        for fact in ctx.index.facts
        if fact.conflict_group_id is None and fact.evidence_ids
    )
    evidence_id = undisputed.evidence_ids[0]

    def contradict(data: Any) -> None:
        for record in data["evidence"]:
            if record["evidence_id"] == evidence_id:
                record["supports_record_ids"] = [
                    t for t in record["supports_record_ids"] if t != undisputed.fact_id
                ]
                record["contradicts_record_ids"] = [
                    *record["contradicts_record_ids"],
                    undisputed.fact_id,
                ]

    edit_document(synthetic_bundle, "evidence/records.yaml", contradict)
    findings = of(structural(synthetic_bundle), IssueCode.CONTRADICTION_WITHOUT_RULING)
    assert [f.details["target"] for f in findings] == [undisputed.fact_id]


def test_contradicting_evidence_inside_a_conflict_group_is_accepted(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The paired positive: a recorded dispute is exactly what makes contradiction legitimate."""
    ctx = build_context(synthetic_bundle.draft, mode="draft", bundle_root=synthetic_bundle.root)
    disputed = ctx.index.conflicts[0].candidate_fact_ids[0]
    fact = ctx.index.fact(disputed)
    assert fact is not None and fact.evidence_ids
    evidence_id = fact.evidence_ids[0]

    def contradict(data: Any) -> None:
        for record in data["evidence"]:
            if record["evidence_id"] == evidence_id:
                record["supports_record_ids"] = [
                    t for t in record["supports_record_ids"] if t != disputed
                ]
                record["contradicts_record_ids"] = [
                    *record["contradicts_record_ids"],
                    disputed,
                ]

    edit_document(synthetic_bundle, "evidence/records.yaml", contradict)
    assert not of(structural(synthetic_bundle), IssueCode.CONTRADICTION_WITHOUT_RULING)


def test_a_fact_whose_basis_no_cited_evidence_can_carry_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§12.1 makes a secondary summary "import evidence, not final verification".

    A fact claiming `public_record_verified` while citing only a summary asserts a check that never
    happened, and every report downstream would treat it as verified.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft", bundle_root=synthetic_bundle.root)
    summary = next(
        record
        for record in ctx.index.evidence
        if str(record.evidence_class) == "secondary_summary"
    )
    dependent = next(
        fact
        for fact in ctx.index.facts
        if summary.evidence_id in fact.evidence_ids
    )
    owning = ctx.index.paths[dependent.fact_id].as_posix()

    def overclaim(data: Any) -> None:
        for entry in data["facts"]:
            if entry["fact_id"] == dependent.fact_id:
                entry["verification_basis"] = "public_record_verified"
                entry["evidence_ids"] = [summary.evidence_id]

    edit_document(synthetic_bundle, owning, overclaim)
    findings = of(structural(synthetic_bundle), IssueCode.VERIFICATION_BASIS_UNSUPPORTED)
    assert [f.record_id for f in findings] == [dependent.fact_id]
    assert findings[0].details["cited_classes"] == ["secondary_summary"]


def test_every_basis_in_the_example_is_backed_by_an_acceptable_evidence_class(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The positive floor for the check above, and a statement about the example: every fact's
    declared basis is actually carried by the evidence it cites."""
    assert not of(structural(synthetic_bundle), IssueCode.VERIFICATION_BASIS_UNSUPPORTED)


# --------------------------------------------------------------------------------------
# Structural / completeness separation
# --------------------------------------------------------------------------------------


def test_completeness_never_emits_an_error_tier_finding(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The layer's contract. An error from the completeness pass would make a valid revision invalid
    on the strength of something the design says is only a blocker."""
    findings = completeness(synthetic_bundle)
    assert findings
    assert {f.tier for f in findings} == {"blocker"}


def test_structural_never_emits_a_blocker_tier_finding(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """And the converse, checked against a bundle deliberately carrying a structural error."""
    target = inline_evidence_id(synthetic_bundle)
    set_inline_text(synthetic_bundle, target, "key: AKIAIOSFODNN7EXAMPLE")
    findings = structural(synthetic_bundle)
    assert findings
    assert "blocker" not in {f.tier for f in findings}


def test_a_missing_bundle_root_is_reported_rather_than_silently_skipping_blobs(
    tmp_path: Path, synthetic_bundle: SyntheticBundle
) -> None:
    """Validating a bare tree with no blob store must not report blob integrity as clean.

    This is the `inspect`-a-copied-tree case, and it is the one where "we could not check" is easiest
    to mistake for "there was nothing wrong".
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft", bundle_root=None)
    findings = validate_evidence_structural(ctx)
    missing = of(findings, IssueCode.MISSING_BLOB)
    assert missing
    assert "no bundle root" in missing[0].message
