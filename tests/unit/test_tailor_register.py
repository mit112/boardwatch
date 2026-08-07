"""Tests for the deterministic register guard (P4 item 3a, 2a/2b): banned-register
blocklist and per-bullet buzzword-density ceiling. Mirrors test_overmatch.py's shape --
pure `(text, catalog) -> reasons` predicates, no JD or Resume fixtures needed.
"""

import pytest

from boardwatch.tailor import register as register_module
from boardwatch.tailor.register import (
    REGISTER_VERSION,
    RegisterError,
    banned_register_reasons,
    buzzword_density_reasons,
    load_register,
)

_BANNED = ("responsible for", "synergy")
_BUZZWORDS = ("innovative", "seamless", "dynamic")


def test_register_version_is_defined():
    assert isinstance(REGISTER_VERSION, str)
    assert REGISTER_VERSION == "p4-register-1"


# -- banned_register_reasons -------------------------------------------------------


def test_clean_bullet_has_no_banned_register_reasons():
    assert banned_register_reasons("Built the launch plan for a growing team", _BANNED) == []


def test_banned_phrase_hit_names_the_phrase():
    reasons = banned_register_reasons("Was responsible for the launch plan", _BANNED)
    assert len(reasons) == 1
    assert "responsible for" in reasons[0]


def test_banned_phrase_match_is_case_insensitive():
    reasons = banned_register_reasons("Drove SYNERGY across teams", _BANNED)
    assert len(reasons) == 1
    assert "synergy" in reasons[0]


def test_banned_phrase_does_not_match_inside_a_longer_word():
    # "synergy" must not fire on a word that merely contains it as a substring.
    assert banned_register_reasons("Used a synergystic approach to planning", _BANNED) == []


def test_multiple_banned_phrases_are_all_named():
    reasons = banned_register_reasons(
        "Was responsible for driving synergy across teams", _BANNED
    )
    assert len(reasons) == 2


def test_empty_banned_phrases_catalog_never_flags():
    assert banned_register_reasons("Was responsible for everything", ()) == []


# -- buzzword_density_reasons -------------------------------------------------------


def test_clean_bullet_is_under_the_ceiling():
    assert buzzword_density_reasons("Built the launch plan for a growing team", _BUZZWORDS, 1) == []


def test_bullet_at_the_ceiling_is_the_clean_boundary():
    # Exactly one buzzword hit at ceiling=1 -- AT the ceiling, not over it, must stay clean.
    assert buzzword_density_reasons("Built an innovative launch plan", _BUZZWORDS, 1) == []


def test_bullet_exceeding_the_ceiling_is_flagged():
    reasons = buzzword_density_reasons(
        "Built an innovative and seamless launch plan", _BUZZWORDS, 1
    )
    assert len(reasons) == 1
    assert "innovative" in reasons[0] and "seamless" in reasons[0]


def test_buzzword_match_is_case_insensitive():
    reasons = buzzword_density_reasons("Built an INNOVATIVE and Seamless plan", _BUZZWORDS, 1)
    assert len(reasons) == 1


def test_repeated_occurrences_of_the_same_buzzword_each_count():
    # Two occurrences of "innovative" alone exceed ceiling=1, even with no second word.
    reasons = buzzword_density_reasons("An innovative, innovative plan", _BUZZWORDS, 1)
    assert len(reasons) == 1


def test_zero_ceiling_flags_a_single_buzzword():
    assert buzzword_density_reasons("Built an innovative plan", _BUZZWORDS, 0) != []


# -- load_register -------------------------------------------------------


def test_load_register_returns_non_empty_catalogs_with_a_version():
    table = load_register()
    assert table.banned_phrases and table.buzzwords
    assert table.buzzword_density_ceiling >= 0
    assert isinstance(table.version, str) and table.version


def test_load_register_is_deterministic():
    assert load_register().version == load_register().version


def test_parse_str_list_rejects_non_string_entries():
    with pytest.raises(RegisterError):
        register_module._parse_str_list({"k": ["ok", 123]}, "k")
