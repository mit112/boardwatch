import re

import pytest

from boardwatch.tailor.equivalences import (
    EquivalenceError,
    EquivalencePair,
    _parse_pairs,
    load_equivalences,
)

# Pin AFTER first green run (paste the computed hex). Freeze test = the trust-root seal.
FROZEN_VERSION = "e0eb98d678e181d6022e265a68381581dc15012bdcfe0eebae337a2db3766627"


def test_table_is_frozen():
    assert load_equivalences().version == FROZEN_VERSION


def test_pairs_are_single_token():
    t = load_equivalences()
    tok = re.compile(r"^\w+$")
    for p in t.as_pairs():
        assert tok.match(p.from_phrase) and tok.match(p.to_phrase)
        assert " " not in p.from_phrase and " " not in p.to_phrase


def test_no_pair_introduces_a_digit_or_negation():
    # Entailment-neutrality guard: a swap must not add/remove a number or a polarity word.
    NEG = {"no", "not", "never", "without"}
    for p in load_equivalences().as_pairs():
        assert any(c.isdigit() for c in p.from_phrase) == any(c.isdigit() for c in p.to_phrase)
        assert (p.from_phrase.lower() in NEG) == (p.to_phrase.lower() in NEG)


def test_curated_allowlist_exact():
    # The reviewed set. Adding a pair must be a conscious edit here AND re-freeze the hash.
    got = {(p.from_phrase, p.to_phrase) for p in load_equivalences().as_pairs()}
    assert got == {
        ("JS", "JavaScript"),
        ("TS", "TypeScript"),
        ("Postgres", "PostgreSQL"),
        ("GCP", "GoogleCloud"),
    }


def test_parse_pairs_rejects_non_word_token():
    with pytest.raises(EquivalenceError):
        _parse_pairs({"pairs": [{"from": "C++", "to": "Cpp"}]})


def test_parse_pairs_rejects_duplicate():
    with pytest.raises(EquivalenceError):
        _parse_pairs(
            {
                "pairs": [
                    {"from": "JS", "to": "JavaScript"},
                    {"from": "JS", "to": "JavaScript"},
                ]
            }
        )


def test_parse_pairs_accepts_well_formed():
    pairs = _parse_pairs({"pairs": [{"from": "JS", "to": "JavaScript"}]})
    assert pairs == (EquivalencePair("JS", "JavaScript"),)
