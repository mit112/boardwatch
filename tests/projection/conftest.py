"""Projection fixtures. The bundle comes from the profile_bundle fixtures, never re-parsed here.

Imported as `from tests.projection.conftest import ...` — never `from conftest import`, which binds
whichever conftest loaded first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

import pytest

from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME
from boardwatch.profile_bundle.validation.context import ValidationContext, context_from_documents
from boardwatch.projection.declaration import load_declaration, projection_digest
from boardwatch.projection.stamp import write_stamp
from tests.profile_bundle.conftest import (
    SyntheticBundle,
    materialise,
    parse_documents,
    promote_example_tree,
)


def context_over(bundle: SyntheticBundle) -> ValidationContext:
    """Parse and index whatever `bundle.draft` currently holds, through the production loader.

    Split out of `bundle_ctx` so a test can edit a document in place (`SyntheticBundle.write`)
    before parsing — to build a negative case the packaged example does not contain — without a
    second, parallel bundle-building helper.
    """
    documents = parse_documents(bundle.draft)
    return context_from_documents(
        documents, root=bundle.draft, mode="draft", bundle_root=bundle.root
    )


@pytest.fixture
def materialised_bundle(tmp_path: Path) -> SyntheticBundle:
    """The packaged synthetic bundle, materialised into `tmp_path` but not yet parsed.

    The packaged example is a DRAFT with `bundle_digest: ''` and no blobs, so
    `read_current_once` cannot reach it — `materialise` is what turns it into a usable tree.
    """
    root = tmp_path / "career-profile"
    root.mkdir()
    (root / "drafts").mkdir()
    return materialise(root)


@pytest.fixture
def bundle_ctx(materialised_bundle: SyntheticBundle) -> ValidationContext:
    """A ValidationContext over the packaged synthetic bundle, unmodified."""
    return context_over(materialised_bundle)


#: A minimal, valid header/education shell. Reused verbatim from `test_projection_shell.py`'s own
#: `GOOD` constant shape, not restated logic — this is plain fixture data, not a check.
_SHELL_BODY = (
    "header:\n"
    "  - Example Candidate\n"
    "  - candidate@example.com\n"
    "education:\n"
    "  - Example University\n"
)


@dataclass(frozen=True)
class ProjectionEnv:
    """A promoted bundle, a config dir, and the `projection.yaml` declaration path over it —
    everything `project_pool` needs to run Stage 1 end to end."""

    bundle_root: Path
    config_dir: Path
    declaration: Path


def _build_projection_env(tmp_path: Path, *, approved: bool) -> ProjectionEnv:
    """`project_pool` reads the bundle through `read_current_once`, which needs a genuinely
    promoted revision (a `CURRENT` pointer, a `COMPLETE` marker) — not merely the materialised
    draft `context_over` builds. `promote_example_tree` (`tests/profile_bundle/conftest.py`) is
    the existing, already-exercised route to that; this does not re-implement it.

    The declaration is the packaged `projection.example.yaml` itself, copied byte for byte rather
    than restated: its `shell_source: master_resume.yaml` is RELATIVE, which is exactly what
    exercises this task's own obligation — resolving it against `config_dir` — rather than a
    declaration authored with an already-absolute path (as `test_projection_declaration.py`'s
    `MINIMAL` fixture uses, for an unrelated reason: it does not go through `project_pool`).

    Named `projection-bundle`, distinct from `materialised_bundle`'s own `career-profile`: a test
    that requests both this and `bundle_ctx` (as an independent oracle) must not collide on the
    same `tmp_path` subdirectory.
    """
    bundle_root = tmp_path / "projection-bundle"
    promote_example_tree(bundle_root)

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "master_resume.yaml").write_text(_SHELL_BODY, encoding="utf-8")

    traversable = resources.files("boardwatch.projection.examples").joinpath(
        "projection.example.yaml"
    )
    with resources.as_file(traversable) as packaged:
        declaration_text = packaged.read_text(encoding="utf-8")
    declaration_path = config_dir / "projection.yaml"
    declaration_path.write_text(declaration_text, encoding="utf-8")

    if approved:
        digest = projection_digest(load_declaration(declaration_path))
        write_stamp(config_dir, digest=digest, approved_at=datetime(2026, 8, 13, 12, tzinfo=UTC))

    return ProjectionEnv(
        bundle_root=bundle_root, config_dir=config_dir, declaration=declaration_path
    )


@pytest.fixture
def projection_env(tmp_path: Path) -> ProjectionEnv:
    """A fully approved, resolvable projection environment over a promoted synthetic bundle."""
    return _build_projection_env(tmp_path, approved=True)


@pytest.fixture
def projection_env_unapproved(tmp_path: Path) -> ProjectionEnv:
    """The same environment, minus the approval stamp."""
    return _build_projection_env(tmp_path, approved=False)


@pytest.fixture
def example_declaration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The packaged example declaration, resolvable end to end with no `--bundle`/`--declaration`
    override: a promoted synthetic bundle at `config_dir / "career-profile"` (the CLI's own
    default via `resolve_bundle_root`), a valid header/education shell beside it, and
    `BOARDWATCH_CONFIG_DIR` pointed at that same directory. Unapproved — no stamp is written —
    because these tests are about the command that creates the first one.

    Returns the declaration's path (`config_dir / "projection.yaml"`); `path.parent` is the
    config dir, for a test that needs to look at what the command wrote (or didn't).
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))

    promote_example_tree(config_dir / BUNDLE_DIR_NAME)
    (config_dir / "master_resume.yaml").write_text(_SHELL_BODY, encoding="utf-8")

    traversable = resources.files("boardwatch.projection.examples").joinpath(
        "projection.example.yaml"
    )
    with resources.as_file(traversable) as packaged:
        declaration_text = packaged.read_text(encoding="utf-8")
    declaration_path = config_dir / "projection.yaml"
    declaration_path.write_text(declaration_text, encoding="utf-8")
    return declaration_path
