"""Projection fixtures. The bundle comes from the profile_bundle fixtures, never re-parsed here.

Imported as `from tests.projection.conftest import ...` — never `from conftest import`, which binds
whichever conftest loaded first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.profile_bundle.validation.context import context_from_documents
from tests.profile_bundle.conftest import materialise, parse_documents


@pytest.fixture
def bundle_ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    """A ValidationContext over the packaged synthetic bundle.

    The packaged example is a DRAFT with `bundle_digest: ''` and no blobs, so
    `read_current_once` cannot reach it — `materialise` is what turns it into a usable tree.
    """
    root = tmp_path / "career-profile"
    root.mkdir()
    (root / "drafts").mkdir()
    bundle = materialise(root)
    documents = parse_documents(bundle.draft)
    return context_from_documents(documents, root=bundle.draft, mode="draft", bundle_root=root)
