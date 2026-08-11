"""Structural validation: the tree's shape, and every record addressable exactly once.

Each negative case is produced by editing the comprehensive example, not by hand-writing a broken
tree, so a check cannot pass because the fixture drifted away from what production reads. The
mutations go through the restricted loader and back out through PyYAML, which means a mutation that
produces unparseable YAML fails loudly here instead of silently testing nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from boardwatch.profile_bundle.errors import IssueCode
from boardwatch.profile_bundle.index import build_index, prefix_matches_kind, record_id_of
from boardwatch.profile_bundle.validation import (
    BundleParseError,
    build_context,
    validate_structural,
)
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import SyntheticBundle, blob_reader


class _NoAliasDumper(yaml.SafeDumper):
    """PyYAML emits anchors for shared objects, and the restricted loader refuses them.

    A mutation that produced an anchor would fail to load, and the test would report the loader's
    refusal instead of the condition it meant to exercise.
    """

    def ignore_aliases(self, data: Any) -> bool:  # noqa: ANN401 - PyYAML's own signature
        return True


def edit_document(
    bundle: SyntheticBundle, relative: str, mutate: Callable[[Any], None]
) -> None:
    """Round-trip one document through the restricted loader, mutate it, and write it back.

    Read through `load_yaml_bytes` rather than `yaml.safe_load` on purpose: the restricted loader
    hands back dates and times as strings, so re-dumping them cannot turn an authored `'2026-08-10'`
    into a YAML 1.1 timestamp that the loader would then refuse on the way back in.
    """
    data = load_yaml_bytes(
        bundle.document(relative).read_bytes(), logical_path=Path(relative).as_posix()
    )
    mutate(data)
    bundle.write(
        relative,
        yaml.dump(
            data,
            Dumper=_NoAliasDumper,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
            width=100,
        ),
    )


def structural_findings(bundle: SyntheticBundle) -> tuple[Any, ...]:
    ctx = build_context(
        bundle.draft, mode="draft", blobs=blob_reader(), bundle_root=bundle.root
    )
    return validate_structural(ctx)


def codes(findings: tuple[Any, ...]) -> list[str]:
    return sorted(finding.code for finding in findings)


# --------------------------------------------------------------------------------------
# The clean case
# --------------------------------------------------------------------------------------


def test_the_comprehensive_example_has_no_structural_findings(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The floor for every negative case below: without this, they prove nothing."""
    assert structural_findings(synthetic_bundle) == ()


def test_every_record_in_the_example_is_indexed_exactly_once(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Counted a second way: the index's own collision list must be empty, and the flat record map
    must hold as many entries as the per-kind lists do in total."""
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    assert ctx.index.collisions == ()
    per_kind = sum(len(records) for records in ctx.index.by_kind.values())
    assert len(ctx.index.records) == per_kind


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"value: \xff\n", IssueCode.INVALID_UTF8),
        (b"value: [unclosed\n", IssueCode.INVALID_YAML),
        (b"value: yes\n", IssueCode.RESTRICTED_YAML_VIOLATION),
    ],
)
def test_yaml_failure_keeps_its_raise_site_code(
    synthetic_bundle: SyntheticBundle,
    body: bytes,
    expected: IssueCode,
) -> None:
    relative = "facts/identity.yaml"
    synthetic_bundle.document(relative).write_bytes(body)

    with pytest.raises(BundleParseError) as excinfo:
        build_context(synthetic_bundle.draft, mode="draft")

    matching = [
        finding
        for finding in excinfo.value.diagnostics
        if finding.path == relative and finding.code == expected
    ]
    assert len(matching) == 1


def test_the_index_dispatches_on_record_type_not_field_name(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`policy/relations.yaml` has a `relations` field of catalog rows and `policy/sources.yaml` a
    `sources` field; neither may enter the record index.

    This is a regression guard with a history: name-based dispatch indexed those catalog rows as
    records, and the example — which is correct — reported duplicate IDs and a wrong owning file.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    catalog = ctx.index.relation_catalog
    assert catalog is not None and catalog.relations, "the example must exercise the hazard"
    for spec in catalog.relations:
        assert spec.relation_type not in ctx.index.records
    # The ledger's per-source blocks are keyed by a catalogued source ID; the catalog owns it.
    ledger = ctx.index.source_ledger
    assert ledger is not None and ledger.sources
    for used in ledger.sources:
        assert ctx.index.paths[used.source_id].as_posix() == "policy/sources.yaml"


# --------------------------------------------------------------------------------------
# Missing declared documents
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    ["policy/units.yaml", "metrics/records.yaml", "history/changes.yaml"],
)
def test_a_deleted_declared_document_is_reported(
    synthetic_bundle: SyntheticBundle, relative: str
) -> None:
    """An absent catalog is not an empty one, so absence must be a finding rather than a default."""
    synthetic_bundle.document(relative).unlink()
    findings = structural_findings(synthetic_bundle)
    missing = [
        finding
        for finding in findings
        if finding.code == IssueCode.MISSING_REQUIRED_FILE and finding.path == relative
    ]
    assert len(missing) == 1


def test_a_missing_catalog_does_not_silently_pass_its_version_check(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Deleting `policy/units.yaml` must report the missing file, and must NOT also report a
    catalog-version mismatch — a second finding about the same cause would send the operator to fix
    the manifest instead of restoring the file."""
    synthetic_bundle.document("policy/units.yaml").unlink()
    assert codes(structural_findings(synthetic_bundle)) == [IssueCode.MISSING_REQUIRED_FILE]


# --------------------------------------------------------------------------------------
# Global ID uniqueness
# --------------------------------------------------------------------------------------


def test_the_same_fact_id_in_two_documents_is_a_duplicate(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Facts legitimately live in many files, which is exactly why the ID index must be global.

    The copied fact is appended to `facts/awards.yaml`, so the finding names both owning paths.
    """
    identity = load_yaml_bytes(
        synthetic_bundle.document("facts/identity.yaml").read_bytes(),
        logical_path="facts/identity.yaml",
    )
    assert isinstance(identity, dict)
    borrowed = identity["facts"][0]

    def append(data: Any) -> None:
        data["facts"].append(borrowed)

    edit_document(synthetic_bundle, "facts/awards.yaml", append)
    findings = structural_findings(synthetic_bundle)
    duplicates = [f for f in findings if f.code == IssueCode.DUPLICATE_RECORD_ID]
    assert len(duplicates) == 1
    assert duplicates[0].record_id == borrowed["fact_id"]
    # Both owning paths are named. Which one is "first" follows the tree's sorted iteration order
    # rather than which file is the original, so the pair is asserted as a set: the operator needs
    # both filenames, and pinning the order would pin an implementation detail of the walk.
    assert {duplicates[0].details["first_path"], duplicates[0].path} == {
        "facts/identity.yaml",
        "facts/awards.yaml",
    }


def test_a_duplicate_id_does_not_stop_the_index_from_finding_the_next_one(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Two collisions must both be reported. An index that raised on the first would hide the
    second, and the operator would fix one and rerun."""
    identity = load_yaml_bytes(
        synthetic_bundle.document("facts/identity.yaml").read_bytes(),
        logical_path="facts/identity.yaml",
    )
    assert isinstance(identity, dict)
    first, second = identity["facts"][0], identity["facts"][1]

    edit_document(
        synthetic_bundle, "facts/awards.yaml", lambda data: data["facts"].append(first)
    )
    edit_document(
        synthetic_bundle, "facts/courses.yaml", lambda data: data["facts"].append(second)
    )
    duplicates = [
        f for f in structural_findings(synthetic_bundle) if f.code == IssueCode.DUPLICATE_RECORD_ID
    ]
    assert sorted(f.record_id for f in duplicates) == sorted(
        [first["fact_id"], second["fact_id"]]
    )


# --------------------------------------------------------------------------------------
# Entity-owned files
# --------------------------------------------------------------------------------------


def test_an_entity_file_whose_basename_disagrees_with_its_entity_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§7 builds the digest leaf key from the path, so a basename and an entity ID that disagree
    would give one entity two identities depending on which a reader trusted."""
    projects = sorted(synthetic_bundle.document("facts/projects").iterdir())
    target = projects[0].relative_to(synthetic_bundle.draft).as_posix()
    renamed = projects[0].with_name("project.renamed-elsewhere.yaml")
    projects[0].rename(renamed)

    findings = structural_findings(synthetic_bundle)
    mismatches = [f for f in findings if f.code == IssueCode.BASENAME_ID_MISMATCH]
    assert len(mismatches) == 1
    assert mismatches[0].details["basename_declares"] == "project.renamed-elsewhere"
    assert mismatches[0].path == renamed.relative_to(synthetic_bundle.draft).as_posix()
    assert target != mismatches[0].path


def test_a_fact_filed_away_from_its_subject_is_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§6: an entity-owned file also owns its subject's atomic facts.

    Moving an education fact into `facts/awards.yaml` leaves the record's own bytes untouched and
    changes only which digest leaf carries it — the failure mode this check exists for.
    """
    education = load_yaml_bytes(
        synthetic_bundle.document("facts/education.yaml").read_bytes(),
        logical_path="facts/education.yaml",
    )
    assert isinstance(education, dict)
    moved = education["facts"][0]

    edit_document(
        synthetic_bundle,
        "facts/education.yaml",
        lambda data: data["facts"].remove(moved),
    )
    edit_document(
        synthetic_bundle, "facts/awards.yaml", lambda data: data["facts"].append(moved)
    )

    findings = structural_findings(synthetic_bundle)
    misfiled = [f for f in findings if f.code == IssueCode.WRONG_OWNING_FILE]
    assert len(misfiled) == 1
    assert misfiled[0].record_id == moved["fact_id"]
    assert misfiled[0].path == "facts/awards.yaml"
    assert misfiled[0].details["owning_file"] == "facts/education.yaml"


def test_application_only_facts_may_name_any_subject(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The one exception §6 names. `application/gated-facts.yaml` holds facts about subjects owned
    by other files, and must not be reported for it.

    Asserted against the example's real content rather than a constructed case, so the exemption is
    shown to be exercised: if the example ever stopped carrying a cross-subject gated fact, this
    test would say so instead of passing vacuously.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    gated = ctx.documents.get("application/gated-facts.yaml")
    assert gated is not None
    subjects = {fact.subject_id for fact in gated.facts}  # type: ignore[union-attr]
    elsewhere = {
        subject
        for subject in subjects
        if ctx.index.paths[subject].as_posix() != "application/gated-facts.yaml"
    }
    assert elsewhere, "the example must carry a gated fact about an externally-owned subject"
    assert not [f for f in validate_structural(ctx) if f.code == IssueCode.WRONG_OWNING_FILE]


# --------------------------------------------------------------------------------------
# Manifest / catalog agreement
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("manifest_field", "catalog_path"),
    [
        ("predicate_catalog_version", "policy/predicates.yaml"),
        ("unit_catalog_version", "policy/units.yaml"),
        ("relation_catalog_version", "policy/relations.yaml"),
        ("skill_category_catalog_version", "policy/skill-categories.yaml"),
        ("assertion_tag_catalog_version", "policy/assertion-tags.yaml"),
        ("secret_scan_ruleset_version", "policy/secret-scan.yaml"),
    ],
)
def test_a_manifest_that_pins_the_wrong_catalog_version_is_reported(
    synthetic_bundle: SyntheticBundle, manifest_field: str, catalog_path: str
) -> None:
    """A manifest claiming catalog 7 beside catalog 1 would attribute this revision's clearances to
    rules that never ran. Every pinned version is covered, because a version added to the manifest
    but not to the check would simply stop being verified."""

    def bump(data: Any) -> None:
        data[manifest_field] = data[manifest_field] + 6

    edit_document(synthetic_bundle, "manifest.yaml", bump)
    findings = structural_findings(synthetic_bundle)
    mismatches = [f for f in findings if f.code == IssueCode.CATALOG_VERSION_MISMATCH]
    assert len(mismatches) == 1
    assert mismatches[0].details["catalog_path"] == catalog_path
    assert mismatches[0].details["manifest_declares"] != mismatches[0].details["catalog_declares"]


# --------------------------------------------------------------------------------------
# Record-kind prefixes
# --------------------------------------------------------------------------------------


def test_prefix_matches_kind_accepts_every_indexed_record_in_the_example(
    synthetic_bundle: SyntheticBundle,
) -> None:
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    for kind, records in ctx.index.by_kind.items():
        for record in records:
            assert prefix_matches_kind(record_id_of(record), kind)


@pytest.mark.parametrize(
    ("record_id", "kind", "expected"),
    [
        ("fact.a.001", "fact", True),
        ("fact.a.001", "metric", False),
        ("metric.a.001", "fact", False),
        # All eleven entity prefixes map to the one `entity` kind, so the check is membership.
        ("person.subject", "entity", True),
        ("employment.acme", "entity", True),
        ("project.thing", "entity", True),
        ("fact.a.001", "entity", False),
        # An ID naming no known kind agrees with nothing.
        ("mystery.a.001", "fact", False),
        ("", "fact", False),
    ],
)
def test_prefix_matches_kind_is_exact(record_id: str, kind: str, expected: bool) -> None:
    """Exercised directly because authored YAML cannot reach the check that uses it: every record's
    own ID field is pattern-pinned to its prefix, so a mismatch is refused at parse time. This keeps
    the guard honest for the day a field is widened to a bare `RecordId`."""
    assert prefix_matches_kind(record_id, kind) is expected


# --------------------------------------------------------------------------------------
# Approval sub-entry uniqueness
# --------------------------------------------------------------------------------------


def test_two_stamps_sharing_an_approval_id_are_reported(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§13 makes sub-approval IDs globally unique. Reusing one would let a stamp bound to revision
    N's candidate digest be cited as authority for revision N+1's."""
    stamp = {
        "approval_stamp_id": "approval-stamp.synthetic.001",
        "candidate_content_digest": "sha256:" + "0" * 64,
        "approved_at": "2026-08-10T12:00:00Z",
        "approved_via": "controlling_terminal",
        "entries": [
            {
                "approval_id": "approval.reused.001",
                "action": "approve_evidence_sufficiency",
                "target_record_id": "evidence.example.legacy-summary.001",
                "target_content_digest": "sha256:" + "1" * 64,
                "resulting_state": "owner_approved",
            }
        ],
    }
    second = {
        **stamp,
        "approval_stamp_id": "approval-stamp.synthetic.002",
        "candidate_content_digest": "sha256:" + "2" * 64,
    }

    def add_both(data: Any) -> None:
        data["approvals"] = [stamp, second]

    edit_document(synthetic_bundle, "history/approvals.yaml", add_both)
    findings = structural_findings(synthetic_bundle)
    duplicates = [f for f in findings if f.code == IssueCode.DUPLICATE_APPROVAL_ID]
    assert [f.record_id for f in duplicates] == ["approval.reused.001"]


# --------------------------------------------------------------------------------------
# Diagnostic hygiene
# --------------------------------------------------------------------------------------


def test_structural_diagnostics_sort_deterministically(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Two independent findings, sorted by `(tier, code, path, record_id, message)`.

    A report whose order depended on dict iteration would make two runs of the same bundle produce
    diffable-but-different output, and a reviewer could not tell a new finding from a reordered one.
    """
    synthetic_bundle.document("policy/units.yaml").unlink()
    synthetic_bundle.document("metrics/records.yaml").unlink()
    findings = structural_findings(synthetic_bundle)
    keys = [f.sort_key() for f in sorted(findings, key=lambda d: d.sort_key())]
    assert keys == sorted(keys)
    assert len(findings) == 2


def test_the_index_can_be_rebuilt_from_documents_alone(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """`build_index` is a pure function of the parsed tree: same documents, same index.

    Load-bearing because the promotion path indexes a tree it has already parsed rather than
    re-reading it, and the two must not be able to disagree.
    """
    ctx = build_context(synthetic_bundle.draft, mode="draft")
    rebuilt = build_index(ctx.documents)
    assert sorted(rebuilt.records) == sorted(ctx.index.records)
    assert rebuilt.paths == ctx.index.paths
    assert rebuilt.collisions == ctx.index.collisions
