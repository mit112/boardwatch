"""T369: the report that proposes leveling bindings from the judge's seniority answers.

Companies are planted and fake. Expected values come from each fixture's construction (how many
postings were planted and read, with which answer), never from the report's own grouping.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import Engine
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.settings import Settings
from boardwatch.rank.leveling import load_leveling
from boardwatch.reports.leveling_bindings import (
    DEFAULT_MIN_N,
    LevelingReportError,
    build_report,
    current_readings,
    leveling_report,
    wilson_lower,
)
from boardwatch.store.db import get_readonly_engine
from tests.pipeline.test_gate_stage import env, fake_claude
from tests.pipeline.test_value_shadow import _post, _read, _stack

__all__ = ["env", "fake_claude"]


def _plant(
    engine: Engine, settings: Settings, company: str, token: str, answer: str, count: int,
    *, role: str = "Software Engineer", slug: str | None = None, **read: str,
) -> list[int]:
    ids = []
    for n in range(count):
        pid = _post(
            engine, title=f"{role} {token} - Team {chr(65 + n)}", company=company,
            slug=slug or company.lower(),
        )
        _read(engine, settings, pid, good=answer == "yes", seniority=answer, **read)
        ids.append(pid)
    return ids


def _report(engine: Engine, settings: Settings, min_n: int = DEFAULT_MIN_N) -> str:
    return leveling_report(engine, settings, min_n)


def _bindings(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("- {provider")]


def test_the_planted_groups_come_out_with_their_counts_and_a_paste_ready_block(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Fakeco", "5", "no", 8)
    _plant(engine, settings, "Fakeco", "1", "yes", 7)
    text = _report(engine, settings)

    assert "Fakeco" in text
    assert "8/8" in text and "7/7" in text
    # ic_1_to_7 and ic_1_to_6 both agree with 5 -> above band and 1 -> in band: the first
    # in catalog order is proposed and the other is named.
    assert _bindings(text) == [
        '- {provider: "greenhouse", slug: "fakeco", scheme: "ic_1_to_7"}  # Fakeco; '
        "also consistent: ic_1_to_6",
    ]


def test_one_scheme_per_company_consistent_with_every_token(env: Path) -> None:
    engine, settings = _stack(env)
    # "3" above band rules out ic_1_to_7 (3 is entry there); "1" in band keeps ic_1_to_6.
    _plant(engine, settings, "Sixco", "3", "no", 7)
    _plant(engine, settings, "Sixco", "1", "yes", 7)
    text = _report(engine, settings)
    assert [b.split("scheme: ")[1].split("}")[0] for b in _bindings(text)] == ['"ic_1_to_6"']
    assert "also consistent" not in text


def test_a_group_no_scheme_agrees_with_is_unmatched_and_never_forced(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Oddco", "2", "no", 13)  # 2 is entry in both shipped schemes
    text = _report(engine, settings)
    assert "UNMATCHED" in text and "Oddco 2" in text
    assert _bindings(text) == []


def test_one_unmatched_token_keeps_the_whole_board_out_of_the_block(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Mixco", "5", "no", 7)
    _plant(engine, settings, "Mixco", "2", "no", 7)
    assert _bindings(_report(engine, settings)) == []


def test_a_mixed_group_is_never_proposed(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Splitco", "5", "no", 5)
    _plant(engine, settings, "Splitco", "5", "yes", 4)
    text = _report(engine, settings)
    assert "5/9" in text and _bindings(text) == []


def test_a_group_below_the_minimum_n_is_not_listed(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Smallco", "5", "no", 6)
    assert "Smallco" not in _report(engine, settings)
    assert "Smallco" in _report(engine, settings, min_n=6)


def test_only_the_current_judge_identity_counts(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Idco", "5", "no", 7)
    _plant(engine, settings, "Idco", "5", "yes", 9, model="haiku")  # another model
    _plant(engine, settings, "Idco", "5", "yes", 9, effort="high")  # another level
    _plant(engine, settings, "Idco", "5", "yes", 9, band="mid")  # another band
    text = _report(engine, settings)
    assert "7/7" in text and "Idco" in text
    readings, band = current_readings(engine, settings)
    assert len(readings) == 7 and band == "entry"


def test_the_newest_reading_of_a_posting_is_the_one_that_counts(env: Path) -> None:
    engine, settings = _stack(env)
    ids = _plant(engine, settings, "Redoco", "5", "yes", 7)  # the old answer
    for pid in ids:
        _read(engine, settings, pid, good=False, seniority="no")  # re-judged since
    text = _report(engine, settings)
    assert "7/7" in text and "above" in text


def test_a_title_a_seniority_word_decides_is_not_evidence_for_its_number(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Wordco", "3", "no", 7, role="Senior Software Engineer")
    assert "Wordco" not in _report(engine, settings)


def test_a_roman_one_is_listed_and_read_without_a_binding(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Romanco", "I", "yes", 7)
    text = _report(engine, settings)
    assert "Romanco" in text and "no binding needed" in text
    assert _bindings(text) == []


def test_a_target_band_of_any_has_no_seniority_answers_to_read(env: Path) -> None:
    engine, settings = _stack(env)
    from boardwatch.store import tables

    with engine.begin() as conn:
        conn.execute(tables.profile.update().values(target_seniority_band="any"))
    try:
        _report(engine, settings)
    except LevelingReportError as exc:
        assert "any" in str(exc)
    else:
        raise AssertionError("expected LevelingReportError")


def test_wilson_lower_bound_matches_the_published_values() -> None:
    # Wilson 95% interval, hand-computed: 26/26 -> 26 / (26 + z^2) = 0.8713, 7/7 -> 0.6457.
    assert round(wilson_lower(26, 26), 3) == 0.871
    assert round(wilson_lower(7, 7), 3) == 0.646
    assert round(wilson_lower(12, 13), 3) == 0.667
    assert wilson_lower(0, 0) == 0.0


def test_build_report_is_pure_over_its_readings(tmp_path: Path) -> None:
    from boardwatch.reports.leveling_bindings import Reading

    catalog = load_leveling(tmp_path)
    readings = [Reading("greenhouse", "x", "Xco", "Software Engineer 6", "no")] * 7
    report = build_report(readings, catalog, "software", "entry")
    assert [p.scheme for p in report.proposals] == ["ic_1_to_7"]
    assert build_report(readings, catalog, "software", "entry", min_n=8).groups == ()


def test_a_token_below_min_n_is_not_listed_but_still_has_to_agree(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Lowco", "5", "no", 7)
    _plant(engine, settings, "Lowco", "2", "no", 1)  # 2 is entry in both shipped schemes
    text = _report(engine, settings)
    assert _bindings(text) == []
    assert "Lowco 5" in text  # the 5 group is listed, as unmatched, because of the 2
    _plant(engine, settings, "Okco", "5", "no", 7)
    _plant(engine, settings, "Okco", "2", "yes", 1)  # a lone token that agrees does not veto
    assert len(_bindings(_report(engine, settings))) == 1


def test_a_split_token_below_min_n_vetoes_the_board(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Splitlow", "5", "no", 7)
    _plant(engine, settings, "Splitlow", "2", "yes", 3)  # agrees with both schemes (2 is entry)
    _plant(engine, settings, "Splitlow", "2", "no", 2)  # contradicts both: 2 is entry in each
    assert _bindings(_report(engine, settings)) == []


def test_boards_sharing_a_company_name_are_judged_apart(env: Path) -> None:
    engine, settings = _stack(env)
    _plant(engine, settings, "Twin", "5", "no", 7, slug="twin-a")
    _plant(engine, settings, "Twin", "5", "yes", 7, slug="twin-b")  # the opposite reading
    text = _report(engine, settings)
    bound = _bindings(text)
    assert len(bound) == 1 and 'slug: "twin-a"' in bound[0]
    assert "Twin 5 (greenhouse/twin-b)" in text  # UNMATCHED, on its own readings


def test_an_in_band_answer_on_a_high_rung_rules_a_scheme_out(env: Path) -> None:
    engine, settings = _stack(env)
    # 5 in band: no rung 5 is at or below entry, so neither scheme agrees with it.
    _plant(engine, settings, "Highco", "5", "yes", 7)
    _plant(engine, settings, "Highco", "3", "no", 7)  # on its own this fits ic_1_to_6
    assert _bindings(_report(engine, settings)) == []


def test_an_answer_to_a_superseded_version_is_not_evidence_for_the_revised_title(
    env: Path,
) -> None:
    from boardwatch.core.clock import utcnow
    from boardwatch.store import tables

    engine, settings = _stack(env)
    ids = _plant(engine, settings, "Revco", "5", "no", 7)
    assert len(_bindings(_report(engine, settings))) == 1  # counted while its version is current
    with engine.begin() as conn:
        for pid in ids:
            conn.execute(tables.postings.update().where(tables.postings.c.id == pid).values(
                title="Software Engineer 3 - Revised"
            ))
            conn.execute(tables.posting_versions.insert().values(
                posting_id=pid, content_hash=f"v2-{pid}", body_text="A junior role.",
                captured_at=utcnow(), capture_reason="revised",
            ))
    text = _report(engine, settings)
    assert "Revco" not in text and _bindings(text) == []


def test_the_printed_block_loads_through_the_bindings_loader(env: Path, tmp_path: Path) -> None:
    from boardwatch.rank.leveling import load_bindings

    engine, settings = _stack(env)
    _plant(engine, settings, "Boolco", "5", "no", 7, slug="on")  # a bare `on` loads as True
    _plant(engine, settings, "Nullco", "5", "no", 7, slug="null")
    text = _report(engine, settings)
    (tmp_path / "leveling-bindings.yaml").write_text(
        text[text.index("bindings:"):], encoding="utf-8"
    )
    assert load_bindings(tmp_path) == {
        ("greenhouse", "on"): "ic_1_to_7",
        ("greenhouse", "null"): "ic_1_to_7",
    }


def _state(data_dir: Path) -> tuple[str, list[str], int, int]:
    """The database file's bytes and mtime, the files beside it other than SQLite's own -shm/-wal
    sidecars (which a read of a WAL store creates, empty), and the bytes in the -wal."""
    db = data_dir / "boardwatch.db"
    wal = data_dir / "boardwatch.db-wal"
    return (
        hashlib.sha256(db.read_bytes()).hexdigest(),
        sorted(p.name for p in data_dir.iterdir() if not p.name.endswith(("-shm", "-wal"))),
        db.stat().st_mtime_ns,
        wal.stat().st_size if wal.exists() else 0,
    )


def test_the_command_writes_nothing_and_does_not_migrate(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from boardwatch.cli import eligibility_cmd

    opened: list[str] = []

    def spy(data_dir: Path, busy_timeout_ms: int = 5000) -> Engine:
        engine = get_readonly_engine(data_dir, busy_timeout_ms=busy_timeout_ms)
        opened.append(str(engine.url))
        return engine

    monkeypatch.setattr(eligibility_cmd, "get_readonly_engine", spy)
    engine, settings = _stack(env)
    _plant(engine, settings, "Fakeco", "5", "no", 7)
    with engine.connect() as conn:  # fold the WAL in, so only the command can change the file
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    engine.dispose()
    before = _state(env)

    first = CliRunner().invoke(app, ["--data-dir", str(env), "eligibility", "leveling"])
    second = CliRunner().invoke(app, ["--data-dir", str(env), "eligibility", "leveling"])

    assert first.exit_code == 0, first.output
    assert "Fakeco" in first.output and "bindings:" in first.output
    assert second.output == first.output
    assert len(opened) == 2 and all("mode=ro" in url for url in opened)
    assert _state(env) == before


def test_a_missing_store_is_reported_and_not_created(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path / "nope"), "eligibility", "leveling"])
    assert result.exit_code == 1
    assert not (tmp_path / "nope").exists()
