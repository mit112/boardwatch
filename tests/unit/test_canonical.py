"""P4 item 2: `build_canonical_vocab` replaces the duplicated 3-line expression that used
to live independently in `rewrite/lane.py::run_tier_b` and
`rewrite/agent_lane.py::apply_agent_rewrites`. This pins parity against that former
expression so a future drift in the helper is caught.
"""

from __future__ import annotations

from boardwatch.extract.taxonomy import Taxonomy, load_taxonomy
from boardwatch.tailor.canonical import build_canonical_vocab
from boardwatch.tailor.equivalences import EquivalencePair, EquivalenceTable


def _old_expression(taxonomy: Taxonomy, table: EquivalenceTable) -> frozenset[str]:
    """The exact expression both call sites used before P4 item 2 (lane.py:317-323,
    agent_lane.py:147-152), reconstructed here rather than imported, so this test fails if
    the helper's derivation ever drifts from what it replaced."""
    return frozenset(p.name.lower() for p in taxonomy.patterns) | frozenset(
        img.lower() for img in table.images()
    )


def test_terms_match_the_former_duplicated_expression(tmp_path) -> None:
    # ZzzCustomImage deliberately does NOT collide with any taxonomy.yaml pattern name, so
    # this pins the table.images() half of the union, not just the taxonomy half (a real
    # equivalences.yaml image like "JavaScript" already exists as a taxonomy pattern name
    # and would pass even if the union were silently dropped).
    taxonomy = load_taxonomy(tmp_path)
    table = EquivalenceTable(
        pairs=(EquivalencePair(from_phrase="ZZZ", to_phrase="ZzzCustomImage"),), version="t1"
    )
    vocab = build_canonical_vocab(taxonomy, table)
    assert vocab.terms == _old_expression(taxonomy, table)
    assert "zzzcustomimage" in vocab.terms


def test_field_defaults_to_swe() -> None:
    taxonomy = load_taxonomy_stub()
    table = EquivalenceTable(pairs=(), version="t1")
    vocab = build_canonical_vocab(taxonomy, table)
    assert vocab.field == "swe"


def test_version_is_nonempty_and_reflects_either_source() -> None:
    taxonomy = load_taxonomy_stub()
    table_a = EquivalenceTable(pairs=(), version="version-a")
    table_b = EquivalenceTable(pairs=(), version="version-b")

    version_a = build_canonical_vocab(taxonomy, table_a).version
    version_b = build_canonical_vocab(taxonomy, table_b).version

    assert version_a
    assert version_a != version_b

    taxonomy_2 = load_taxonomy_stub(version="taxonomy-2")
    version_c = build_canonical_vocab(taxonomy_2, table_a).version
    assert version_c != version_a


def load_taxonomy_stub(version: str = "taxonomy-1") -> Taxonomy:
    return Taxonomy(patterns=(), version=version, source="bundled")
