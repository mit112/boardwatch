"""The tectonic version pin lives in two places; this is the drift detector.

`Dockerfile`'s `ARG TECTONIC_VERSION` and `.github/actions/setup-typesetting`'s
`tectonic-version` input default are two sites for one fact (D-114). Both build a release-tarball
URL from it, so a silent divergence means the container and the runners typeset with different
binaries — benign while both versions happen to work, and invisible until one stops.

This is the fourth hand-maintained mirror the program has been bitten by; `reports/manifest.py`'s
`_assert_exhaustive` is the same idea applied to `Settings` fields.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
ACTION = REPO_ROOT / ".github" / "actions" / "setup-typesetting" / "action.yml"


def _dockerfile_pin() -> str:
    """The `ARG TECTONIC_VERSION=` default, or a failure naming the file if the line is renamed."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    match = re.search(r"^ARG\s+TECTONIC_VERSION=(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, f"{DOCKERFILE}: no `ARG TECTONIC_VERSION=<version>` line"
    return match.group(1)


def _action_pin() -> str:
    """The composite action's `tectonic-version` input default, by the same contract."""
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    inputs = action.get("inputs", {})
    assert "tectonic-version" in inputs, f"{ACTION}: no `tectonic-version` input"
    default = inputs["tectonic-version"].get("default")
    assert default is not None, f"{ACTION}: `tectonic-version` declares no default"
    return str(default)


def test_the_tectonic_pin_agrees_across_its_two_homes() -> None:
    dockerfile_pin = _dockerfile_pin()
    action_pin = _action_pin()
    assert dockerfile_pin == action_pin, (
        f"tectonic pin has drifted: {DOCKERFILE.name} says {dockerfile_pin!r}, "
        f"setup-typesetting/action.yml says {action_pin!r}. They are two sites for one fact — "
        f"move both or neither."
    )
