"""Bundle path resolution and confinement.

Design §5: the bundle location is resolved at the command boundary as
`settings.config_dir / "career-profile"`, with `--bundle PATH` overriding it. It is deliberately
not a `Settings` field — it is machine-local and takes no part in lead selection or
`policy_version`.

Every other path in the bundle is *derived*, and derivation is the confinement boundary. A draft
name reaches this module from an operator or a cooperative agent; if `drafts/<name>` could escape
the root, so could promotion's temporary tree and the rebase backup. Names are therefore matched
against a closed grammar rather than sanitised, and digests are validated before they become a
directory name so a malformed pointer cannot address an arbitrary path.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Final

from pydantic import StringConstraints

from boardwatch.profile_bundle.errors import BundlePathError

Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
BareSha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

_DIGEST_RE: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_BARE_DIGEST_RE: Final = re.compile(r"^[0-9a-f]{64}$")

# Lowercase-anchored so a name cannot differ from another only by case on a case-insensitive
# filesystem. The interior admits `.` and `-` because the rebase backup name is itself a draft
# directory (`<name>.pre-rebase-sha256-<64hex>`), and a grammar that rejected it would make the
# drain unrepresentable. A trailing separator is refused so no name can be a prefix-with-dot of
# another.
_DRAFT_NAME_RE: Final = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")

#: The longest name this module derives from a draft name: the rebase backup's
#: `.pre-rebase-sha256-<64hex>`. Computed rather than counted, so the two caps below stay consistent
#: with the grammar `rebase_backup_name` actually emits.
_LONGEST_DERIVED_SUFFIX: Final = len(f".pre-rebase-{'sha256-' + '0' * 64}")

#: The cap on a name an operator or agent supplies.
MAX_DRAFT_NAME_LENGTH: Final = 96

#: The cap on any draft *directory* name, which includes the ones this module derives. It has to
#: exceed `MAX_DRAFT_NAME_LENGTH` by the derived suffix: capping both at 96 would mean every legal
#: draft name longer than `96 - 83` derived a backup name its own grammar refused, so it could never
#: be rebased and `promote` would report `stale_draft_parent` for it forever. The sum is still far
#: inside the 255-byte per-component limit the filesystems Boardwatch runs on enforce.
MAX_DRAFT_SEGMENT_LENGTH: Final = MAX_DRAFT_NAME_LENGTH + _LONGEST_DERIVED_SUFFIX

BUNDLE_DIR_NAME: Final = "career-profile"
CURRENT_FILE: Final = "CURRENT"
COMPLETE_FILE: Final = "COMPLETE"
LOCK_FILE: Final = "career-profile.lock"
LOCAL_SOURCES_FILE: Final = "local-sources.yaml"
APPROVALS_DIR: Final = "approvals"
REVISIONS_DIR: Final = "revisions"
DRAFTS_DIR: Final = "drafts"
BLOBS_DIR: Final = "blobs"
BLOB_ALGORITHM_DIR: Final = "sha256"

#: The closed set of names permitted directly under the bundle root (design §6). Lock-file
#: persistence is normal and carries no meaning; see `promotion` for why it is never broken.
ROOT_MEMBERS: Final[frozenset[str]] = frozenset(
    {CURRENT_FILE, LOCK_FILE, LOCAL_SOURCES_FILE, APPROVALS_DIR, REVISIONS_DIR, DRAFTS_DIR,
     BLOBS_DIR}
)

#: The rebase backup token for a parentless revision-1 draft, where there is no parent digest.
ROOT_PARENT_TOKEN: Final = "root"


def resolve_bundle_root(config_dir: Path, override: Path | None) -> Path:
    """The bundle root: `--bundle` if given, else `config_dir / "career-profile"`."""
    return override if override is not None else config_dir / BUNDLE_DIR_NAME


def require_digest(value: str) -> str:
    """Return `value` if it is a lowercase full `sha256:<64-hex>` string, else raise.

    Uppercase hex is refused rather than folded: two spellings of one digest would produce two
    directory names for one revision, and on a case-insensitive filesystem they would collide.
    """
    if not _DIGEST_RE.match(value):
        raise BundlePathError(
            f"expected a lowercase 'sha256:<64-hex>' digest, got {value!r}"
        )
    return value


def require_bare_digest(value: str) -> str:
    """Return `value` if it is 64 lowercase hex characters with no prefix, else raise."""
    if not _BARE_DIGEST_RE.match(value):
        raise BundlePathError(f"expected 64 lowercase hexadecimal characters, got {value!r}")
    return value


def digest_token(value: str) -> str:
    """The filesystem token for a full digest: `sha256-<64-hex>`.

    The `:` in the textual digest form is not portable in a filename (it is a path separator on
    some platforms and reserved on Windows), so the token substitutes `-`. The textual form stays
    authoritative inside documents.
    """
    return "sha256-" + require_digest(value).removeprefix("sha256:")


def require_draft_name(name: str) -> str:
    """Return `name` if it matches the closed draft-name grammar, else raise.

    For a name that came from an operator or an agent. A name this module *derived* goes through
    `require_draft_segment`, which admits the derived suffix as well.
    """
    return _require_draft_segment(name, MAX_DRAFT_NAME_LENGTH)


def require_draft_segment(name: str) -> str:
    """Return `name` if it is a legal draft directory name, including a derived one, else raise.

    Same grammar, the longer cap. Used where the subject is a directory that already exists — a
    rebase backup an inventory found under `drafts/`, say — rather than a name being requested.
    """
    return _require_draft_segment(name, MAX_DRAFT_SEGMENT_LENGTH)


def _require_draft_segment(name: str, limit: int) -> str:
    if not name or len(name) > limit or not _DRAFT_NAME_RE.match(name):
        raise BundlePathError(
            f"draft name {name!r} is not a single lowercase path segment matching "
            f"{_DRAFT_NAME_RE.pattern} within {limit} characters"
        )
    return name


def current_path(bundle_root: Path) -> Path:
    return bundle_root / CURRENT_FILE


def lock_path(bundle_root: Path) -> Path:
    return bundle_root / LOCK_FILE


def local_sources_path(bundle_root: Path) -> Path:
    """The private root sidecar. Excluded from every revision, digest, and export."""
    return bundle_root / LOCAL_SOURCES_FILE


def approvals_dir(bundle_root: Path) -> Path:
    return bundle_root / APPROVALS_DIR


def revisions_dir(bundle_root: Path) -> Path:
    return bundle_root / REVISIONS_DIR


def drafts_dir(bundle_root: Path) -> Path:
    return bundle_root / DRAFTS_DIR


def blobs_dir(bundle_root: Path) -> Path:
    return bundle_root / BLOBS_DIR / BLOB_ALGORITHM_DIR


def draft_root(bundle_root: Path, name: str) -> Path:
    return drafts_dir(bundle_root) / require_draft_name(name)


def rebase_backup_name(name: str, old_parent_digest: str | None) -> str:
    """`<name>.pre-rebase-sha256-<64hex>`, or `.pre-rebase-root` for a parentless draft.

    Deterministic on purpose: a second rebase of the same draft from the same parent must land on
    the same path so it can be compared byte-for-byte instead of accumulating numbered backups.

    The derived name is re-checked against the grammar — confinement is not inherited from the input
    just because the suffix looks safe — but against the segment cap, because the suffix is this
    module's own and refusing it would refuse the draft rather than the name.
    """
    token = ROOT_PARENT_TOKEN if old_parent_digest is None else digest_token(old_parent_digest)
    return require_draft_segment(f"{require_draft_name(name)}.pre-rebase-{token}")


def rebase_backup_root(bundle_root: Path, name: str, old_parent_digest: str | None) -> Path:
    return drafts_dir(bundle_root) / rebase_backup_name(name, old_parent_digest)


def revision_root(bundle_root: Path, bundle_digest: str) -> Path:
    """`revisions/sha256-<full-digest>`. Revision numbers are never filesystem identity."""
    return revisions_dir(bundle_root) / digest_token(bundle_digest)


def approval_path(bundle_root: Path, candidate_digest: str) -> Path:
    """`approvals/sha256-<candidate-digest>.yaml`.

    Keyed by the candidate digest rather than the draft name: a stamp outlives the draft that
    produced it, and two drafts with the same content must not alias to two stamp files.
    """
    return approvals_dir(bundle_root) / f"{digest_token(candidate_digest)}.yaml"


def blob_path(bundle_root: Path, bare_digest: str) -> Path:
    """`blobs/sha256/<64-hex>`. Blob filesystem paths are never digest inputs."""
    return blobs_dir(bundle_root) / require_bare_digest(bare_digest)


def complete_marker_path(revision_dir: Path) -> Path:
    return revision_dir / COMPLETE_FILE
