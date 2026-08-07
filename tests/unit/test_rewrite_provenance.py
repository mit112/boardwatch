"""Tests for Tier-B reword provenance check (P1b, D-033)."""

from boardwatch.tailor.equivalences import EquivalencePair, EquivalenceTable
from boardwatch.tailor.rewrite.provenance import (
    CONNECTIVES,
    PROVENANCE_VERSION,
    ProvenanceResult,
    reword_is_provenanced,
)


def test_provenance_version_is_defined():
    """PROVENANCE_VERSION constant is defined."""
    assert isinstance(PROVENANCE_VERSION, str)
    assert PROVENANCE_VERSION == "p1b-provenance-1"


def test_connectives_are_structural_only():
    """CONNECTIVES contains only claim-free structural words."""
    assert isinstance(CONNECTIVES, frozenset)
    expected = {"the", "a", "an", "of", "to", "for", "and", "or", "with", "in", "on", "at", "from", "by", "as", "that"}
    assert CONNECTIVES == expected


def test_provenance_result_frozen():
    """ProvenanceResult is a frozen dataclass."""
    result = ProvenanceResult(ok=True, offending=())
    assert result.ok is True
    assert result.offending == ()


def _make_table(*pairs):
    """Helper: build a small EquivalenceTable from (from, to) tuples."""
    ep_list = [EquivalencePair(frm, to) for frm, to in pairs]
    return EquivalenceTable(pairs=tuple(ep_list), version="test-1")


def test_fabricated_reword_rejected():
    """A reword with unjustified content tokens is rejected."""
    table = _make_table()
    result = reword_is_provenanced("Built the service", "Engineered the product", table=table)
    assert result.ok is False
    assert "Engineered" in result.offending
    assert "product" in result.offending


def test_connective_insertion_allowed():
    """Inserting connectives (articles, prepositions) is allowed."""
    table = _make_table()
    result = reword_is_provenanced("Built service", "Built the service", table=table)
    assert result.ok is True
    assert result.offending == ()


def test_equivalence_image_allowed():
    """A token matching an approved equivalence image is allowed."""
    table = _make_table(("JS", "JavaScript"))
    result = reword_is_provenanced("Used JS library", "Used JavaScript library", table=table)
    assert result.ok is True
    assert result.offending == ()


def test_punctuation_only_diff_allowed():
    """Differences in punctuation and case only are allowed."""
    table = _make_table()
    result = reword_is_provenanced("Built. The service!", "built the service", table=table)
    assert result.ok is True
    assert result.offending == ()


def test_bare_synonym_rejected():
    """A synonym with no equivalence table entry is rejected."""
    table = _make_table()
    result = reword_is_provenanced("Optimize the system", "Improve the system", table=table)
    assert result.ok is False
    assert "Improve" in result.offending


def test_tense_variant_without_table_pair_rejected():
    """A tense variant with no table pair is rejected."""
    table = _make_table()
    result = reword_is_provenanced("Optimize the system", "Optimized the system", table=table)
    assert result.ok is False
    assert "Optimized" in result.offending


def test_verb_to_agent_noun_regression():
    """Verb→agent-noun transform (via stem) is rejected — a regression test."""
    table = _make_table()
    result = reword_is_provenanced("Architected the service", "Architect of the service", table=table)
    # "Architect" is not in the source (which has "Architected"); no stem match.
    assert result.ok is False
    assert "Architect" in result.offending


def test_modal_regression():
    """Modal auxiliary introduction is rejected — a regression test."""
    table = _make_table()
    result = reword_is_provenanced("Implemented the checkout flow", "Will implement the checkout flow", table=table)
    # "Will" is not a connective and is not in the source.
    assert result.ok is False
    assert "Will" in result.offending


def test_mixed_justified_and_unjustified():
    """Multiple tokens: only the unjustified ones are listed in offending."""
    table = _make_table(("Python", "Rust"))
    result = reword_is_provenanced("Built with Python", "Built with Rust and Kubernetes", table=table)
    assert result.ok is False
    # "Built", "with" are in source/connectives; "Rust" is justified by equivalence table image
    # (wait, no: the table maps TO Rust, not FROM Rust). Let me reconsider.
    # The swap is {python: Rust}, so images are {Rust}.
    # "Built" is in source (case-insensitive), "with" is a connective, "Rust" is in images.
    # But "Kubernetes" is new and unjustified.
    assert "Kubernetes" in result.offending
    assert len(result.offending) == 1


def test_case_insensitive_source_match():
    """Source tokens are matched case-insensitively."""
    table = _make_table()
    result = reword_is_provenanced("Built PYTHON service", "Built python SERVICE", table=table)
    assert result.ok is True
