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
    """Empty Facts() (every field None) must abstain in every family, never decide.

    One representative detection per registered family — its catalog's first pattern. The
    choice of pattern does not matter: every resolver's missing-fact check runs before any
    pattern-specific branch (verified by reading resolve.py), so any pattern from the family
    reaches the same abstain. `degree` is the sharpest case: it declares TWO inputs
    (`highest_degree`, `total_years_experience`) and must abstain with both None, which is
    exactly the universal property this test checks — not a family-specific special case.

    A resolver that forgot to abstain returns `met` or `unmet` here instead of `unknown`,
    and the assertion below names exactly which family did it.
    """
    empty_facts = Facts()
    failures: list[tuple[str, str, str]] = []
    for family_id in registry():
        family = catalog.family(family_id)
        pattern = family.patterns[0]
        detection = Detection(family=family_id, pattern=pattern, span=(0, 0), values={})
        resolution = resolve(detection, empty_facts, family)
        if resolution.disposition != UNKNOWN:
            failures.append((family_id, resolution.disposition, resolution.rationale))
    assert failures == [], (
        "resolver(s) decided ELIGIBLE/INELIGIBLE on empty facts instead of abstaining "
        f"(family, disposition, rationale): {failures}"
    )
