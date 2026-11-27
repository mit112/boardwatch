"""T368: the replay reads planted `slate-cut-<run>.json` files. Every expected value below is a
hand count off the planted rows (written in the comments), never the replay's own sort."""

from __future__ import annotations

import json
from pathlib import Path

from tools.slate_cut_replay import find_files, main, replay


def _row(
    position: int, fit: str | None, *, in_slate: bool, decision: str | None = "eligible"
) -> dict[str, object]:
    return {
        "position": position, "posting_id": 100 + position, "shortlist_rank": position,
        "tier": 1, "decision": decision, "seniority_fit": fit,
        "reading": "cached" if decision else "absent", "in_slate": in_slate, "lane": None,
    }


def _report(
    run_id: int, rows: list[dict[str, object]], *, scan_ran: bool = True
) -> dict[str, object]:
    return {
        "version": 1, "run_id": run_id, "scan_ran": scan_ran, "top_n": 3, "slate_ceiling": 0,
        "slate_size": sum(1 for r in rows if r["in_slate"]), "survivors": rows,
    }


def test_an_above_band_survivor_ranked_above_an_in_band_one_loses_the_slot() -> None:
    # Ranker order: 1 no, 2 no, 3 yes | beyond the cut: 4 unclear, 5 yes, 6 no.
    # Slate size 3. Seniority-first: yes {3, 5}, then unclear {4} -> slate {3, 5, 4}.
    rows = [
        _row(1, "no", in_slate=True), _row(2, "no", in_slate=True), _row(3, "yes", in_slate=True),
        _row(4, "unclear", in_slate=False), _row(5, "yes", in_slate=False),
        _row(6, "no", in_slate=False),
    ]
    result = replay(_report(7, rows))
    assert (result.run_id, result.survivors, result.slate_size, result.in_slate) == (7, 6, 3, 3)
    assert result.eligible_in_band_beyond == 1          # posting 105 only; 104 reads unclear
    assert result.above_band_in_slate == 2     # 101, 102
    assert result.above_band_in_slate_after == 0
    assert result.swapped_in == (104, 105)
    assert result.swapped_out == (101, 102)


def test_the_cut_is_stable_inside_a_group_and_an_absent_reading_is_unclear() -> None:
    # Slate size 2: 1 (unclear) and 2 (absent) hold it; 3 reads yes.
    # Seniority-first: yes {3} first, then the FIRST of the middle group (1, not 2). An absent
    # reading is in the middle group: were it read as `yes`, 2 would keep its slot.
    rows = [_row(1, "unclear", in_slate=True), _row(2, None, in_slate=True),
            _row(3, "yes", in_slate=False)]
    result = replay(_report(8, rows))
    assert result.swapped_in == (103,)
    assert result.swapped_out == (102,)
    assert result.eligible_in_band_beyond == 1
    assert result.above_band_in_slate == 0


def test_a_yes_reading_without_an_eligible_decision_is_not_in_band_and_is_not_promoted() -> None:
    # Slate size 2: 1 (eligible, unclear) and 2 (eligible, no) hold it. Beyond the cut:
    #   3 decision absent + yes   (an effort switch left the old effort's seniority answer)
    #   4 uncertain + yes         (the judge cannot clear it but reads the level as in band)
    #   5 ineligible + yes
    #   6 eligible + yes          (the one real in-band opportunity)
    # Hand count: one eligible in-band survivor beyond the cut (106). Seniority-first: 106
    # (group 1), then 101 (group 2, unclear); everything else is group 3 -> slate {101, 106}.
    rows = [
        _row(1, "unclear", in_slate=True), _row(2, "no", in_slate=True),
        _row(3, "yes", in_slate=False, decision=None),
        _row(4, "yes", in_slate=False, decision="uncertain"),
        _row(5, "yes", in_slate=False, decision="ineligible"),
        _row(6, "yes", in_slate=False),
    ]
    result = replay(_report(11, rows))
    assert result.eligible_in_band_beyond == 1
    assert result.swapped_in == (106,)
    assert result.swapped_out == (102,)


def test_an_eligible_survivor_read_above_band_is_not_promoted_over_an_open_one() -> None:
    # Slate size 1 holds 1 (eligible, no). Beyond: 2 (uncertain, yes), 3 (eligible, absent).
    # Group 2 (eligible, open) beats group 3 (the rest): 103 takes the slot, not 102.
    rows = [_row(1, "no", in_slate=True), _row(2, "yes", in_slate=False, decision="uncertain"),
            _row(3, None, in_slate=False)]
    result = replay(_report(12, rows))
    assert result.swapped_in == (103,) and result.swapped_out == (101,)
    assert result.eligible_in_band_beyond == 0


def test_a_run_whose_slate_already_holds_the_in_band_leads_changes_nothing() -> None:
    rows = [_row(1, "yes", in_slate=True), _row(2, "yes", in_slate=True),
            _row(3, "no", in_slate=False)]
    result = replay(_report(9, rows))
    assert (result.eligible_in_band_beyond, result.above_band_in_slate) == (0, 0)
    assert result.swapped_in == () and result.swapped_out == ()


def test_the_script_reads_a_folder_of_files_and_prints_one_row_per_run(
    tmp_path: Path, capsys: object
) -> None:
    day = tmp_path / "2026-11-27"
    day.mkdir()
    (day / "slate-cut-7.json").write_text(json.dumps(_report(7, [
        _row(1, "no", in_slate=True), _row(2, "yes", in_slate=False)])))
    (day / "slate-cut-9.json.partial").write_text("{not json")  # a half-written file is ignored
    (day / "slate-cut-8.json").write_text(json.dumps(_report(8, [
        _row(1, "no", in_slate=True), _row(2, "yes", in_slate=False)], scan_ran=False)))
    (day / "funnel-7.json").write_text("{}")
    assert find_files([tmp_path]) == [day / "slate-cut-7.json", day / "slate-cut-8.json"]
    assert main([str(tmp_path)]) == 0  # nightlies only: the pass that did not scan is left out
    lines = capsys.readouterr().out.strip().splitlines()  # type: ignore[attr-defined]
    assert len(lines) == 2  # header + the one nightly
    assert lines[0].split()[:3] == ["run", "survivors", "in"]
    assert lines[1].split() == ["7", "2", "1", "1", "1", "0", "1", "1"]
    assert main(["--all-runs", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.strip().splitlines()  # type: ignore[attr-defined]
    assert [line.split()[0] for line in lines[1:]] == ["7", "8"]
    assert main([str(tmp_path / "nothing-here")]) == 1
