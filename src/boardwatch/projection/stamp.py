"""The owner's approval of one `projection.yaml`, bound to its digest.

Deliberately NOT `profile_bundle.ApprovalStamp`, for three reasons:
`test_profile_bundle_cli_approval.py`'s `test_production_has_exactly_one_approval_stamp_writer`
asserts by `rglob` over `src/` that exactly two files call the bundle's stamp-bytes function —
`profile_bundle/approvals.py` (defines it) and `profile_bundle/authoring.py` (the one caller); a
third caller fails that test instantly, and it scans for the call text itself, so even naming it in
a comment here would trip it — this module must not spell that name followed by an opening
parenthesis anywhere, including in prose. `ApprovedVia` is a closed one-member enum baked into the
shipped JSON schema (`models/history.py:180-184`, `resources/career-profile.schema.json`), so it
cannot grow a projection member. And `ApprovalStamp.candidate_content_digest` means *bundle
candidate* — reusing it here would let a bundle approval satisfy a projection gate, conflating two
different facts that happen to share a shape.

The PROPERTIES are copied — digest-bound, collision-free id, controlling-terminal only — the type
is not.

The gate does not prove a template literal is honest; nothing can. It guarantees no literal reaches
a résumé without the owner having seen that exact text.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.paths import digest_token
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import document_bytes

#: `{config_dir}/projection-approvals/`. Its own directory, not inside the bundle: a projection
#: approval is a fact about `projection.yaml`, which itself lives outside the bundle
#: (declaration.py).
APPROVALS_DIR = "projection-approvals"


class ProjectionStamp(BaseModel):
    """One approval of one projection digest.

    `approved_via` is a `Literal` rather than a shared enum, because the bundle's `ApprovedVia` is
    closed and schema-bound (see the module docstring) — this is deliberately its own one-value
    type, not a member borrowed from that one.

    `bundle_digest` binds the approval to the bundle revision the declaration was resolved
    against at approval time, not just to the declaration's own content. `projection_digest` alone
    cannot carry this: it hashes `projection.yaml` only (`declaration.py`'s own docstring), so an
    unedited declaration re-approves silently even when the bundle facts it resolves against have
    moved — the owner would be approving text they never saw. `project_pool` is what reads this
    field back, unconditionally, to detect exactly that drift (D-167).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    projection_stamp_id: str
    projection_digest: str
    bundle_digest: str
    approved_at: datetime
    approved_via: Literal["controlling_terminal"] = "controlling_terminal"


def stamp_path(config_dir: Path, digest: str) -> Path:
    """`{config_dir}/projection-approvals/sha256-<hex>.yaml`.

    Keyed by digest, not by a name: a stamp outlives the declaration that produced it, and two
    declarations with the same content must not alias to two stamp files — while two declarations
    with DIFFERENT content (different digests) must never alias to the SAME stamp file. That second
    half is what makes an edited-but-unapproved declaration have no stamp, rather than inheriting
    one it was never shown for.

    `digest_token` (`profile_bundle/paths.py`) both derives the filename-safe token and validates
    `digest` first via `require_digest` — a malformed digest (no `sha256:` prefix, wrong hex
    length, or containing a path separator or `..`) raises `BundlePathError` here rather than
    silently becoming a path.
    """
    return config_dir / APPROVALS_DIR / f"{digest_token(digest)}.yaml"


def stamp_exists(config_dir: Path, digest: str) -> bool:
    """Whether `digest` has been approved. A stamp for a different digest does not count."""
    return stamp_path(config_dir, digest).is_file()


def write_stamp(
    config_dir: Path, *, digest: str, bundle_digest: str, approved_at: datetime
) -> Path:
    """Write the stamp for exactly this digest. Idempotent — one digest, one file, because the
    path is a pure function of the digest: writing it again overwrites the same file rather than
    creating a second one.

    `projection_stamp_id` is built as `"projection-approval." + digest_token(digest)`: with exactly
    one dot, the prefix and the token can never be re-bracketed against each other. This is the same
    property `approvals.py`'s `build_approval_stamp` enforces at runtime for a *caller-supplied*
    scope (`profile_bundle/approvals.py:202-213`) — here it holds by construction instead, because
    `digest_token`'s token is `require_digest`-validated hex with no `.` to begin with.

    Always `approved_via="controlling_terminal"` — there is no parameter for it, matching the
    property copied from `profile_bundle.approvals`: an approval is filed by the command layer that
    asked the owner on a controlling terminal, never constructed with an arbitrary provenance.
    """
    stamp = ProjectionStamp(
        projection_stamp_id=f"projection-approval.{digest_token(digest)}",
        projection_digest=digest,
        bundle_digest=bundle_digest,
        approved_at=approved_at,
    )
    path = stamp_path(config_dir, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    logical = PurePosixPath(f"{APPROVALS_DIR}/{path.name}")
    path.write_bytes(document_bytes(stamp.model_dump(mode="json"), logical_path=logical))
    return path


def read_stamp(config_dir: Path, digest: str) -> ProjectionStamp:
    """Read back the stamp written for `digest`, through the same restricted loader
    `document_bytes` writes against (`profile_bundle.yaml_loader.load_yaml_bytes`) — the read side
    of the exact round-trip `write_stamp` already verifies at write time.

    Guards its own body. `stamp_exists` (`project_pool`'s own gate) proves only that a file
    existed at this path at the moment it was checked — never that the bytes on disk still parse,
    or still satisfy the CURRENT `ProjectionStamp` model. A stamp written before `bundle_digest`
    was required (this task's own schema change) is exactly such a file: valid YAML that fails
    `model_validate`, not a read failure at all. A file removed in the gap between the two calls
    is a second, narrower way to reach the same arm. Both are converted to `ProfileBundleError`
    here, one level up from `load_yaml_bytes`'s own catch-all
    (`profile_bundle/yaml_loader.py`), which already raises that type for anything unexpected
    *inside* the loader; this guard covers the two things outside the loader's own boundary — the
    read (`OSError`) and the model validation (`ValidationError`) — so nothing escapes this
    function as a bare, untyped exception.

    `ProfileBundleError`, not `ProjectionError`: `ProjectionIssue` has no member for "this file
    should have been well-formed and was not" — it is not a projection business outcome — and
    `cli/projection_cmd.py`'s `_boundary_outcome` already has a dedicated arm for exactly this
    type, reporting it as `INTERNAL_ERROR`.
    """
    path = stamp_path(config_dir, digest)
    logical = PurePosixPath(f"{APPROVALS_DIR}/{path.name}")
    try:
        raw = load_yaml_bytes(path.read_bytes(), logical_path=logical)
        return ProjectionStamp.model_validate(raw)
    except (OSError, ValidationError) as exc:
        raise ProfileBundleError(
            f"{logical}: stamp could not be read ({type(exc).__name__})"
        ) from exc
