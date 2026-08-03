"""Hermetic test for the Tier B offline eval harness: corpus + filter-only report.

No network, no live client -- only exercises the deterministic filter, matching the
harness's `--live`-free default mode.
"""

from __future__ import annotations

from pathlib import Path

from boardwatch.extract.taxonomy import load_taxonomy
from tools.tier_b_eval.__main__ import load_corpus, run_filter_only

CORPUS = Path(__file__).parent.parent.parent / "tools" / "tier_b_eval" / "corpus.yaml"


def test_corpus_loads_and_is_labeled() -> None:
    cases = load_corpus(CORPUS)
    assert len(cases) >= 12
    assert {c.label for c in cases} <= {"entailed", "fabricated"}
    families = {
        "invented_skill",
        "inflated_number",
        "scope_creep",
        "seniority_inflation",
        "negation_flip",
        "unsupported_outcome",
        "faithful",
    }
    assert families <= {c.family for c in cases}
    for family in families:
        assert sum(1 for c in cases if c.family == family) >= 2
    assert any(c.held_out for c in cases)


def test_filter_catches_overmatch_families(tmp_path: Path) -> None:
    cases = load_corpus(CORPUS)
    report = run_filter_only(cases, load_taxonomy(tmp_path))
    # The filter alone must reject every invented_skill / inflated_number fabrication.
    for fam in ("invented_skill", "inflated_number"):
        assert report[fam]["false_accept"] == 0
