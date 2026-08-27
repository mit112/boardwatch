"""The committed React bundle must not outlive the TypeScript it was built from.

`src/boardwatch/web/static/` holds a Vite build committed to the repository, so that
`pip install boardwatch` needs no node toolchain (delivery design §10). The failure that
costs weeks is silent: somebody edits `web/src/`, forgets `make web`, and every wheel from
then on serves the previous UI with nothing red anywhere.

`make check` cannot rebuild the bundle to find out — the gate runs on three operating
systems with no node installed — so it checks the next best thing. `make web` records a
sha256 over every build input under `web/`, and the tests here recompute it. A stale bundle
becomes a failing test on the commit that caused it.

This module is also the manifest WRITER, run as a script by `make web`. One implementation,
so what gets recorded and what gets checked cannot drift apart.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPO_ROOT / "web"
MANIFEST_PATH = WEB_ROOT / "bundle-inputs.sha256"
MANIFEST_REL = "web/bundle-inputs.sha256"

# Every failure message ends with this. A freshness check whose message does not say what to
# do gets diagnosed from scratch by whoever hits it next.
FIX = f"run `make web` and commit the result (the bundle and {MANIFEST_REL})"

# Directory names pruned from the walk, at any depth under `web/`.
#   node_modules  installed, not authored. `package-lock.json` is the input that pins it.
#   dist          Vite's DEFAULT outDir. The real outDir is `../src/boardwatch/web/static`,
#                 outside this tree, but `.gitignore`'s unanchored `dist/` means a build that
#                 lands one here is untracked — hashing output would also make the manifest
#                 irreproducible from a clean clone.
EXCLUDED_DIRS = frozenset({"node_modules", "dist"})

# Skipped by file name. The manifest cannot hash itself. `.DS_Store` is not a build input and
# is gitignored, so recording one would fail this check on every machine except the one that
# created it.
EXCLUDED_FILES = frozenset({"bundle-inputs.sha256", ".DS_Store"})


def build_inputs() -> dict[str, str]:
    """sha256 of every build input under `web/`, keyed by repo-relative POSIX path.

    Deliberately a walk with exclusions rather than an extension allowlist: a new PostCSS or
    Tailwind config, a `public/` asset, or a whole new source directory is covered the day it
    lands, without anybody remembering to widen a list here.
    """
    inputs: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(WEB_ROOT):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIRS]
        for filename in filenames:
            if filename in EXCLUDED_FILES:
                continue
            path = Path(dirpath) / filename
            rel = path.relative_to(REPO_ROOT).as_posix()
            inputs[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not inputs:
        # Refused on both paths: an empty walk would let `make web` write an empty manifest
        # that then matches, which is this check silently disarming itself.
        raise RuntimeError(
            f"no build inputs found under {WEB_ROOT}. If the web source tree moved, this "
            "freshness check and Vite's outDir both need updating"
        )
    return inputs


def render(inputs: dict[str, str]) -> str:
    """The manifest text: `<sha256>  <repo-relative path>`, sorted by path, LF-terminated."""
    return "".join(f"{inputs[rel]}  {rel}\n" for rel in sorted(inputs))


def write_manifest() -> dict[str, str]:
    inputs = build_inputs()
    MANIFEST_PATH.write_text(render(inputs), encoding="utf-8", newline="\n")
    return inputs


def _committed_text() -> str:
    if not MANIFEST_PATH.is_file():
        raise AssertionError(
            f"{MANIFEST_REL} is missing, so nothing pins the committed bundle in "
            f"src/boardwatch/web/static/ to the sources in web/: {FIX}"
        )
    # Read as bytes and decode: universal-newline translation would let a CRLF manifest pass
    # a byte-for-byte comparison.
    return MANIFEST_PATH.read_bytes().decode("utf-8")


def _parse(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, separator, rel = line.partition("  ")
        entries[rel if separator else line] = digest
    return entries


def test_manifest_exists() -> None:
    """A missing manifest fails. Skipping here is the same as having no check at all."""
    assert MANIFEST_PATH.is_file(), (
        f"{MANIFEST_REL} is missing, so a stale committed bundle could not be detected: {FIX}"
    )


def test_every_build_input_is_listed() -> None:
    """The direction that matters: an input nobody hashed is how this check goes blind."""
    unlisted = sorted(set(build_inputs()) - set(_parse(_committed_text())))
    assert not unlisted, (
        f"{len(unlisted)} build input(s) under web/ are absent from {MANIFEST_REL}, so "
        f"editing them could never fail this check: {', '.join(unlisted)}. {FIX}"
    )


def test_manifest_matches_working_tree() -> None:
    inputs = build_inputs()
    expected = render(inputs)
    committed = _committed_text()
    if committed == expected:
        return

    listed = _parse(committed)
    changed = sorted(rel for rel, digest in inputs.items() if listed.get(rel, digest) != digest)
    unlisted = sorted(set(inputs) - set(listed))
    removed = sorted(set(listed) - set(inputs))
    lines = [f"{MANIFEST_REL} does not match the working tree. {FIX}."]
    for label, paths in (("changed", changed), ("not listed", unlisted), ("gone", removed)):
        for rel in paths:
            lines.append(f"  {label}: {rel}")
    if not (changed or unlisted or removed):
        # Same paths, same hashes, different bytes: ordering, spacing or line endings.
        lines.append("  the entries agree; the manifest's own formatting is out of date")
    raise AssertionError("\n".join(lines))


if __name__ == "__main__":  # `make web` writes the manifest through this entry point.
    recorded = write_manifest()
    print(f"{MANIFEST_REL}: {len(recorded)} build inputs")
