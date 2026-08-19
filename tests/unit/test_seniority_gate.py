from pathlib import Path

import pytest

from boardwatch.rank.leveling import load_leveling
from boardwatch.rank.seniority_gate import seniority_verdict


@pytest.fixture
def cat(tmp_path: Path):
    return load_leveling(tmp_path)


@pytest.fixture
def tier(cat):
    return cat.fields["software"]


def V(title, cat, tier, *, scheme=None, target="entry"):
    return seniority_verdict(title, scheme, target, tier, cat)


class TestWordBoundaries:
    @pytest.mark.parametrize("title", [
        "Software Engineer - Cloud SRE",
        "Software Development Engineer, SRE (US Federal)",
        "Software Engineer - Figma Weave (Tel Aviv, Israel)",
    ])
    def test_sr_does_not_match_inside_sre_isr_or_israel(self, title, cat, tier):
        assert V(title, cat, tier)[0] == "in_band"

    def test_leader_is_senior(self, cat, tier):
        verdict, reason = V("Software Engineering Technical Leader", cat, tier)
        assert verdict == "above_band"
        assert "leader" in reason.lower()

    def test_fellow_is_not_a_seniority_word(self, cat, tier):
        # Measured false drop: fellowships are early-career (spec 3.4).
        assert V("SWE Fellow - Human Frontier Collective", cat, tier)[0] == "in_band"

    def test_distinguished_and_vice_president_drop(self, cat, tier):
        assert V("Distinguished Engineer", cat, tier)[0] == "above_band"
        assert V("Full Stack Engineer, Vice President", cat, tier)[0] == "above_band"


class TestRoman:
    def test_engineer_i_is_entry_and_stays(self, cat, tier):
        # Run 61's Affirm lead must be retained.
        assert V("Software Engineer I, Backend (Collections)", cat, tier)[0] == "in_band"

    def test_ii_is_mid_and_drops_at_entry(self, cat, tier):
        assert V("Backend Engineer II", cat, tier)[0] == "above_band"

    def test_ii_stays_when_the_target_is_mid(self, cat, tier):
        assert V("Backend Engineer II", cat, tier, target="mid")[0] == "in_band"


class TestSchemes:
    def test_level_token_without_a_binding_abstains(self, cat, tier):
        verdict, reason = V("Software Engineer, Specs, Level 5", cat, tier)
        assert verdict == "uncertain"
        assert "no scheme" in reason.lower()
        assert "Level 5" in reason

    def test_level_token_with_a_binding_resolves(self, cat, tier):
        scheme = cat.schemes["ic_1_to_7"]
        assert V("Software Engineer, Specs, Level 5", cat, tier, scheme=scheme)[0] == "above_band"
        assert V("Software Engineer, Level 3", cat, tier, scheme=scheme)[0] == "in_band"

    def test_level_outside_the_scheme_range_abstains_with_its_own_reason(self, cat, tier):
        scheme = cat.schemes["ic_1_to_7"]
        verdict, reason = V("Software Architect, Level 9", cat, tier, scheme=scheme)
        assert verdict == "uncertain"
        assert "outside" in reason.lower()

    @pytest.mark.parametrize("title", [
        "Software Development Engineer - Routing Platforms & L2 - Routing",
        "L2 Support Engineer (Automation Focused)",
        "Machine Learning Engineer (T25)",
    ])
    def test_ambiguous_bare_letter_tokens_always_abstain(self, title, cat, tier):
        # Even WITH a scheme bound: L2 is OSI layer 2 here, not a rung.
        assert V(title, cat, tier, scheme=cat.schemes["ic_1_to_7"])[0] == "uncertain"


class TestFailDirection:
    def test_no_token_is_in_band(self, cat, tier):
        assert V("Software Engineer, Content Platform", cat, tier)[0] == "in_band"

    def test_target_any_is_always_in_band_and_says_so(self, cat, tier):
        verdict, reason = V("Distinguished Engineer", cat, tier, target="any")
        assert verdict == "in_band"
        assert "inert" in reason.lower()

    def test_every_non_pass_verdict_names_the_text_that_decided_it(self, cat, tier):
        for title in ("Senior Software Engineer", "Staff Software Engineer", "Backend Engineer II"):
            verdict, reason = V(title, cat, tier)
            assert verdict == "above_band"
            assert reason.strip()


class TestTheCatalogActuallyDrivesBehaviour:
    """The `grammars:` section must not be decoration.

    Before this was wired, the module hardcoded its ambiguous-token list and the catalog's
    declaration was read by nobody: editing the YAML changed nothing. These tests fail if
    that regresses.
    """

    def test_dropping_a_grammar_from_the_catalog_changes_the_verdict(self, tmp_path):
        from boardwatch.rank.leveling import load_leveling

        (tmp_path / "leveling.yaml").write_text("""
leveling_version: 1
grammars: {level_n: {kind: self_describing}}
schemes: {s: {grammar: level_n, levels: {"5": senior}}}
fields: {software: {words: {}, roman: {}}}
""", encoding="utf-8")
        cat = load_leveling(tmp_path)
        # `l_prefix` is no longer declared, so L2 is not recognised as anything at all and the
        # title falls through to the entry default instead of abstaining.
        verdict, _ = seniority_verdict(
            "L2 Support Engineer", None, "entry", cat.fields["software"], cat
        )
        assert verdict == "in_band"

    def test_a_grammar_the_module_cannot_match_is_not_declarable(self, tmp_path):
        from boardwatch.rank.leveling import LevelingError, load_leveling

        (tmp_path / "leveling.yaml").write_text("""
leveling_version: 1
grammars: {klingon_prefix: {kind: ambiguous}}
schemes: {}
fields: {software: {words: {}, roman: {}}}
""", encoding="utf-8")
        with pytest.raises(LevelingError, match="klingon_prefix"):
            load_leveling(tmp_path)
