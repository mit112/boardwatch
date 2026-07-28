"""Group 2: data-file admission (R7) and registry invariants (R8, added in Task 5).

Semantic detection of "is this list personal?" is not decidable, and trying it is
what made the first attempt at these checks fire on legitimate product content.
Admission is decidable: a new data file cannot land without a diff-visible entry
stating what it is and where it came from.
"""

from __future__ import annotations

import hashlib

from tools.generalization import allowlists as al
from tools.generalization.discovery import DiscoveryError, Repo
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
# uv.lock and alembic.ini are belt and braces: their suffixes are outside DATA_SUFFIXES
# today, so they are already out of scope, and listing them keeps the classification
# correct if DATA_SUFFIXES ever grows.
TOOLING_CONFIG: frozenset[str] = frozenset(
    {"pyproject.toml", "uv.lock", "alembic.ini", ".pre-commit-config.yaml"}
)

# A closed vocabulary. kind is contributor-supplied, so an unconstrained string lets a
# typo ("fixtures") or a deliberate mislabel silently change how an entry is treated.
ALLOWED_DATA_KINDS: frozenset[str] = frozenset(
    {"taxonomy", "company_enumeration", "fixture", "corpus", "template"}
)

# Living product data that churns and carries its own validators. Pinning it would put a
# hash bump in the path of every community registry PR, which is how checks get weakened
# or deleted. The exemption is bound to LITERAL PATHS rather than to a kind label, for the
# same reason section 5.2 binds the registry designation to a path: a corpus mislabelled
# "taxonomy" must not inherit the exemption and become append-anything-forever.
UNPINNED_PATHS: frozenset[str] = frozenset(
    {
        "src/boardwatch/extract/taxonomy.yaml",
        "src/boardwatch/registry/companies.yaml",
    }
)

# Provenance values that make this repo a redistributor, so a license is required.
LICENSED_PROVENANCE: frozenset[str] = frozenset({"public", "licensed"})

# Only the workflow directory. The shape rules additionally exclude the checker's own
# sources because those .py files deliberately hold PII-shaped literals to test the rules.
# That reasoning does not extend to DATA files, so R7 covers tools/generalization/** and
# tests/generalization/** like anywhere else: a corpus dropped beside the engine's own
# tests must still be admitted explicitly.
_EXCLUDED_PREFIXES = (".github/",)
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

    for path in sorted(scope - known):
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
    for path in sorted(known - scope):
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
        if entry.kind not in ALLOWED_DATA_KINDS:
            violations.append(
                Violation(
                    "R7",
                    path,
                    None,
                    f"kind={entry.kind!r} is not one of {sorted(ALLOWED_DATA_KINDS)!r}. "
                    "An unrecognised kind changes how the entry is treated without saying so",
                )
            )
        if not entry.reason.strip():
            violations.append(
                Violation(
                    "R7",
                    path,
                    None,
                    "'reason' is empty. The entry IS the justification, so a blank one is a "
                    "rubber stamp",
                )
            )
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
        if entry.provenance in LICENSED_PROVENANCE and not entry.license_:
            violations.append(
                Violation(
                    "R7",
                    path,
                    None,
                    f"provenance={entry.provenance!r} makes this repo a redistributor and "
                    "requires a 'license'",
                )
            )
        if path in UNPINNED_PATHS:
            if entry.pin != "none":
                violations.append(
                    Violation(
                        "R7",
                        path,
                        None,
                        "this path is living product data with its own validators and must "
                        "use pin='none'",
                    )
                )
            continue
        if not entry.pin.startswith("sha256:"):
            violations.append(
                Violation(
                    "R7",
                    path,
                    None,
                    "requires a sha256 pin so its content cannot drift after review. Only "
                    f"{sorted(UNPINNED_PATHS)!r} are exempt, and the exemption is bound to "
                    "the path, not to the kind label",
                )
            )
            continue
        found = repo.by_path(path)
        if found is None:
            raise DiscoveryError(
                f"{path!r} is in the inventory scope but not readable from the discovered "
                "file set, so its pin cannot be verified. Refusing to report a clean scan"
            )
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
