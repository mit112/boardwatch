"""`ResumeSourceLineage` round-trips through its flat `meta_json` form, and its home module stays
free of the tailor/bundle import wall it was carved out to avoid breaking."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from boardwatch.core.lineage import ResumeSourceLineage


def test_lineage_round_trips_through_its_meta_form() -> None:
    lineage = ResumeSourceLineage(
        kind="projection",
        bundle_revision="21",
        bundle_digest="sha256:" + "a" * 64,
        projection_digest="sha256:" + "b" * 64,
        posting_version_id=4321,
        as_of="2026-08-17",
        scorer_id="mean_per_bullet",
        taxonomy_version="c" * 64,
        equivalence_version="d" * 64,
        persona_registry_version="e" * 64,
        resume_sha256="f" * 64,
        resume_model_sha256="0" * 64,
        manifest_schema=1,
    )
    meta = lineage.as_meta()
    assert meta["projection_bundle_revision"] == "21"
    assert meta["projection_posting_version_id"] == 4321
    # Every field reaches the artifact row: a lineage field that is silently dropped is the
    # exact "more inspectable, not detected" failure this slice exists to close.
    assert len(meta) == len(dataclasses.fields(lineage))


def test_the_lineage_module_does_not_reach_the_profile_bundle() -> None:
    """`reports.tailor` imports this type and sits inside the tailor import-wall closure, so a
    lineage module that reached `profile_bundle` would break
    `test_no_production_tailor_module_reaches_the_profile_bundle`."""
    import boardwatch.core.lineage as lineage_module

    source = Path(lineage_module.__file__).read_text(encoding="utf-8")
    assert "profile_bundle" not in source
    assert "boardwatch.projection" not in source
