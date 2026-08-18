"""`ResumeSourceLineage` round-trips through its flat `meta_json` form, and its home module stays
free of the tailor/bundle import wall it was carved out to avoid breaking."""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

from boardwatch.core import lineage
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


def test_the_lineage_module_imports_neither_the_bundle_nor_projection() -> None:
    """The guarantee is an IMPORT edge, not a spelling. `reports.tailor` imports this module and
    sits inside the closure `test_profile_bundle_tailor_isolation.py` walks, so an import of
    `profile_bundle` here would break that wall. Asserting on parsed imports rather than on the
    raw source lets the docstring name the constraint it exists to enforce."""
    tree = ast.parse(Path(lineage.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    forbidden = [
        name
        for name in imported
        if name.startswith(("boardwatch.profile_bundle", "boardwatch.projection"))
    ]
    assert forbidden == []
