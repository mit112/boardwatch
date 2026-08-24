"""`python -m tools.decisions` must read the same rows the reindex gate keeps true (D-109).

Finding one decision should cost the matching rows and one range, never the ~28.6k-token index.
The load-bearing property is that a lookup sees *only* the authoritative index block: a fenced
example row or a stray row-shaped line below the index must not surface as a real entry, because
the tool then reports a phantom or extracts against a heading that never existed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.decisions.__main__ import DOCS, _extract, _find, _rows, main
from tools.program_index.index import SPECS

DECISIONS_SPEC, METRICS_SPEC = SPECS

# A real index block, a live heading its row points at, and a *fenced* example row that a
# fence-blind scan would wrongly treat as a fourth entry.
DECISIONS_LIVE = "\n".join(
    [
        "# DECISIONS",  # 1
        "",  # 2
        "| # | File | Line | Decision |",  # 3
        "|---|---|---|---|",  # 4
        "| D-001 | DECISIONS-ARCHIVE.md | 3 | An archived one |",  # 5
        "| D-002 | DECISIONS.md | 10 | A live one about **windows** and CI |",  # 6
        "",  # 7
        "---",  # 8
        "",  # 9
        "## D-002 — A live one about windows and CI",  # 10
        "",  # 11
        "First body line.",  # 12
        "Second body line.",  # 13
        "",  # 14
        "## D-003 — Shows the index format",  # 15
        "",  # 16
        "```",  # 17
        "| D-042 | DECISIONS.md | 999 | An example row inside a fence |",  # 18
        "```",  # 19
        "",  # 20
        "trailing prose",  # 21
    ]
) + "\n"

DECISIONS_ARCHIVE = "\n".join(["# ARCHIVE", "", "## D-001 — An archived one", "", "arch body"]) + "\n"


def _seed(docs: Path) -> None:
    docs.mkdir(parents=True, exist_ok=True)
    # utf-8 for the same reason the tool pins it: the headings carry em-dashes.
    (docs / "DECISIONS.md").write_text(DECISIONS_LIVE, encoding="utf-8")
    (docs / "DECISIONS-ARCHIVE.md").write_text(DECISIONS_ARCHIVE, encoding="utf-8")


def test_rows_are_exactly_the_index_block() -> None:
    rows = _rows(DECISIONS_SPEC, DECISIONS_LIVE)

    assert rows == [
        ("D-001", "DECISIONS-ARCHIVE.md", 3, "An archived one"),
        ("D-002", "DECISIONS.md", 10, "A live one about **windows** and CI"),
    ]


def test_a_fenced_example_row_is_not_a_lookup_entry() -> None:
    """The regression this tool's `_rows` exists to avoid: a quoted example is prose, not a row."""
    keys = [row[0] for row in _rows(DECISIONS_SPEC, DECISIONS_LIVE)]

    assert "D-042" not in keys


def test_find_matches_key_and_title_case_insensitively_and_requires_every_word() -> None:
    rows = _rows(DECISIONS_SPEC, DECISIONS_LIVE)

    assert [r[0] for r in _find(rows, ["windows", "ci"])] == ["D-002"]
    assert [r[0] for r in _find(rows, ["WINDOWS"])] == ["D-002"]
    assert _find(rows, ["windows", "absent"]) == []
    # A bare key is matchable too, since key and title are searched together.
    assert [r[0] for r in _find(rows, ["d-001"])] == ["D-001"]


def test_extract_stops_at_the_next_heading(tmp_path: Path) -> None:
    _seed(tmp_path)

    end, text = _extract(DECISIONS_SPEC, tmp_path, "DECISIONS.md", 10)

    assert end == 14
    assert text == (
        "## D-002 — A live one about windows and CI\n\nFirst body line.\nSecond body line."
    )
    assert "## D-003" not in text


def test_show_prints_the_entry_and_find_prints_a_sed_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed(tmp_path)
    monkeypatch.setattr("tools.decisions.__main__.DOCS", tmp_path)

    assert main(["--show", "D-002"]) == 0
    out = capsys.readouterr().out
    assert "First body line." in out
    assert "# DECISIONS.md:10-14" in out

    assert main(["--find", "windows"]) == 0
    out = capsys.readouterr().out
    assert "D-002" in out
    assert "sed -n '10,14p' docs/program/DECISIONS.md" in out


def test_a_fenced_key_cannot_be_shown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end: the example key inside the fence resolves to no entry, exit 1."""
    _seed(tmp_path)
    monkeypatch.setattr("tools.decisions.__main__.DOCS", tmp_path)

    assert main(["--show", "D-042"]) == 1


def test_a_miss_exits_one_and_an_unreadable_log_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    monkeypatch.setattr("tools.decisions.__main__.DOCS", tmp_path)
    assert main(["--find", "nothingmatchesthisword"]) == 1
    assert main(["--show", "D-404"]) == 1

    monkeypatch.setattr("tools.decisions.__main__.DOCS", tmp_path / "absent")
    assert main(["--find", "anything"]) == 2


def test_the_real_log_is_queryable() -> None:
    """The gate the tool actually serves: an entry in the shipped index resolves against it."""
    assert (DOCS / "DECISIONS.md").exists()
    assert main(["--show", "D-001"]) == 0
