"""Projection fixtures. The bundle comes from the profile_bundle fixtures, never re-parsed here.

Imported as `from tests.projection.conftest import ...` — never `from conftest import`, which binds
whichever conftest loaded first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.profile_bundle.validation.context import ValidationContext, context_from_documents
from tests.profile_bundle.conftest import SyntheticBundle, materialise, parse_documents


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
