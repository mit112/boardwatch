"""Group 2: data-file admission (R7) and registry invariants (R8, added in Task 5).

Semantic detection of "is this list personal?" is not decidable, and trying it is
what made the first attempt at these checks fire on legitimate product content.
Admission is decidable: a new data file cannot land without a diff-visible entry
stating what it is and where it came from.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import PurePosixPath

import yaml

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

# Closed for the same reason as ALLOWED_DATA_KINDS. The license check keys on membership of
# LICENSED_PROVENANCE, so a free-form label ("third-party", "harvested", "Public") would
# slip past it. The source check keys on "not first-party" and is fail-closed already.
ALLOWED_PROVENANCE: frozenset[str] = frozenset(
    {"first-party", "synthetic", "public", "licensed"}
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
        if entry.provenance not in ALLOWED_PROVENANCE:
            violations.append(
                Violation(
                    "R7",
                    path,
                    None,
                    f"provenance={entry.provenance!r} is not one of "
                    f"{sorted(ALLOWED_PROVENANCE)!r}. An unrecognised provenance skips the "
                    "license requirement without saying so",
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


def _data_literals(source: str) -> set[str]:
    """Every string constant in `source` that names a data file.

    Prose is excluded by requiring the literal to contain no whitespace. A docstring or an
    error message that happens to end in "companies.yaml" is not a path reference, and
    treating it as one fires the rule on legitimate content, which is the exact failure this
    phase exists to correct. A real reference is a bare relative filename.

    Raises SyntaxError, which the caller converts into a violation.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        value = node.value
        if any(character.isspace() for character in value):
            continue
        if PurePosixPath(value).suffix.lower() in DATA_SUFFIXES:
            found.add(value)
    return found


def _registry_rows(source: str) -> tuple[list[dict[str, object]], str | None]:
    """The registry's rows, or a reason the document could not be read as the registry.

    Every unrecognised shape returns a reason rather than an empty row list. An empty row
    list reads as "no bad tags", which is how this check goes silently dead: restructure the
    YAML, update the loader in the same commit, and the gate stays green while a personal
    annotation ships.
    """
    try:
        raw = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        return [], f"could not be parsed as YAML ({type(exc).__name__})"
    if raw is None:
        return [], "is empty"
    if not isinstance(raw, dict):
        return [], f"has a top-level {type(raw).__name__}, expected a mapping"
    if "companies" not in raw:
        return [], "has no top-level 'companies' key"
    rows = raw["companies"]
    if rows is None:
        return [], "has an empty 'companies' key"
    if not isinstance(rows, list):
        return [], f"has 'companies' as a {type(rows).__name__}, expected a list"
    typed: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            return [], f"has 'companies' item {index} as a {type(row).__name__}, expected a mapping"
        typed.append(row)
    return typed, None


def _registry_tags(
    rows: list[dict[str, object]],
) -> tuple[list[tuple[str, str]], list[str]]:
    """(tag, slug) for every tag in use, plus one problem per row whose tags are malformed."""
    used: list[tuple[str, str]] = []
    problems: list[str] = []
    for row in rows:
        slug = str(row.get("slug", "?"))
        tags = row.get("tags")
        if tags is None:
            continue
        if not isinstance(tags, list):
            problems.append(
                f"entry {slug!r} has 'tags' as a {type(tags).__name__}, expected a list"
            )
            continue
        for tag in tags:
            used.append((str(tag), slug))
    return used, problems


def check_registry_invariants(repo: Repo) -> list[Violation]:
    """R8: one registry, at one path, read from one place, with a closed tag vocabulary."""
    violations: list[Violation] = []

    designated = sorted(
        path for path, entry in al.SHIPPED_DATA.items() if entry.kind == "company_enumeration"
    )
    if designated != [al.CANONICAL_REGISTRY_PATH]:
        violations.append(
            Violation(
                "R8",
                ALLOWLIST_PATH,
                None,
                "exactly one company_enumeration is allowed and it must be "
                f"{al.CANONICAL_REGISTRY_PATH!r}, found {designated!r}. A personal target "
                "list does not become acceptable by being inventoried",
            )
        )

    loader = repo.by_path(al.REGISTRY_LOADER_PATH)
    if loader is None:
        violations.append(
            Violation("R8", al.REGISTRY_LOADER_PATH, None, "the registry loader is missing")
        )
    else:
        try:
            literals = _data_literals(loader.text)
        except SyntaxError as exc:
            violations.append(
                Violation(
                    "R8",
                    al.REGISTRY_LOADER_PATH,
                    None,
                    f"could not be parsed as Python ({exc.msg}), so the single-loader "
                    "invariant could not be checked. An unreadable loader means this check "
                    "is disabled, not that it passed",
                )
            )
        else:
            expected = {PurePosixPath(al.CANONICAL_REGISTRY_PATH).name}
            if literals != expected:
                violations.append(
                    Violation(
                        "R8",
                        al.REGISTRY_LOADER_PATH,
                        None,
                        f"loader must reference only {sorted(expected)!r}, "
                        f"found {sorted(literals)!r}. Write the registry filename as a plain "
                        "string literal in this module: this rule cannot follow a name "
                        "imported from elsewhere, interpolated or built by concatenation, and "
                        "a second data literal here means a second bulk list is being read",
                    )
                )

    registry = repo.by_path(al.CANONICAL_REGISTRY_PATH)
    if registry is None:
        violations.append(
            Violation("R8", al.CANONICAL_REGISTRY_PATH, None, "the registry file is missing")
        )
        return violations
    rows, problem = _registry_rows(registry.text)
    if problem is not None:
        violations.append(
            Violation(
                "R8",
                al.CANONICAL_REGISTRY_PATH,
                None,
                f"the registry {problem}, so the tag vocabulary could not be checked. An "
                "unrecognised shape is reported, never skipped: it means this check is "
                "disabled, not that it passed",
            )
        )
    used, problems = _registry_tags(rows)
    for detail in problems:
        violations.append(Violation("R8", al.CANONICAL_REGISTRY_PATH, None, detail))
    for tag, slug in used:
        if tag not in al.ALLOWED_REGISTRY_TAGS:
            violations.append(
                Violation(
                    "R8",
                    al.CANONICAL_REGISTRY_PATH,
                    None,
                    f"entry {slug!r} uses tag {tag!r}, outside the public vocabulary "
                    f"{sorted(al.ALLOWED_REGISTRY_TAGS)!r}. Tags describe the product, "
                    "not one user's interest in a company",
                )
            )
    return violations
