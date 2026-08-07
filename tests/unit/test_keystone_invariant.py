"""Machine-enforced keystone abstain invariant (P2 item 3).

CLAUDE.md's keystone invariant: every eligibility rule declares which profile fields it
reads, and if a declared field is missing it must ABSTAIN — never `met`, never `unmet`.
Until this test, that was enforced only by CONVENTION: each resolver in resolve.py
hand-writes an UNKNOWN Resolution at its own missing-fact check. Nothing MACHINE-CHECKED
that a resolver actually does this, so a future family that forgot would silently decide a
fresh user's undeclared facts as eligible or ineligible instead of abstaining.

This iterates `registry()` itself, never a hardcoded family list, so a resolver registered
after this test is written is covered automatically without editing this file.
"""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.detect import Detection
from boardwatch.eligibility.facts import Facts
from boardwatch.eligibility.resolve import UNKNOWN, registry, resolve


@pytest.fixture()
def catalog(tmp_path: Path):
    return load_rules(tmp_path / "no-override")


def test_every_resolver_abstains_on_empty_facts(catalog) -> None:
    """Empty Facts() (every field None) must abstain on EVERY pattern, in EVERY family.

    `patterns[0]` alone is not enough: `experience_years` and `clearance` both contain
    patterns that short-circuit to UNKNOWN for a reason that has NOTHING to do with a
    missing fact (`scoped_years_minimum` -> "no per-skill durations stored",
    `clearable_required` -> "obtain-after-hire eligibility is not stored"). Resolving only
    the catalog's first pattern per family would pass VACUOUSLY for those two families if
    `rules.yaml` ever reordered patterns so a fact-blind pattern landed at index 0 while the
    real "fact not declared" abstain line regressed — exactly the "detection so degenerate
    the resolver never reads the fact" failure this test exists to catch. Iterating every
    pattern in the family, not just one, forces the fact-reading branch to execute for at
    least one pattern regardless of catalog order, and as a bonus catches a newly added
    pattern within an existing family that forgot to abstain.

    Every family resolver's missing-fact check runs before it reads `detection.values`
    (verified by reading resolve.py), so `values={}` never causes a crash for any pattern.

    A resolver that forgot to abstain returns `met` or `unmet` here instead of `unknown`,
    and the assertion below names exactly which (family, pattern) did it.
    """
    empty_facts = Facts()
    failures: list[tuple[str, str, str, str]] = []
    for family_id in registry():
        family = catalog.family(family_id)
        for pattern in family.patterns:
            detection = Detection(family=family_id, pattern=pattern, span=(0, 0), values={})
            resolution = resolve(detection, empty_facts, family)
            if resolution.disposition != UNKNOWN:
                failures.append(
                    (family_id, pattern.id, resolution.disposition, resolution.rationale)
                )
    assert failures == [], (
        "resolver(s) decided ELIGIBLE/INELIGIBLE on empty facts instead of abstaining "
        f"(family, pattern, disposition, rationale): {failures}"
    )
