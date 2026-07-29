"""The catalog is a TRUST ROOT: a wrong pattern is a wrong verdict (D-P2-7). Every
malformed shape has its own raise site and its own test, and every raise site names the
offending document so a user editing an override gets a usable message.

The suppressor and cue-consumption tests are POSITIVE CONTROLS against silent drop: the
catalog carries five suppressor kinds plus per-pattern consumed cues and doc-level idioms,
and a loader that quietly modelled only one of them would report green while dropping the
mechanism that keeps a hedge, a company-side subject or a cross-sentence escape from
turning into a wrong verdict. Those are prototype findings 31 and 59; the loader ports
their load-time guards, and each guard has a test beside its positive control."""

import re
from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import (
    CATALOG_REVISION,
    CatalogError,
    bundled_rules_text,
    load_rules,
)
from boardwatch.eligibility.facts import Policy


def _write(config_dir: Path, body: str) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "rules.yaml"
    path.write_text(body, encoding="utf-8")
    return path


MINIMAL = """
version: 1
negation_cues: ["not"]
families:
  - id: degree
    label: Degree
    fact: highest_degree
    answer_type: choice
    default_policy: preference
    question: "Highest degree?"
    fields:
      - name: highest_degree
        type: choice
        choices: [none, bachelor]
        ranks: {none: 0, bachelor: 3}
    implies_vocabulary: [degree_required]
    exclusive_groups: []
    patterns:
      - id: bachelor_required
        requiredness: required
        implies: degree_required
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is required"
        pattern: "bachelor"
"""


# A family carrying one of every optional pattern member, so the loader is proven to
# COMPILE and CARRY each rather than silently drop it. negation_cues declares the cue this
# pattern consumes and the idiom list is non-empty so cue_idioms is stamped.
MINIMAL_RICH = """
version: 1
negation_cues: ["not", "no"]
negation_cue_idioms:
  - "unless\\\\s+otherwise\\\\s+noted"
families:
  - id: degree
    label: Degree
    fact: highest_degree
    answer_type: choice
    default_policy: preference
    question: "Highest degree?"
    fields:
      - name: highest_degree
        type: choice
        choices: [none, bachelor]
        ranks: {none: 0, bachelor: 3}
    implies_vocabulary: [degree_required]
    exclusive_groups: []
    patterns:
      - id: bachelor_required
        requiredness: required
        implies: degree_required
        scope: sentence
        required_rank: 3
        requirement_text: "A bachelor's degree is required"
        subject_suppressors:
          - "our team"
        suppressed_by_unit:
          - "or equivalent"
        suppressed_by_sentence:
          - "or an? equivalent"
        abstain_by:
          - "or equivalent experience"
        consumes_cues: ["no"]
        pattern: "bachelor"
"""


def test_the_bundled_catalog_loads(tmp_path: Path) -> None:
    catalog = load_rules(tmp_path / "no-override")
    assert catalog.source == "bundled"
    assert [f.id for f in catalog.families] == [
        "work_auth", "experience_years", "clearance", "degree",
    ]
    assert len(catalog.negation_cues) == 26
    assert sum(len(f.patterns) for f in catalog.families) == 39


def test_the_bundled_catalog_carries_every_suppressor_kind(tmp_path: Path) -> None:
    """A loader that modelled only one suppressor kind would load GREEN and silently
    drop the rest, which is prototype finding 31's silent class. Census the loaded
    catalog against the reviewed artifact so a dropped kind fails here, not at resolve
    time (D-P2-7)."""
    catalog = load_rules(tmp_path / "no-override")
    patterns = [p for f in catalog.families for p in f.patterns]
    census = {
        "suppressed_by_unit": sum(bool(p.suppressed_by_unit) for p in patterns),
        "suppressed_by_sentence": sum(bool(p.suppressed_by_sentence) for p in patterns),
        "subject_suppressors": sum(bool(p.subject_suppressors) for p in patterns),
        "abstain_by": sum(bool(p.abstain_by) for p in patterns),
        "jurisdiction_map": sum(bool(p.jurisdiction_map) for p in patterns),
        "consumes_cues": sum(bool(p.consumes_cues) for p in patterns),
    }
    assert census == {
        "suppressed_by_unit": 10,
        "suppressed_by_sentence": 1,
        "subject_suppressors": 16,
        "abstain_by": 7,
        "jurisdiction_map": 2,
        "consumes_cues": 1,
    }
    # The doc-level idioms are stamped identically onto every pattern (prototype's
    # split-brain note: they ride on the pattern, not a module global).
    assert all(len(p.cue_idioms) == 3 for p in patterns)


def test_an_override_wins_and_is_labelled(tmp_path: Path) -> None:
    _write(tmp_path, MINIMAL)
    catalog = load_rules(tmp_path)
    assert catalog.source == "override"
    assert [f.id for f in catalog.families] == ["degree"]


def test_optional_pattern_members_are_compiled_and_carried(tmp_path: Path) -> None:
    """Every suppressor list becomes a tuple of compiled patterns, consumes_cues a tuple
    of strings, cue_idioms a tuple of compiled idioms, and the absent kinds stay empty."""
    _write(tmp_path, MINIMAL_RICH)
    pattern = load_rules(tmp_path).family("degree").patterns[0]
    for carried in (
        pattern.subject_suppressors,
        pattern.suppressed_by_unit,
        pattern.suppressed_by_sentence,
        pattern.abstain_by,
        pattern.cue_idioms,
    ):
        assert len(carried) == 1
        assert isinstance(carried[0], re.Pattern)
    assert pattern.consumes_cues == ("no",)
    assert pattern.suppressed_by == ()
    assert pattern.jurisdiction_map == {}


def test_the_version_is_stable_and_content_addressed(tmp_path: Path) -> None:
    first = load_rules(tmp_path / "a").version
    assert first == load_rules(tmp_path / "b").version
    assert len(first) == 64


def test_reformatting_does_not_change_the_version(tmp_path: Path) -> None:
    """The version hashes the CANONICAL parsed document, so indentation and key order
    never matter, exactly as extract/taxonomy.py:95-103 does it."""
    _write(tmp_path / "one", MINIMAL)
    reordered = MINIMAL.replace(
        'version: 1\nnegation_cues: ["not"]', 'negation_cues: ["not"]\nversion: 1'
    )
    _write(tmp_path / "two", reordered)
    assert load_rules(tmp_path / "one").version == load_rules(tmp_path / "two").version


def test_content_changes_the_version(tmp_path: Path) -> None:
    _write(tmp_path / "one", MINIMAL)
    _write(tmp_path / "two", MINIMAL.replace('pattern: "bachelor"', 'pattern: "masters"'))
    assert load_rules(tmp_path / "one").version != load_rules(tmp_path / "two").version


def test_rule_ids_are_composite(tmp_path: Path) -> None:
    """rule_id carries family and pattern, because eligibility_requirements has NO
    family column and requirement identity must survive without one (D-P2-17)."""
    catalog = load_rules(tmp_path)
    pattern = catalog.family("degree").patterns[0]
    assert pattern.rule_id == f"degree:{pattern.id}"
    assert catalog.pattern_for(pattern.rule_id) is pattern
    assert catalog.pattern_for("degree:no_such_pattern") is None
    assert catalog.pattern_for("malformed") is None


def test_the_policy_map_is_materialised_from_catalog_defaults(tmp_path: Path) -> None:
    """An empty stored policy and a fully written one must not be two fingerprints for
    identical behaviour (D-P2-2, spec §4.1)."""
    catalog = load_rules(tmp_path)
    materialised = catalog.materialised_policy(Policy())
    assert set(materialised) == {f.id for f in catalog.families}
    assert set(materialised.values()) == {"preference"}
    overridden = catalog.materialised_policy(Policy(families={"degree": "blocker"}))
    assert overridden["degree"] == "blocker"
    assert overridden["clearance"] == "preference"
    # a stored family the catalog no longer declares is ignored, never crashed on
    stale = catalog.materialised_policy(Policy(families={"gone": "blocker"}))
    assert "gone" not in stale


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("::: not yaml :::", "invalid YAML"),
        ("version: 1\n", "'families' must be a non-empty list"),
        ('version: 1\nnegation_cues: ["not"]\nfamilies:\n  - just a string\n',
         "must be mappings"),
        (MINIMAL + MINIMAL.split("families:")[1], "duplicate family id"),
        (MINIMAL.replace("    fact: highest_degree\n", ""), "missing 'fact'"),
        (MINIMAL.replace("    answer_type: choice\n", ""), "missing 'answer_type'"),
        (MINIMAL.replace("        choices: [none, bachelor]\n", ""), "declares no 'choices'"),
        (MINIMAL.replace("implies: degree_required", "implies: not_in_vocabulary"),
         "outside the family's declared vocabulary"),
        (MINIMAL.replace("exclusive_groups: []", "exclusive_groups: oops"),
         "'exclusive_groups' must be a list"),
        (MINIMAL.replace("exclusive_groups: []", "exclusive_groups: [[degree_required]]"),
         "fewer than 2 members"),
        (MINIMAL.replace("exclusive_groups: []",
                         "exclusive_groups: [[degree_required, nope]]"),
         "outside the family's declared vocabulary"),
        (MINIMAL.replace("scope: sentence", "scope: paragraph"), "unknown scope"),
        (MINIMAL.replace('pattern: "bachelor"', 'pattern: "([unclosed"'), "does not compile"),
        (MINIMAL.replace("ranks: {none: 0, bachelor: 3}", "ranks: {none: 0, doctorate: 5}"),
         "ranks a value that is not a choice"),
        (MINIMAL.replace("      - id: bachelor_required", "      - id: dup") +
         "      - id: dup\n        requiredness: required\n        implies: degree_required\n"
         "        scope: sentence\n        requirement_text: x\n        pattern: y\n",
         "duplicate pattern id"),
        (MINIMAL[:MINIMAL.index("    patterns:")] + "    patterns: []\n",
         "declares no patterns"),
        (MINIMAL.replace("requiredness: required", "requiredness: essential"),
         "unknown requiredness"),
        (MINIMAL.replace("default_policy: preference", "default_policy: sometimes"),
         "unknown default_policy"),
        # A bare string is iterable, so `subject_suppressors: "our team"` would compile a
        # regex per CHARACTER, one of them " ", which matches every unit. Prototype finding
        # 31: reject it at load rather than let the family stop producing rows in silence.
        (MINIMAL.replace('        pattern: "bachelor"',
                         '        subject_suppressors: "our team"\n        pattern: "bachelor"'),
         "must be a list"),
        (MINIMAL.replace('        pattern: "bachelor"',
                         '        abstain_by: ["([bad"]\n        pattern: "bachelor"'),
         "does not compile"),
        # Prototype finding 59: a cue this pattern claims to consume must be a DECLARED
        # negation cue, or the cue-inside guard would never have dropped anything for it.
        (MINIMAL.replace('        pattern: "bachelor"',
                         '        consumes_cues: ["never"]\n        pattern: "bachelor"'),
         "not a declared negation cue"),
        # Unquoted `no` is a YAML 1.1 boolean, the exact shape of finding 59: it arrives as
        # False, str(False) is "False", and the guard silently consumes nothing.
        (MINIMAL.replace('        pattern: "bachelor"',
                         '        consumes_cues: [no]\n        pattern: "bachelor"'),
         "QUOTE it"),
        (MINIMAL.replace('negation_cues: ["not"]',
                         'negation_cues: ["not"]\nnegation_cue_idioms: "boom"'),
         "must be a list"),
    ],
)
def test_each_malformed_shape_has_its_own_raise_site(
    tmp_path: Path, mutation: str, message: str
) -> None:
    _write(tmp_path, mutation)
    with pytest.raises(CatalogError) as exc:
        load_rules(tmp_path)
    assert message in str(exc.value)
    assert "rules.yaml" in str(exc.value)  # the message names the offending document


def test_a_structured_family_needs_at_least_two_fields(tmp_path: Path) -> None:
    _write(tmp_path, MINIMAL.replace("answer_type: choice", "answer_type: structured"))
    with pytest.raises(CatalogError, match="structured"):
        load_rules(tmp_path)


def test_a_scalar_family_field_type_must_match_the_answer_type(tmp_path: Path) -> None:
    _write(tmp_path, MINIMAL.replace("        type: choice", "        type: int"))
    with pytest.raises(CatalogError, match="answer_type"):
        load_rules(tmp_path)


def test_an_exclusive_implies_value_may_not_appear_in_two_groups(tmp_path: Path) -> None:
    """Overlap would make the conflict rewrite order-dependent, and order dependence is
    how a shape rule becomes a semantic rule (spec §4.4 stage 1)."""
    body = MINIMAL.replace(
        "implies_vocabulary: [degree_required]",
        "implies_vocabulary: [degree_required, a, b]",
    ).replace(
        "exclusive_groups: []",
        "exclusive_groups: [[degree_required, a], [degree_required, b]]",
    )
    _write(tmp_path, body)
    with pytest.raises(CatalogError, match="more than one group"):
        load_rules(tmp_path)


def test_the_bundled_text_is_readable_without_a_config_dir() -> None:
    assert "families:" in bundled_rules_text()
    assert CATALOG_REVISION == 1
