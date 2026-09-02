"""The seeds-no-resolver-claims report (D-422), and the registry it reads from.

The load-bearing test here is the REGISTRY GUARD. Every other property of this report is
arithmetic; the one that fails silently is a resolver joining `boardwatch.lanes` and not
`SEED_RESOLVERS`, which makes that resolver's whole backlog read as unclaimed and sends someone
to build a lane that already exists.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import boardwatch.lanes
from boardwatch.reports.seed_claims import (
    SEED_RESOLVERS,
    build_seed_claim_report,
    claimed_hosts,
)
from boardwatch.store.seed_queries import UnclaimedHost


def _modules_declaring_seed_hosts() -> set[str]:
    """Lane modules with a module-level `SEED_HOSTS`, found by AST rather than by import.

    Parsed, not imported and `hasattr`-ed: an import-time `SEED_HOSTS` bound inside a function or
    re-exported from another module would satisfy `hasattr` while declaring nothing, and this test
    is asking specifically about DECLARATIONS.
    """
    root = Path(boardwatch.lanes.__file__).parent
    found = set()
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            targets = (
                node.targets if isinstance(node, ast.Assign)
                else [node.target] if isinstance(node, ast.AnnAssign)
                else []
            )
            if any(isinstance(t, ast.Name) and t.id == "SEED_HOSTS" for t in targets):
                found.add(path.stem)
    return found


def test_every_lane_that_declares_a_seed_catalog_is_in_the_registry() -> None:
    """A resolver missing from `SEED_RESOLVERS` makes its own backlog report as unclaimed.

    Matched on the catalog VALUES rather than on the lane name, so renaming a lane cannot quietly
    satisfy this while the registry still points at nothing.
    """
    registered = set(SEED_RESOLVERS.values())
    declaring = _modules_declaring_seed_hosts()
    assert declaring, "no lane declares SEED_HOSTS — this guard would be vacuous"
    for name in declaring:
        module = importlib.import_module(f"boardwatch.lanes.{name}")
        catalog = (module.SEED_HOSTS, module.SEED_HOST_SUFFIXES)
        assert catalog in registered, (
            f"lane {name!r} declares a seed catalog that `SEED_RESOLVERS` does not carry, so "
            f"every seed it can drain would be reported as claimable by nothing"
        )


def test_claimed_hosts_unions_every_registered_resolver() -> None:
    hosts, suffixes = claimed_hosts()
    for lane_hosts, lane_suffixes in SEED_RESOLVERS.values():
        assert lane_hosts <= hosts and lane_suffixes <= suffixes


def test_the_split_is_summed_from_the_breakdown_rather_than_taken_on_trust() -> None:
    """One reading, so a total and its breakdown cannot come from two reads across a write."""
    report = build_seed_claim_report(
        unresolved=100,
        hosts=(
            UnclaimedHost("grnh.se", 60, ("indeed",), 143),
            UnclaimedHost("click.appcast.io", 21, ("indeed", "jsonld"), 143),
        ),
    )
    assert (report.unclaimed, report.claimed) == (81, 19)
    assert report.unclaimed_share == 0.81


def test_an_empty_queue_reports_no_share_rather_than_zero_percent() -> None:
    """A share of nothing is not zero percent, and printing 0.0% would read as a healthy drain."""
    report = build_seed_claim_report(unresolved=0, hosts=())
    assert report.unclaimed_share is None
    assert (report.unclaimed, report.claimed) == (0, 0)
