"""Group 2: data-file admission (R7) and registry invariants (R8, added in Task 5).

Semantic detection of "is this list personal?" is not decidable, and trying it is
what made the first attempt at these checks fire on legitimate product content.
Admission is decidable: a new data file cannot land without a diff-visible entry
stating what it is and where it came from.
"""

from __future__ import annotations

import hashlib

from tools.generalization import allowlists as al
from tools.generalization.discovery import Repo
from tools.generalization.model import Violation

DATA_SUFFIXES: frozenset[str] = frozenset(
    {
        ".yaml",
        ".yml",
        ".json",
        ".jsonl",
        ".csv",
        ".tsv",
        ".toml",
        ".tex",
        ".typ",
        ".txt",
        ".mako",
    }
)

# Build and tooling configuration, not data. Group 1's shape scan still covers these.
TOOLING_CONFIG: frozenset[str] = frozenset(
    {"pyproject.toml", "uv.lock", "alembic.ini", ".pre-commit-config.yaml"}
)

# Content that should not drift silently. Living product data (taxonomy, registry)
# is deliberately excluded: pinning it would put a hash bump in the path of every
# community registry PR, which is how checks get weakened or deleted.
PIN_REQUIRED_KINDS: frozenset[str] = frozenset({"fixture", "corpus", "template"})

_EXCLUDED_PREFIXES = (".github/", "tools/generalization/", "tests/generalization/")
ALLOWLIST_PATH = "tools/generalization/allowlists.py"


def inventory_scope(repo: Repo) -> set[str]:
    return {
        entry.path
        for entry in repo.files
        if entry.suffix in DATA_SUFFIXES
        and entry.path not in TOOLING_CONFIG
        and not entry.path.startswith(_EXCLUDED_PREFIXES)
    }


def check_inventory(repo: Repo) -> list[Violation]:
    """R7: every data file in the tree is a reviewed, justified entry."""
    violations: list[Violation] = []
    scope = inventory_scope(repo)
    known = set(al.SHIPPED_DATA)

    unknown = sorted(scope - known)
    stale = sorted(known - scope)

    for path in unknown:
        violations.append(
            Violation(
                "R7",
                path,
                None,
                "new data file is not in SHIPPED_DATA. Add an entry stating kind, reason, "
                "provenance and pin, or do not ship it. Harvested corpora need source, "
                "license and a sha256 pin",
            )
        )
    # Only report stale entries if the repo has no unknown files
    if not unknown:
        for path in stale:
            violations.append(
                Violation(
                    "R7",
                    ALLOWLIST_PATH,
                    None,
                    f"stale SHIPPED_DATA entry {path!r}: that file is no longer in scope",
                )
            )

    for path in sorted(scope & known):
        entry = al.SHIPPED_DATA[path]
        needs_pin = entry.kind in PIN_REQUIRED_KINDS or entry.provenance != "first-party"
        if entry.provenance != "first-party" and not entry.source:
            violations.append(
                Violation(
                    "R7",
                    path,
                    None,
                    f"provenance={entry.provenance!r} requires a 'source' "
                    "(branch@commit or URL)",
                )
            )
        if not needs_pin:
            if entry.pin != "none":
                violations.append(
                    Violation(
                        "R7",
                        path,
                        None,
                        f"kind={entry.kind!r} is living product data and must use pin='none'",
                    )
                )
            continue
        if not entry.pin.startswith("sha256:"):
            violations.append(
                Violation(
                    "R7",
                    path,
                    None,
                    f"kind={entry.kind!r} provenance={entry.provenance!r} requires a "
                    "sha256 pin so its content cannot drift after review",
                )
            )
            continue
        found = repo.by_path(path)
        if found is None:
            continue
        actual = hashlib.sha256(found.abspath.read_bytes()).hexdigest()
        expected = entry.pin.removeprefix("sha256:")
        if actual != expected:
            violations.append(
                Violation(
                    "R7",
                    path,
                    None,
                    f"content changed: pin says {expected[:12]}, file is {actual[:12]}. "
                    "Re-review the change, then update the pin",
                )
            )
    return violations
