"""The synthetic comprehensive bundle, materialised into a temporary bundle root.

The packaged example is a *logical revision tree*: manifest, facts, claims, policy, imports,
history. Blobs deliberately are not part of it, because design §6 puts `blobs/sha256/` at the bundle
ROOT and shares it across revisions. So the fixture is what turns the example into a usable bundle:
it copies the tree into `drafts/<name>/` (or into a revision directory), writes the blob bytes the
example's one blob capture names, and hands back the paths and digests a test needs.

The blob text lives here rather than in the package because it is *not* part of any revision's
logical content — only its digest is.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import pytest

from boardwatch.profile_bundle.canonical import MappingBlobReader
from boardwatch.profile_bundle.models.documents import BundleDocuments
from boardwatch.profile_bundle.paths import blob_path, blobs_dir, draft_root, drafts_dir
from boardwatch.profile_bundle.validation import load_documents

EXAMPLE_PACKAGE = "boardwatch.profile_bundle"
EXAMPLE_RELATIVE = "examples/comprehensive"

#: The bytes behind the example's one blob capture. Its digest is authored into
#: `evidence/records.yaml`, so changing this text without regenerating the example breaks the
#: blob-integrity check — which is the point.
BLOB_TEXT = (
    "# Packet Pantry baseline A\n\n"
    "Synthetic benchmark note. Sustained approximately 120 items/s over a five minute run on a\n"
    "single local node with one producer. Recorded so the linked metric can be reviewed without\n"
    "resolving its origin.\n"
)
BLOB_BYTES = BLOB_TEXT.encode("utf-8")
BLOB_SHA256 = hashlib.sha256(BLOB_BYTES).hexdigest()

#: The example is a parentless revision-1 draft, so its manifest carries this evidence-set digest.
#: Pinned here as well as in the YAML so a test can assert the two agree by a second path.
EXAMPLE_EVIDENCE_SET_DIGEST = (
    "sha256:bb92aef8ff2d82c0178482ab5fa4c24975e6f3ab8251f3e6d939e14d3bcffde0"
)

EXAMPLE_PROFILE_ID = "profile.example-candidate"


def example_source_root() -> Path:
    """The packaged example tree, resolved through `importlib.resources`.

    Resolved as a resource rather than by walking up from `__file__` so the same fixture works
    against an installed wheel, which is where a missing package-data file would actually show up.
    """
    traversable = resources.files(EXAMPLE_PACKAGE).joinpath(EXAMPLE_RELATIVE)
    with resources.as_file(traversable) as path:
        return Path(path)


@dataclass(frozen=True)
class SyntheticBundle:
    """A materialised bundle root holding the comprehensive example as one draft."""

    root: Path
    draft_name: str
    draft: Path
    blob: Path

    @property
    def manifest_path(self) -> Path:
        return self.draft / "manifest.yaml"

    def document(self, relative: str) -> Path:
        return self.draft / relative

    def read(self, relative: str) -> str:
        return self.document(relative).read_text(encoding="utf-8")

    def write(self, relative: str, text: str) -> None:
        """Rewrite one document in place. Used to build the negative cases."""
        self.document(relative).write_text(text, encoding="utf-8")


def materialise(root: Path, *, draft_name: str = "baseline") -> SyntheticBundle:
    """Copy the packaged example into `root` as a draft, and write its blob bytes."""
    target = draft_root(root, draft_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(example_source_root(), target)
    blobs_dir(root).mkdir(parents=True, exist_ok=True)
    blob = blob_path(root, BLOB_SHA256)
    blob.write_bytes(BLOB_BYTES)
    return SyntheticBundle(root=root, draft_name=draft_name, draft=target, blob=blob)


def materialise_revision_tree(destination: Path) -> Path:
    """Copy the example's logical tree to an arbitrary directory, blobs excluded.

    Promotion and digest tests need the tree somewhere that is not `drafts/`, and they own where.
    """
    shutil.copytree(example_source_root(), destination)
    return destination


@pytest.fixture
def synthetic_bundle(tmp_path: Path) -> SyntheticBundle:
    """A fresh bundle root with the comprehensive example checked out as `drafts/baseline/`."""
    root = tmp_path / "career-profile"
    root.mkdir()
    drafts_dir(root).mkdir()
    return materialise(root)


def parse_documents(root: Path, *, final_revision: bool = False) -> BundleDocuments:
    """Parse one logical tree into `BundleDocuments`, through the production loader.

    Delegates rather than re-implementing: a fixture that parsed by its own path would let the
    fixtures agree with each other while disagreeing with what the CLI actually reads.
    """
    return load_documents(root, mode="revision" if final_revision else "draft")


def blob_reader() -> MappingBlobReader:
    """A reader over the one blob the example names, for identity computations in tests."""
    return MappingBlobReader({BLOB_SHA256: BLOB_BYTES})
