"""Canonical identity: what changes a digest, and what must never change one (design §7).

Both halves are the test. A digest that moved when YAML formatting changed would make every
content-addressed directory name depend on the editor that last touched the file; a digest that did
NOT move when a fact changed would make the whole scheme decorative.

The properties pinned here:

- **Insensitive:** mapping-key order, YAML block-vs-flow style, indentation, comments, the bundle's
  location on disk, Unicode composition, and the root-only `local-sources.yaml`.
- **Sensitive:** list order, any record's content, the evidence document, blob bytes.
- **Structural:** leaf keys are `doc:<path>` and `blob:sha256:<digest>` — never a delimiter-joined
  string — and every leaf digest is lowercase `sha256:<64-hex>`.
"""

from __future__ import annotations

import hashlib
import shutil
import unicodedata
from pathlib import Path

import pytest

from boardwatch.profile_bundle.canonical import (
    BLOB_KEY_PREFIX,
    DOCUMENT_KEY_PREFIX,
    CanonicalizationError,
    MappingBlobReader,
    MissingBlobError,
    bundle_digest,
    candidate_content_digest,
    canonical_json_bytes,
    digest_of,
    evidence_set_digest,
    leaf_index,
    record_digest,
    referenced_blob_digests,
)
from boardwatch.profile_bundle.models.metrics import MetricRecord
from boardwatch.profile_bundle.models.sidecars import LocalSourcesSidecar
from boardwatch.profile_bundle.paths import local_sources_path
from tests.profile_bundle.conftest import (
    BLOB_BYTES,
    BLOB_SHA256,
    EXAMPLE_EVIDENCE_SET_DIGEST,
    SyntheticBundle,
    blob_reader,
    example_source_root,
    parse_documents,
)

DIGEST_RE_LENGTH = len("sha256:") + 64


# --------------------------------------------------------------------------------------
# the serializer itself
# --------------------------------------------------------------------------------------


def test_canonical_bytes_are_sorted_compact_and_non_ascii_literal() -> None:
    assert canonical_json_bytes({"b": 1, "a": "café"}) == '{"a":"café","b":1}'.encode()


def test_nfc_and_decomposed_spellings_canonicalise_identically() -> None:
    composed = "Zürich"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    assert canonical_json_bytes(composed) == canonical_json_bytes(decomposed)
    assert digest_of({"k": composed}) == digest_of({"k": decomposed})


def test_mapping_key_order_is_irrelevant_and_list_order_is_not() -> None:
    assert digest_of({"a": 1, "b": 2}) == digest_of({"b": 2, "a": 1})
    assert digest_of(["a", "b"]) != digest_of(["b", "a"])


def test_a_float_is_refused_rather_than_rounded() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_json_bytes({"n": 0.1})
    with pytest.raises(CanonicalizationError):
        canonical_json_bytes({"n": float("nan")})
    with pytest.raises(CanonicalizationError):
        canonical_json_bytes({"n": float("inf")})


def test_a_non_string_mapping_key_is_refused() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_json_bytes({1: "one"})


def test_an_uncanonicalisable_type_is_refused_rather_than_coerced() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_json_bytes({"when": object()})


def test_booleans_stay_json_booleans_and_integers_stay_base_ten() -> None:
    assert canonical_json_bytes({"t": True, "n": 10}) == b'{"n":10,"t":true}'


def test_every_digest_uses_the_one_lowercase_textual_form() -> None:
    value = digest_of({"a": 1})
    assert value.startswith("sha256:")
    assert len(value) == DIGEST_RE_LENGTH
    assert value.islower()


def test_dates_and_timestamps_are_iso_8601_strings() -> None:
    """Pydantic's JSON mode is the boundary; identity must never see a `datetime` object."""
    metric = parse_documents(example_source_root()).get("metrics/records.yaml")
    assert metric is not None
    payload = metric.metrics[0].model_dump(mode="json")  # type: ignore[union-attr]
    assert payload["reviewed_at"] == "2026-08-10"
    evidence = parse_documents(example_source_root()).get("evidence/records.yaml")
    assert evidence is not None
    captured = evidence.evidence[0].model_dump(mode="json")["captured_at"]  # type: ignore[union-attr]
    assert captured == "2026-08-10T12:00:00Z"


def test_record_digest_is_computed_before_approval_metadata_exists() -> None:
    """A target digest binds the record itself; nothing in a record points at its approval."""
    documents = parse_documents(example_source_root())
    metrics = documents.get("metrics/records.yaml")
    assert metrics is not None
    metric = metrics.metrics[0]  # type: ignore[union-attr]
    assert isinstance(metric, MetricRecord)
    assert record_digest(metric) == digest_of(metric.model_dump(mode="json"))
    assert "approval_id" not in type(metric).model_fields


# --------------------------------------------------------------------------------------
# evidence set
# --------------------------------------------------------------------------------------


def test_the_evidence_set_digest_matches_the_examples_authored_value() -> None:
    """Two independent implementations of §7 steps 2-3 agree: the generator's and this one's."""
    documents = parse_documents(example_source_root())
    assert evidence_set_digest(documents, blob_reader()) == EXAMPLE_EVIDENCE_SET_DIGEST
    assert documents.manifest.evidence_set_digest == EXAMPLE_EVIDENCE_SET_DIGEST


def test_the_evidence_set_digest_excludes_the_manifest(synthetic_bundle: SyntheticBundle) -> None:
    """No cycle: the digest is written INTO the manifest, so it cannot depend on it."""
    before = evidence_set_digest(parse_documents(synthetic_bundle.draft), blob_reader())
    text = synthetic_bundle.read("manifest.yaml")
    synthetic_bundle.write(
        "manifest.yaml", text.replace("profile.example-candidate", "profile.other-candidate")
    )
    after = evidence_set_digest(parse_documents(synthetic_bundle.draft), blob_reader())
    assert before == after


def test_a_changed_evidence_record_changes_the_evidence_set_digest(
    synthetic_bundle: SyntheticBundle,
) -> None:
    before = evidence_set_digest(parse_documents(synthetic_bundle.draft), blob_reader())
    text = synthetic_bundle.read("evidence/records.yaml")
    synthetic_bundle.write(
        "evidence/records.yaml", text.replace("Retired scorecard reading", "Retired reading")
    )
    after = evidence_set_digest(parse_documents(synthetic_bundle.draft), blob_reader())
    assert before != after


def test_changed_blob_bytes_change_the_evidence_set_digest() -> None:
    documents = parse_documents(example_source_root())
    tampered = MappingBlobReader({BLOB_SHA256: BLOB_BYTES + b"tampered\n"})
    assert evidence_set_digest(documents, tampered) != EXAMPLE_EVIDENCE_SET_DIGEST


def test_a_missing_blob_refuses_to_produce_a_digest() -> None:
    """Silently omitting an unreadable blob would make a broken bundle compute a valid digest."""
    documents = parse_documents(example_source_root())
    with pytest.raises(MissingBlobError):
        evidence_set_digest(documents, MappingBlobReader({}))


# --------------------------------------------------------------------------------------
# leaves and the bundle digest
# --------------------------------------------------------------------------------------


def test_leaf_keys_are_prefixed_and_never_delimiter_concatenated() -> None:
    leaves = leaf_index(parse_documents(example_source_root()), blob_reader())
    document_keys = [key for key in leaves if key.startswith(DOCUMENT_KEY_PREFIX)]
    blob_keys = [key for key in leaves if key.startswith(BLOB_KEY_PREFIX)]
    assert f"{DOCUMENT_KEY_PREFIX}manifest.yaml" in document_keys
    assert f"{DOCUMENT_KEY_PREFIX}facts/identity.yaml" in document_keys
    assert blob_keys == [f"{BLOB_KEY_PREFIX}sha256:{BLOB_SHA256}"]
    assert set(leaves) == set(document_keys) | set(blob_keys)
    for value in leaves.values():
        assert value.startswith("sha256:")
        assert len(value) == DIGEST_RE_LENGTH


def test_every_declared_document_contributes_exactly_one_leaf() -> None:
    documents = parse_documents(example_source_root())
    leaves = leaf_index(documents, blob_reader())
    document_leaves = {key for key in leaves if key.startswith(DOCUMENT_KEY_PREFIX)}
    assert len(document_leaves) == len(documents.by_path) + 1  # every document plus the manifest


def test_one_blob_referenced_twice_still_yields_exactly_one_leaf(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§7: identical blob digests are deduplicated. Two records citing one capture is normal."""
    text = synthetic_bundle.read("evidence/records.yaml")
    switched = text.replace(
        "  capture:\n    kind: inline\n    text: Median request latency measured at 18 ms across"
        " the same five minute run.\n    media_type: text/plain",
        f"  capture:\n    kind: blob\n    sha256: '{BLOB_SHA256}'\n    media_type: text/markdown",
    )
    assert switched != text, "the latency capture was not rewritten; the fixture text moved"
    synthetic_bundle.write("evidence/records.yaml", switched)
    documents = parse_documents(synthetic_bundle.draft)
    assert referenced_blob_digests(documents) == (BLOB_SHA256,)
    leaves = leaf_index(documents, blob_reader())
    assert len([key for key in leaves if key.startswith(BLOB_KEY_PREFIX)]) == 1


def test_the_changed_evidence_document_still_changes_the_bundle_digest(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The dedupe must not swallow the change: the evidence DOCUMENT leaf still moves."""
    before = bundle_digest(parse_documents(synthetic_bundle.draft), blob_reader())
    text = synthetic_bundle.read("evidence/records.yaml")
    synthetic_bundle.write("evidence/records.yaml", text.replace("18 ms", "19 ms"))
    after = bundle_digest(parse_documents(synthetic_bundle.draft), blob_reader())
    assert before != after


def test_harmless_yaml_reformatting_leaves_the_bundle_digest_unchanged(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """Reordered mapping keys, flow style, extra blank lines, and a comment are all formatting."""
    before = bundle_digest(parse_documents(synthetic_bundle.draft), blob_reader())
    synthetic_bundle.write(
        "policy/units.yaml",
        "# A comment the digest must not see.\n\n"
        "units:\n"
        "- {allowed_metric_kinds: [count], aliases: [item], symbol: items,\n"
        "   display_name: items, unit_id: items}\n"
        "- allowed_metric_kinds: [duration, latency]\n"
        "  aliases:\n"
        "  - millisecond\n"
        "  symbol: ms\n"
        "  display_name: milliseconds\n"
        "  unit_id: milliseconds\n"
        "- {unit_id: items_per_second, display_name: items per second, symbol: items/s,\n"
        "   aliases: [item_per_second], allowed_metric_kinds: [rate, throughput]}\n"
        "- {unit_id: percent, display_name: percent, symbol: '%', aliases: [percentage],\n"
        "   allowed_metric_kinds: [percentage]}\n"
        "- {unit_id: usd, display_name: US dollars, symbol: USD, aliases: [us_dollars],\n"
        "   allowed_metric_kinds: [currency]}\n"
        "- {unit_id: bytes, display_name: bytes, symbol: B, aliases: [byte],\n"
        "   allowed_metric_kinds: [size]}\n"
        "- {unit_id: ordinal, display_name: ordinal position, symbol: ordinal,\n"
        "   aliases: [place], allowed_metric_kinds: [rank]}\n"
        "- {unit_id: points, display_name: points, symbol: pts, aliases: [point],\n"
        "   allowed_metric_kinds: [score]}\n"
        "\n"
        "units_version: 1\n",
    )
    assert bundle_digest(parse_documents(synthetic_bundle.draft), blob_reader()) == before


def test_relocating_the_bundle_leaves_the_bundle_digest_unchanged(tmp_path: Path) -> None:
    """§5: identity is derived from validated content, never from the absolute path."""
    first = tmp_path / "here"
    second = tmp_path / "elsewhere" / "nested"
    shutil.copytree(example_source_root(), first)
    second.parent.mkdir(parents=True)
    shutil.copytree(example_source_root(), second)
    assert bundle_digest(parse_documents(first), blob_reader()) == bundle_digest(
        parse_documents(second), blob_reader()
    )


def test_a_blobs_filesystem_path_is_not_an_identity_input(tmp_path: Path) -> None:
    """The blob leaf is keyed by digest, so where the bytes live cannot matter."""
    documents = parse_documents(example_source_root())
    from boardwatch.profile_bundle.canonical import FilesystemBlobReader

    for directory in ("a", "b/c/d"):
        blobs = tmp_path / directory
        blobs.mkdir(parents=True)
        (blobs / BLOB_SHA256).write_bytes(BLOB_BYTES)
    first = bundle_digest(documents, FilesystemBlobReader(tmp_path / "a"))
    second = bundle_digest(documents, FilesystemBlobReader(tmp_path / "b/c/d"))
    assert first == second


def test_the_root_only_sidecar_cannot_change_any_identity(
    synthetic_bundle: SyntheticBundle, tmp_path: Path
) -> None:
    """§6: `local-sources.yaml` is excluded from revision, evidence and candidate identity."""
    documents = parse_documents(synthetic_bundle.draft)
    before = (
        evidence_set_digest(documents, blob_reader()),
        bundle_digest(documents, blob_reader()),
        candidate_content_digest(documents, blob_reader(), None),
    )
    sidecar = LocalSourcesSidecar.model_validate(
        {"source.synthetic-notes": str(tmp_path / "originals")}
    )
    local_sources_path(synthetic_bundle.root).write_text(
        "\n".join(f"{key}: {value}" for key, value in sidecar.roots.items()) + "\n",
        encoding="utf-8",
    )
    reparsed = parse_documents(synthetic_bundle.draft)
    after = (
        evidence_set_digest(reparsed, blob_reader()),
        bundle_digest(reparsed, blob_reader()),
        candidate_content_digest(reparsed, blob_reader(), None),
    )
    assert before == after


def test_the_bundle_digest_is_stable_across_repeated_computation() -> None:
    documents = parse_documents(example_source_root())
    assert bundle_digest(documents, blob_reader()) == bundle_digest(documents, blob_reader())


def test_rewriting_only_the_bundle_digest_sentinel_leaves_identity_unchanged(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§7 step 5 blanks the field before hashing, so a stored value there is not an input."""
    before = bundle_digest(parse_documents(synthetic_bundle.draft), blob_reader())
    text = synthetic_bundle.read("manifest.yaml")
    assert "bundle_digest: ''" in text
    synthetic_bundle.write("manifest.yaml", text)
    assert bundle_digest(parse_documents(synthetic_bundle.draft), blob_reader()) == before


def test_a_changed_manifest_catalog_version_does_change_the_bundle_digest(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The manifest is a leaf, so everything in it except the two computed fields is an input."""
    before = bundle_digest(parse_documents(synthetic_bundle.draft), blob_reader())
    text = synthetic_bundle.read("manifest.yaml")
    synthetic_bundle.write(
        "manifest.yaml", text.replace("unit_catalog_version: 1", "unit_catalog_version: 2")
    )
    assert bundle_digest(parse_documents(synthetic_bundle.draft), blob_reader()) != before


# --------------------------------------------------------------------------------------
# candidate digest
# --------------------------------------------------------------------------------------


def test_the_candidate_digest_omits_the_approval_ledger(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """The stamp cannot be inside what it approves."""
    before = candidate_content_digest(parse_documents(synthetic_bundle.draft), blob_reader(), None)
    synthetic_bundle.write(
        "history/approvals.yaml",
        "approvals:\n"
        "- approval_stamp_id: approval-stamp.000001\n"
        f"  candidate_content_digest: sha256:{'0' * 64}\n"
        "  approved_at: '2026-08-10T12:00:00Z'\n"
        "  approved_via: controlling_terminal\n"
        "  entries: []\n",
    )
    after = candidate_content_digest(parse_documents(synthetic_bundle.draft), blob_reader(), None)
    assert before == after


def test_editing_any_owner_gated_record_changes_the_candidate_digest(
    synthetic_bundle: SyntheticBundle,
) -> None:
    """§13: "any subsequent draft content edit invalidates it" — by digest mismatch, not by policy."""
    before = candidate_content_digest(parse_documents(synthetic_bundle.draft), blob_reader(), None)
    text = synthetic_bundle.read("claims/bullet-candidates.yaml")
    synthetic_bundle.write(
        "claims/bullet-candidates.yaml",
        text.replace("Built a retry-safe ingestion path", "Architected a retry-safe pipeline"),
    )
    after = candidate_content_digest(parse_documents(synthetic_bundle.draft), blob_reader(), None)
    assert before != after


@pytest.mark.parametrize(
    ("relative", "before_text", "after_text"),
    [
        ("evidence/records.yaml", "Retired scorecard reading", "Retired reading"),
        ("metrics/records.yaml", "qualifier: approximate", "qualifier: at_least"),
        ("conflicts/rulings.yaml", "start of implementation", "start of the build"),
        ("facts/identity.yaml", "Example Candidate", "Example Person"),
        ("imports/exclusions.yaml", "administrative_noise", "non_professional"),
        ("policy/predicates.yaml", "may_ground_skill: true", "may_ground_skill: false"),
        ("application/gated-facts.yaml", "EXAMPLE-REGION-A", "EXAMPLE-REGION-C"),
    ],
)
def test_every_owner_gated_document_is_inside_the_candidate_view(
    synthetic_bundle: SyntheticBundle, relative: str, before_text: str, after_text: str
) -> None:
    before = candidate_content_digest(parse_documents(synthetic_bundle.draft), blob_reader(), None)
    text = synthetic_bundle.read(relative)
    mutated = text.replace(before_text, after_text, 1)
    assert mutated != text, f"{relative} no longer contains {before_text!r}"
    synthetic_bundle.write(relative, mutated)
    after = candidate_content_digest(parse_documents(synthetic_bundle.draft), blob_reader(), None)
    assert before != after


def test_the_candidate_digest_differs_from_the_bundle_digest() -> None:
    """They answer different questions: "did the owner approve THIS content?" versus "is this the
    revision it claims to be?". Sharing a value would make one substitutable for the other."""
    documents = parse_documents(example_source_root())
    assert candidate_content_digest(documents, blob_reader(), None) != bundle_digest(
        documents, blob_reader()
    )


def test_the_blob_bytes_and_the_authored_capture_digest_agree() -> None:
    assert hashlib.sha256(BLOB_BYTES).hexdigest() == BLOB_SHA256
