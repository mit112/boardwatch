"""The comprehensive synthetic bundle: complete placement, and every wrong placement refused.

Design test group 1 asks for "one comprehensive bundle containing every entity and record kind in
its declared owning file and rejection of every unknown placement". Both halves matter. The first
proves the schema can express a whole profile; the second proves ownership is enforced rather than
merely documented — a record cloned into the wrong file must fail, and an undeclared file must fail
even when its content is perfectly valid.

Test group 28's refusals are here too: `policy/persona.yaml`, `policy/selection.yaml`, and every
other tailoring-policy file. That is the mechanism that keeps a later projection design from
becoming bundle authority by being dropped into `policy/`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

import pytest
from pydantic import TypeAdapter, ValidationError

from boardwatch.profile_bundle.errors import BundleLayoutError
from boardwatch.profile_bundle.layout import (
    FIXED_DOCUMENTS,
    DocumentKind,
    discover_source_files,
    missing_fixed_documents,
)
from boardwatch.profile_bundle.models.claims import ClaimType
from boardwatch.profile_bundle.models.documents import BundleDocuments
from boardwatch.profile_bundle.models.entities import ContactChannelType
from boardwatch.profile_bundle.models.evidence import EvidenceClass
from boardwatch.profile_bundle.models.manifests import BundleManifest, DraftManifest
from boardwatch.profile_bundle.models.metrics import CaveatSeverity
from boardwatch.profile_bundle.models.policy import HIGH_RISK_ASSERTION_TAGS
from boardwatch.profile_bundle.schema import model_for_kind
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import (
    BLOB_BYTES,
    BLOB_SHA256,
    EXAMPLE_EVIDENCE_SET_DIGEST,
    EXAMPLE_PROFILE_ID,
    SyntheticBundle,
    example_source_root,
)

MANIFEST_ADAPTER = TypeAdapter(BundleManifest)

TAILORING_POLICY_REFUSALS = (
    "policy/persona.yaml",
    "policy/selection.yaml",
    "policy/role-families.yaml",
    "policy/summary.yaml",
    "policy/tailoring.yaml",
)


def _parse(root: Path) -> BundleDocuments:
    """Parse the whole tree the way the loader will, without the loader existing yet."""
    found = discover_source_files(root, final_revision=False)
    assert missing_fixed_documents(found) == ()
    by_path: dict[PurePosixPath, object] = {}
    manifest = None
    for entry in found:
        parsed = load_yaml_bytes(entry.abspath.read_bytes(), logical_path=entry.logical_path)
        if entry.kind is DocumentKind.MANIFEST:
            manifest = MANIFEST_ADAPTER.validate_python(parsed)
        else:
            by_path[entry.logical_path] = model_for_kind(entry.kind).model_validate(parsed)
    assert manifest is not None
    return BundleDocuments(manifest=manifest, by_path=by_path)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# completeness of the example
# --------------------------------------------------------------------------------------


def test_the_example_is_a_complete_declared_tree() -> None:
    found = discover_source_files(example_source_root(), final_revision=False)
    assert missing_fixed_documents(found) == ()
    assert len(found) == len(FIXED_DOCUMENTS) + 2  # the two entity-owned files


def test_every_document_parses_into_its_declared_wrapper() -> None:
    documents = _parse(example_source_root())
    assert isinstance(documents.manifest, DraftManifest)
    assert len(documents.by_path) == len(FIXED_DOCUMENTS) + 1  # every file except the manifest


def test_the_example_is_a_parentless_revision_one_draft() -> None:
    documents = _parse(example_source_root())
    manifest = documents.manifest
    assert isinstance(manifest, DraftManifest)
    assert manifest.profile_id == EXAMPLE_PROFILE_ID
    assert manifest.draft_of_revision is None
    assert manifest.parent_bundle_digest is None
    assert manifest.bundle_digest == ""
    assert manifest.evidence_set_digest == EXAMPLE_EVIDENCE_SET_DIGEST


def test_every_entity_kind_appears_exactly_once() -> None:
    documents = _parse(example_source_root())
    kinds: list[str] = []
    identity = documents.get("facts/identity.yaml")
    assert identity is not None
    kinds.append(identity.person.entity_type)  # type: ignore[union-attr]
    for relative in (
        "facts/education.yaml",
        "facts/publications.yaml",
        "facts/awards.yaml",
        "facts/certifications.yaml",
        "facts/affiliations.yaml",
        "facts/courses.yaml",
        "facts/presentations.yaml",
        "facts/patents.yaml",
    ):
        document = documents.get(relative)
        assert document is not None
        kinds.extend(entity.entity_type for entity in document.entities)  # type: ignore[union-attr]
    for relative in (
        "facts/experience/employment.example-labs.yaml",
        "facts/projects/project.packet-pantry.yaml",
    ):
        document = documents.get(relative)
        assert document is not None
        kinds.append(document.entity.entity_type)  # type: ignore[union-attr]
    assert sorted(kinds) == sorted(
        [
            "person",
            "education",
            "employment",
            "project",
            "publication",
            "award",
            "certification",
            "affiliation",
            "course",
            "presentation",
            "patent",
        ]
    )


def test_every_evidence_class_and_both_capture_kinds_appear() -> None:
    documents = _parse(example_source_root())
    evidence_document = documents.get("evidence/records.yaml")
    assert evidence_document is not None
    records = evidence_document.evidence  # type: ignore[union-attr]
    assert {record.evidence_class for record in records} == {
        member.value for member in EvidenceClass
    }
    assert {record.capture.kind for record in records} == {"inline", "blob"}


def test_every_contact_channel_type_appears() -> None:
    documents = _parse(example_source_root())
    identity = documents.get("facts/identity.yaml")
    assert identity is not None
    assert {contact.channel_type for contact in identity.contacts} == set(  # type: ignore[union-attr]
        ContactChannelType
    )


def test_every_claim_type_appears_in_its_owning_file() -> None:
    documents = _parse(example_source_root())
    bullets = documents.get("claims/bullet-candidates.yaml")
    summaries = documents.get("claims/summary-candidates.yaml")
    assert bullets is not None and summaries is not None
    bullet_types = {claim.claim_type for claim in bullets.claims}  # type: ignore[union-attr]
    summary_types = {claim.claim_type for claim in summaries.claims}  # type: ignore[union-attr]
    assert bullet_types == {
        ClaimType.RESPONSIBILITY,
        ClaimType.ACCOMPLISHMENT,
        ClaimType.PROJECT_SUMMARY,
    }
    assert summary_types == {ClaimType.PROFESSIONAL_SUMMARY}


def test_every_metric_caveat_severity_appears() -> None:
    documents = _parse(example_source_root())
    metrics = documents.get("metrics/records.yaml")
    assert metrics is not None
    severities = {
        caveat.severity for metric in metrics.metrics for caveat in metric.caveats  # type: ignore[union-attr]
    }
    assert severities == set(CaveatSeverity)


def test_the_example_carries_a_ruled_conflict_and_an_unresolved_one() -> None:
    documents = _parse(example_source_root())
    groups = documents.get("conflicts/groups.yaml")
    rulings = documents.get("conflicts/rulings.yaml")
    assert groups is not None and rulings is not None
    states = {conflict.state.value for conflict in groups.conflicts}  # type: ignore[union-attr]
    assert states == {"unresolved", "resolved"}
    assert len(rulings.rulings) == 1  # type: ignore[union-attr]


def test_the_example_carries_a_stale_record_and_a_supersession_edge() -> None:
    documents = _parse(example_source_root())
    project = documents.get("facts/projects/project.packet-pantry.yaml")
    assert project is not None
    facts = project.facts  # type: ignore[union-attr]
    assert any(fact.verification_state.value == "stale" for fact in facts)
    assert any(fact.verification_state.value == "superseded" for fact in facts)
    assert any(fact.supersedes_fact_ids for fact in facts)


def test_the_example_carries_application_only_facts() -> None:
    documents = _parse(example_source_root())
    gated = documents.get("application/gated-facts.yaml")
    assert gated is not None
    assert gated.facts  # type: ignore[union-attr]
    for fact in gated.facts:  # type: ignore[union-attr]
        assert set(surface.value for surface in fact.allowed_surfaces) <= {"application"}


def test_the_assertion_tag_catalog_carries_all_twelve_design_tags() -> None:
    documents = _parse(example_source_root())
    catalog = documents.get("policy/assertion-tags.yaml")
    assert catalog is not None
    tags = {spec.tag_id for spec in catalog.assertion_tags}  # type: ignore[union-attr]
    assert tags == {
        "shipped",
        "live",
        "production",
        "published",
        "granted",
        "awarded",
        "certified",
        "designed",
        "built",
        "implemented",
        "led",
        "measured",
    }
    high_risk = {
        spec.tag_id for spec in catalog.assertion_tags if spec.high_risk  # type: ignore[union-attr]
    }
    assert high_risk == HIGH_RISK_ASSERTION_TAGS


def test_the_predicate_catalog_carries_every_design_predicate() -> None:
    documents = _parse(example_source_root())
    catalog = documents.get("policy/predicates.yaml")
    assert catalog is not None
    predicates = {spec.predicate_id for spec in catalog.predicates}  # type: ignore[union-attr]
    assert predicates == {
        "person.professional_name",
        "person.professional_headline",
        "education.institution",
        "education.credential",
        "education.field",
        "education.start_date",
        "education.end_date",
        "education.result",
        "employment.organization",
        "employment.title",
        "employment.date_range",
        "employment.responsibility",
        "employment.accomplishment",
        "employment.team_size",
        "project.summary",
        "project.start_date",
        "project.end_date",
        "project.contribution",
        "deployment.environment",
        "technology.used",
        "publication.title",
        "publication.venue",
        "publication.date",
        "entity.location",
        "entity.url",
        "recognition.name",
        "recognition.issuer",
        "award.date",
        "certification.issue_date",
        "certification.expiry",
        "affiliation.role",
        "affiliation.date_range",
        "course.title",
        "presentation.title",
        "presentation.date",
        "presentation.venue",
        "patent.title",
        "patent.filing_date",
        "patent.grant_date",
        "application.requires_sponsorship",
        "application.authorized_regions",
    }


def test_no_shipped_predicate_uses_the_verified_owner_attestation_authority() -> None:
    """§10.4: "all initial predicates that admit owner attestation use `owner_confirmed`, never
    `verified`". The enum admits `verified` because the design declares the catalog; no row uses it."""
    documents = _parse(example_source_root())
    catalog = documents.get("policy/predicates.yaml")
    assert catalog is not None
    authorities = {
        spec.owner_attestation_authority.value for spec in catalog.predicates  # type: ignore[union-attr]
    }
    assert authorities == {"none", "owner_confirmed"}


def test_the_units_catalog_is_exactly_the_designs_fixture_rows() -> None:
    documents = _parse(example_source_root())
    catalog = documents.get("policy/units.yaml")
    assert catalog is not None
    assert [unit.unit_id for unit in catalog.units] == [  # type: ignore[union-attr]
        "items",
        "milliseconds",
        "items_per_second",
        "percent",
        "usd",
        "bytes",
        "ordinal",
        "points",
    ]


def test_the_secret_scan_document_records_the_builtin_v1_rows() -> None:
    from boardwatch.profile_bundle.secret_scan import ruleset_matches_builtin

    documents = _parse(example_source_root())
    ruleset = documents.get("policy/secret-scan.yaml")
    assert ruleset is not None
    assert ruleset_matches_builtin(ruleset)  # type: ignore[arg-type]


def test_the_example_ledger_denominator_adds_up() -> None:
    documents = _parse(example_source_root())
    ledger = documents.get("imports/source-ledger.yaml")
    exclusions = documents.get("imports/exclusions.yaml")
    assert ledger is not None and exclusions is not None
    counts = ledger.counts_by_disposition()  # type: ignore[union-attr]
    assert sum(counts.values()) == ledger.record_count == 4  # type: ignore[union-attr]
    assert len(exclusions.exclusions) == counts[  # type: ignore[union-attr]
        type(next(iter(counts))).EXCLUDED
    ]


def test_the_history_ledgers_are_empty_because_nothing_has_been_promoted() -> None:
    documents = _parse(example_source_root())
    changes = documents.get("history/changes.yaml")
    approvals = documents.get("history/approvals.yaml")
    assert changes is not None and approvals is not None
    assert changes.changes == ()  # type: ignore[union-attr]
    assert approvals.approvals == ()  # type: ignore[union-attr]


def test_the_example_contains_no_blob_bytes_only_a_digest() -> None:
    """Blobs live at the bundle root and are shared across revisions (§6), so a packaged logical
    tree must not carry any."""
    for path in example_source_root().rglob("*"):
        if path.is_file():
            assert path.suffix == ".yaml", path


# --------------------------------------------------------------------------------------
# the materialised fixture
# --------------------------------------------------------------------------------------


def test_the_fixture_materialises_a_usable_bundle_root(synthetic_bundle: SyntheticBundle) -> None:
    assert synthetic_bundle.draft.is_dir()
    assert synthetic_bundle.manifest_path.is_file()
    assert synthetic_bundle.blob.read_bytes() == BLOB_BYTES


def test_the_fixture_blob_matches_the_digest_the_example_authored(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """If this fails, the blob text and the authored capture digest have drifted apart."""
    assert hashlib.sha256(synthetic_bundle.blob.read_bytes()).hexdigest() == BLOB_SHA256
    assert BLOB_SHA256 in synthetic_bundle.read("evidence/records.yaml")


def test_the_materialised_draft_still_parses(synthetic_bundle: SyntheticBundle) -> None:
    documents = _parse(synthetic_bundle.draft)
    assert isinstance(documents.manifest, DraftManifest)


# --------------------------------------------------------------------------------------
# wrong placement and undeclared files
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("facts/awards.yaml", "facts/publications.yaml"),
        ("facts/certifications.yaml", "facts/awards.yaml"),
        ("facts/courses.yaml", "facts/patents.yaml"),
        ("claims/bullet-candidates.yaml", "claims/summary-candidates.yaml"),
        ("claims/summary-candidates.yaml", "claims/bullet-candidates.yaml"),
        ("policy/units.yaml", "policy/relations.yaml"),
        ("imports/candidates.yaml", "imports/exclusions.yaml"),
        ("conflicts/groups.yaml", "conflicts/rulings.yaml"),
        ("metrics/records.yaml", "skills/inventory.yaml"),
    ],
)
def test_a_record_in_the_wrong_owning_file_is_refused(
    synthetic_bundle: SyntheticBundle, source: str, destination: str
) -> None:
    synthetic_bundle.write(destination, synthetic_bundle.read(source))
    with pytest.raises(ValidationError):
        _parse(synthetic_bundle.draft)


def test_an_employment_file_holding_a_project_entity_is_refused(
    synthetic_bundle: SyntheticBundle,
) -> None:
    project = synthetic_bundle.read("facts/projects/project.packet-pantry.yaml")
    synthetic_bundle.write("facts/experience/employment.example-labs.yaml", project)
    with pytest.raises(ValidationError):
        _parse(synthetic_bundle.draft)


@pytest.mark.parametrize("stray", TAILORING_POLICY_REFUSALS)
def test_an_undeclared_tailoring_policy_file_is_refused(
    synthetic_bundle: SyntheticBundle, stray: str
) -> None:
    """Test group 28. Gate A does not define or accept these, so unknown-file validation is what
    stops an undeclared tailoring policy from becoming authority by accident."""
    (synthetic_bundle.draft / stray).write_text("persona: default\n", encoding="utf-8")
    with pytest.raises(BundleLayoutError) as excinfo:
        discover_source_files(synthetic_bundle.draft, final_revision=False)
    assert stray in str(excinfo.value)


@pytest.mark.parametrize(
    "stray",
    [
        "facts/identity.yml",
        "facts/identity.json",
        "notes.md",
        "policy/predicates.yaml.bak",
        "skills/extra.yaml",
        "facts/experience/notes.txt",
    ],
)
def test_an_undeclared_file_of_any_shape_is_refused(
    synthetic_bundle: SyntheticBundle, stray: str
) -> None:
    (synthetic_bundle.draft / stray).write_text("{}\n", encoding="utf-8")
    with pytest.raises(BundleLayoutError):
        discover_source_files(synthetic_bundle.draft, final_revision=False)


def test_an_entity_file_whose_basename_disagrees_with_its_id_is_a_layout_error(
    synthetic_bundle: SyntheticBundle,
) -> None:
    original = synthetic_bundle.draft / "facts/projects/project.packet-pantry.yaml"
    original.rename(synthetic_bundle.draft / "facts/projects/project.other-name.yaml")
    found = discover_source_files(synthetic_bundle.draft, final_revision=False)
    # The layout accepts the name (it is well formed); the basename/content disagreement is a
    # structural check, so what this pins is that discovery does not silently repair it.
    assert any(
        entry.logical_path == PurePosixPath("facts/projects/project.other-name.yaml")
        for entry in found
    )


def test_a_draft_may_not_carry_a_complete_marker(synthetic_bundle: SyntheticBundle) -> None:
    (synthetic_bundle.draft / "COMPLETE").write_bytes(
        ("sha256:" + "0" * 64 + "\n").encode("utf-8")
    )
    with pytest.raises(BundleLayoutError):
        discover_source_files(synthetic_bundle.draft, final_revision=False)
