"""Entry point: `python -m tools.generalization`.

Exit codes: 0 clean, 1 violations found, 2 the gate could not run to completion.
A gate that cannot see the tree, or whose rule crashed, has not passed: it has broken.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from tools.generalization.defaults import (
    check_collection_defaults,
    check_defaults_snapshot,
    check_init_prompts,
)
from tools.generalization.discovery import (
    PRODUCTION_MINIMUM_FILES,
    DiscoveryError,
    discover,
    find_repo_root,
)
from tools.generalization.fixtures import (
    check_fixture_coverage,
    check_fixture_pins,
    check_fixture_review_due,
)
from tools.generalization.inventory import check_inventory, check_registry_invariants
from tools.generalization.model import Rule, Violation
from tools.generalization.packaging import check_wheel_completeness
from tools.generalization.shape import check_artifact_files, check_shapes

ALL_RULES: tuple[Rule, ...] = (
    check_shapes,               # R1 R2 R3 R4
    check_artifact_files,       # R5 R6
    check_inventory,            # R7
    check_registry_invariants,  # R8
    check_collection_defaults,  # R9
    check_defaults_snapshot,    # R10
    check_init_prompts,         # R11
    check_wheel_completeness,   # R12
    check_fixture_coverage,     # R13
    check_fixture_pins,         # R14
    check_fixture_review_due,   # R15
)


def _order(item: Violation) -> tuple[int, str, str, int]:
    """Sort R2 before R10: plain string order puts 'R10' first."""
    return (len(item.rule), item.rule, item.path, item.line or 0)


def run(root: Path) -> list[Violation]:
    # The production floor: a truncated scan must fail, not report a clean tree.
    repo = discover(root, minimum_files=PRODUCTION_MINIMUM_FILES)
    found: list[Violation] = []
    for rule in ALL_RULES:
        found.extend(rule(repo))
    return found


def main() -> int:
    try:
        violations = run(find_repo_root(Path.cwd().resolve()))
    except DiscoveryError as exc:
        print(f"generalization: FAILED, {exc}", file=sys.stderr)
        return 2
    except Exception:
        traceback.print_exc()
        print(
            "generalization: FAILED, the scan did not finish, so this is not a clean tree.",
            file=sys.stderr,
        )
        return 2
    if not violations:
        print("generalization: OK")
        return 0
    print(f"generalization: {len(violations)} violation(s)", file=sys.stderr)
    for violation in sorted(violations, key=_order):
        print(f"  {violation.render()}", file=sys.stderr)
    print(
        "\nSee 'What must never enter this repo' in CONTRIBUTING.md. Weakening or "
        "removing a generalization check is a security-sensitive change.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
