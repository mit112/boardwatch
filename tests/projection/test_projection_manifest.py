"""Task 13: the projection manifest sidecar.

Two properties the brief names explicitly: the emitted JSON is deterministic (`sort_keys=True`),
and a float score is rejected outright rather than silently coerced — `canonical._normalize`
(profile_bundle, not importable from here) raises on any float for the identical reason: a score
that reaches this sidecar must never depend on floating-point representation.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from boardwatch.projection.manifest import (
    MANIFEST_SCHEMA_VERSION,
    ProjectionManifest,
    manifest_bytes,
)


def _manifest(**overrides: object) -> ProjectionManifest:
    fields: dict[str, object] = dict(
        manifest_schema=MANIFEST_SCHEMA_VERSION,
        bundle_revision="7",
        bundle_digest="sha256:" + "a" * 64,
        projection_digest="sha256:" + "b" * 64,
        posting_id=None,
        jd_skills=("python", "sql"),
        pinned_entry_ids=("entry.pinned",),
        selected_entry_ids=("entry.pinned", "entry.candidate"),
        scores=(("entry.candidate", "2.5"),),
        claim_to_bullet=(("claim.a", "claim.a"),),
        posting_version_id=11,
        as_of="2026-08-17",
        scorer_id="mean_per_bullet",
        taxonomy_version="c" * 64,
        equivalence_version="equiv-1",
        persona_registry_version="personas-1",
        resume_sha256="d" * 64,
        resume_model_sha256="e" * 64,
    )
    fields.update(overrides)
    return ProjectionManifest(**fields)  # type: ignore[arg-type]


def test_manifest_bytes_sorts_top_level_keys_alphabetically() -> None:
    """A real determinism claim, not a tautology: the manifest's own field-declaration order
    (`manifest_schema` first) differs from alphabetical order (`bundle_digest` first), so this
    fails if `sort_keys=True` is ever dropped from the emitter."""
    manifest = _manifest()
    raw = manifest_bytes(manifest)
    parsed_pairs = json.loads(raw.decode("utf-8"), object_pairs_hook=list)
    top_level_keys = [key for key, _ in parsed_pairs]

    # The premise: declared field order and sorted order are genuinely different for this
    # model, or a broken emitter that ignores sort_keys entirely would pass by accident.
    assert list(ProjectionManifest.model_fields) != sorted(ProjectionManifest.model_fields)

    assert top_level_keys == sorted(top_level_keys)


def test_manifest_bytes_is_deterministic_across_calls() -> None:
    manifest = _manifest()
    assert manifest_bytes(manifest) == manifest_bytes(manifest)


def test_manifest_rejects_a_float_score() -> None:
    with pytest.raises(ValidationError):
        _manifest(scores=(("entry.candidate", 2.5),))


def test_manifest_rejects_a_malformed_decimal_string() -> None:
    """Distinct from the float case: this is a `str`, so a bare unconstrained `str` field would
    accept it. Only the `DecimalString` pattern itself catches scientific notation."""
    with pytest.raises(ValidationError):
        _manifest(scores=(("entry.candidate", "2.5e3"),))


def test_manifest_accepts_a_negative_decimal_string() -> None:
    """Positive control for the pattern: a well-formed decimal string, including a negative
    one, is accepted verbatim."""
    manifest = _manifest(scores=(("entry.candidate", "-1.25"),))
    assert manifest.scores == (("entry.candidate", "-1.25"),)


def test_manifest_scores_survive_a_round_trip_as_the_exact_decimal_string() -> None:
    """The whole point of carrying scores as strings: `Decimal("2.5")` stringified and stored
    here must come back out byte-for-byte, never renormalised or re-rendered as a float."""
    score = str(Decimal("2.50"))
    manifest = _manifest(scores=(("entry.candidate", score),))
    raw = manifest_bytes(manifest)
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["scores"] == [["entry.candidate", score]]
