"""The program logs' spanning indexes must point at the lines they claim (D-108)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.program_index.__main__ import DOCS, main
from tools.program_index.index import SPECS, reindex

DECISIONS_SPEC, METRICS_SPEC = SPECS

# D-002's heading really sits on line 10; the index row claims 99.
DECISIONS_LIVE = """# DECISIONS

| # | File | Line | Decision |
|---|---|---|---|
| D-001 | DECISIONS-ARCHIVE.md | 3 | An archived one |
| D-002 | DECISIONS.md | 99 | A live one |

---

## D-002 — A live one

Body.
"""

DECISIONS_ARCHIVE = """# ARCHIVE

## D-001 — An archived one
"""

# `Run log` really sits on line 12; the index row claims 1. The index's own heading is
# above the index, so it owes no row of its own.
METRICS_LIVE = """# METRICS

## Index — spans both files

| File | Line | Section |
|---|---|---|
| METRICS-ARCHIVE.md | 3 | Old thing |
| METRICS.md | 1 | Run log |

---

## Run log

rows
"""

METRICS_ARCHIVE = """# ARCHIVE

## Old thing
"""


def _seed(docs: Path) -> None:
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "DECISIONS.md").write_text(DECISIONS_LIVE)
    (docs / "DECISIONS-ARCHIVE.md").write_text(DECISIONS_ARCHIVE)
    (docs / "METRICS.md").write_text(METRICS_LIVE)
    (docs / "METRICS-ARCHIVE.md").write_text(METRICS_ARCHIVE)


def test_a_stale_row_is_reported_against_the_heading_it_names() -> None:
    result = reindex(DECISIONS_SPEC, DECISIONS_LIVE, DECISIONS_ARCHIVE)

    assert [(d.key, d.old, d.new) for d in result.drifts] == [("D-002", 99, 10)]
    assert result.errors == ()
    assert "| D-002 | DECISIONS.md | 10 | A live one |" in result.text
    # The row that was already right is left exactly as it was.
    assert "| D-001 | DECISIONS-ARCHIVE.md | 3 | An archived one |" in result.text


def test_the_index_heading_itself_owes_no_row_but_a_section_below_it_does() -> None:
    result = reindex(METRICS_SPEC, METRICS_LIVE, METRICS_ARCHIVE)

    assert [(d.key, d.old, d.new) for d in result.drifts] == [("Run log", 1, 12)]
    assert result.errors == ()


def test_correcting_an_index_converges_in_one_pass() -> None:
    once = reindex(DECISIONS_SPEC, DECISIONS_LIVE, DECISIONS_ARCHIVE)
    twice = reindex(DECISIONS_SPEC, once.text, DECISIONS_ARCHIVE)

    assert twice.drifts == ()
    assert twice.text == once.text


def test_a_heading_with_no_index_row_is_reported_not_repaired() -> None:
    live = DECISIONS_LIVE + "\n## D-003 — Never indexed\n"

    result = reindex(DECISIONS_SPEC, live, DECISIONS_ARCHIVE)

    assert any("D-003" in error and "no index row" in error for error in result.errors)
    assert "D-003" not in result.text.split("## D-002")[0]


def test_a_row_naming_a_heading_that_does_not_exist_is_reported() -> None:
    live = DECISIONS_LIVE.replace(
        "| D-002 | DECISIONS.md | 99 | A live one |",
        "| D-002 | DECISIONS.md | 99 | A live one |\n| D-009 | DECISIONS.md | 5 | Ghost |",
    )

    result = reindex(DECISIONS_SPEC, live, DECISIONS_ARCHIVE)

    assert any("D-009" in error and "no heading" in error for error in result.errors)


def test_a_repeated_heading_is_never_used_to_rewrite_a_row() -> None:
    """Ambiguity must resolve to nothing, not to whichever copy came first."""
    live = DECISIONS_LIVE + "\n## D-002 — A live one, again\n"

    result = reindex(DECISIONS_SPEC, live, DECISIONS_ARCHIVE)

    assert any("duplicate heading 'D-002'" in error for error in result.errors)
    assert any("has no heading" in error for error in result.errors)
    assert result.drifts == ()
    assert "| D-002 | DECISIONS.md | 99 | A live one |" in result.text


def test_a_row_quoted_inside_a_code_fence_is_prose_not_an_index_row() -> None:
    """These logs illustrate their own format, so a fence-blind scan would edit the example."""
    live = DECISIONS_LIVE + (
        "\n## D-003 — An entry that shows the format\n\n"
        "```\n| D-042 | DECISIONS-ARCHIVE.md | 999 | An example row |\n```\n"
    )

    result = reindex(DECISIONS_SPEC, live, DECISIONS_ARCHIVE)

    assert "| D-042 | DECISIONS-ARCHIVE.md | 999 | An example row |" in result.text
    assert all("D-042" not in error for error in result.errors)
    assert [d.key for d in result.drifts] == ["D-002"]


def test_a_heading_quoted_inside_a_code_fence_is_not_a_heading() -> None:
    """`METRICS.md` tells the reader to grep for '^## '; quoting that output must be safe."""
    live = METRICS_LIVE + "\n```\n## Run log\n```\n"

    result = reindex(METRICS_SPEC, live, METRICS_ARCHIVE)

    assert result.errors == ()
    assert [(d.key, d.new) for d in result.drifts] == [("Run log", 12)]


def test_a_stray_row_below_the_index_does_not_disable_the_missing_row_check() -> None:
    """The index is the first unbroken run of rows; anything later is prose."""
    live = DECISIONS_LIVE + "\n## D-003 — Never indexed\n\n| D-042 | DECISIONS.md | 5 | stray |\n"

    result = reindex(DECISIONS_SPEC, live, DECISIONS_ARCHIVE)

    assert any("D-003" in error and "no index row" in error for error in result.errors)
    assert all("D-042" not in error for error in result.errors)


def test_check_mode_fails_on_drift_and_writes_nothing(tmp_path: Path) -> None:
    _seed(tmp_path)

    assert main(["--check", "--docs", str(tmp_path)]) == 1
    assert (tmp_path / "DECISIONS.md").read_text() == DECISIONS_LIVE


def test_the_fixer_repairs_drift_and_then_the_check_passes(tmp_path: Path) -> None:
    _seed(tmp_path)

    assert main(["--docs", str(tmp_path)]) == 0
    assert "| D-002 | DECISIONS.md | 10 |" in (tmp_path / "DECISIONS.md").read_text()
    assert "| METRICS.md | 12 | Run log |" in (tmp_path / "METRICS.md").read_text()
    assert main(["--check", "--docs", str(tmp_path)]) == 0


def test_the_fixer_still_fails_when_something_it_cannot_repair_remains(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "DECISIONS.md").write_text(DECISIONS_LIVE + "\n## D-003 — Never indexed\n")

    assert main(["--docs", str(tmp_path)]) == 1


def test_a_file_with_a_problem_is_never_called_current(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed(tmp_path)
    (tmp_path / "DECISIONS.md").write_text(
        DECISIONS_LIVE.replace("| 99 |", "| 10 |") + "\n## D-003 — Never indexed\n"
    )

    assert main(["--check", "--docs", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "DECISIONS.md: index is current" not in captured.out
    assert "no index row" in captured.err


def test_an_unreadable_docs_directory_is_a_broken_check_not_a_clean_one(tmp_path: Path) -> None:
    assert main(["--check", "--docs", str(tmp_path / "absent")]) == 2


def test_the_real_program_indexes_are_current() -> None:
    """The gate: every index row in the repo points at its actual heading."""
    for spec in SPECS:
        result = reindex(
            spec,
            (DOCS / spec.live).read_text(),
            (DOCS / spec.archive).read_text(),
        )
        assert result.errors == (), f"{spec.live}: {result.errors}"
        assert result.drifts == (), f"{spec.live}: {[d.render() for d in result.drifts]}"
