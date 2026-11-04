"""Sponsor index: build from LCA workbooks, then exact-match lookup.

Expected values come from the fixture rows written below, never from the implementation's own
selection logic. The workbook is built with `zipfile` in the real layout: a shared-strings part,
sparse cells addressed by column letter, day-serial dates, and trailing blank rows.
"""

from __future__ import annotations

import json
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.rank.sponsors import (
    EXCLUSIONS_FILENAME,
    SPONSORS_FILENAME,
    SponsorIndex,
    load_sponsor_index,
    normalize_employer,
)
from boardwatch.rank.sponsors_build import (
    REQUIRED_COLUMNS,
    MissingColumnError,
    SponsorBuildError,
    build_sponsors,
)

# Real column order matters little; these are the required ones plus decoys, so a header read by
# position rather than by name fails.
HEADER = ("CASE_NUMBER", *REQUIRED_COLUMNS, "JOB_TITLE")
TODAY = date(2026, 11, 4)
SERIAL_2026_01_05 = 46027  # 2026-01-05
SERIAL_2026_03_01 = 46082  # 2026-03-01


def _row(
    employer: str,
    *,
    status: str = "Certified",
    visa: str = "H-1B",
    soc: str = "15-1252.00",
    new: str = "1",
    wage: str = "II",
    secondary: str = "No",
    fein: str = "11-1111111",
    naics: str = "541511",
    state: str = "CA",
    decided: int = SERIAL_2026_01_05,
) -> dict[str, str | int]:
    return {
        "CASE_NUMBER": "I-200-0",
        "CASE_STATUS": status,
        "VISA_CLASS": visa,
        "EMPLOYER_NAME": employer,
        "EMPLOYER_FEIN": fein,
        "EMPLOYER_STATE": state,
        "NAICS_CODE": naics,
        "SOC_CODE": soc,
        "NEW_EMPLOYMENT": new,
        "PW_WAGE_LEVEL": wage,
        "SECONDARY_ENTITY": secondary,
        "DECISION_DATE": decided,
        "JOB_TITLE": "Engineer",
    }


def _letters(index: int) -> str:
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _write_xlsx(
    path: Path, rows: list[dict[str, str | int]], *, header: tuple[str, ...] = HEADER
) -> Path:
    strings: list[str] = []

    def shared(text: str) -> int:
        if text not in strings:
            strings.append(text)
        return strings.index(text)

    def cell(col: int, row_no: int, value: str | int) -> str:
        ref = f"{_letters(col)}{row_no}"
        if isinstance(value, int):
            return f'<c r="{ref}"><v>{value}</v></c>'
        if value == "":
            return ""  # blank cells are absent in the real sheet, so the row is sparse
        # NEW_EMPLOYMENT is a plain number in the real sheet, not a shared string.
        if header[col] == "NEW_EMPLOYMENT":
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="s"><v>{shared(value)}</v></c>'

    body = ['<row r="1">' + "".join(cell(i, 1, h) for i, h in enumerate(header)) + "</row>"]
    for n, data in enumerate(rows, start=2):
        cells = "".join(cell(i, n, data[h]) for i, h in enumerate(header) if h in data)
        body.append(f'<row r="{n}">{cells}</row>')
    last = len(rows) + 2
    for n in range(last, last + 3):  # trailing blank rows, styled but valueless
        body.append(f'<row r="{n}"><c r="A{n}" s="1"/></row>')

    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet = f'<worksheet xmlns="{ns}"><sheetData>{"".join(body)}</sheetData></worksheet>'
    sst = "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}">{sst}</sst>')
    return path


def _build(tmp_path: Path, *files: Path) -> dict[str, object]:
    build_sponsors(list(files), tmp_path / "cfg", today=TODAY)
    loaded: dict[str, object] = json.loads((tmp_path / "cfg" / SPONSORS_FILENAME).read_text())
    return loaded


def _employers(doc: dict[str, object]) -> dict[str, dict[str, object]]:
    employers = doc["employers"]
    assert isinstance(employers, dict)
    return employers


# ---- normalize_employer ----------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["Acme, Inc.", "ACME INC", "🔥 Acme", "Acme LLC", "acme  corp."])
def test_variants_of_one_name_normalize_to_the_same_key(raw: str) -> None:
    assert normalize_employer(raw) == "acme"


def test_decoration_is_removed_by_ascii_folding() -> None:
    # The store carries names like "🔥 PayPal"; the DOL file says "PayPal, Inc.".
    assert normalize_employer("🔥 PayPal") == normalize_employer("PayPal, Inc.") == "paypal"
    assert normalize_employer("Nestlé USA") == "nestle usa"


def test_accents_and_apostrophes_do_not_split_a_word(tmp_path: Path) -> None:
    # DOL writes a curly apostrophe; a company page writes a straight one.
    assert normalize_employer("Kohl’s, Inc.") == normalize_employer("Kohl's") == "kohls"
    assert normalize_employer("Modern Décor LLC") == "modern decor"


def test_visa_group_and_visa_stay_different() -> None:
    assert normalize_employer("Visa Group") == "visa group"
    assert normalize_employer("Visa Inc.") == "visa"
    assert normalize_employer("Visa Group") != normalize_employer("Visa")


@pytest.mark.parametrize("suffix", ["usa", "us", "america", "holdings", "group"])
def test_identity_words_are_never_stripped(suffix: str) -> None:
    assert normalize_employer(f"Acme {suffix.title()} Inc") == f"acme {suffix}"


def test_ampersand_becomes_and_and_dba_is_cut() -> None:
    assert normalize_employer("Johnson & Johnson") == "johnson and johnson"
    assert normalize_employer("Acme Inc dba Roadrunner Supply") == "acme"
    assert normalize_employer("Acme LLC d/b/a Roadrunner") == "acme"


def test_suffix_is_dropped_only_from_the_end() -> None:
    assert normalize_employer("Co Acme Holdings Inc") == "co acme holdings"


# ---- build rules -----------------------------------------------------------------------------


def test_rows_outside_h1b_certified_are_dropped(tmp_path: Path) -> None:
    rows = [
        _row("Keeper Inc"),
        _row("Keeper Inc", visa="E-3 Australian"),
        _row("Keeper Inc", visa="H-1B1 Chile"),
        _row("Keeper Inc", status="Denied"),
        _row("Keeper Inc", status="Withdrawn"),
        _row("Keeper Inc", status="Certified - Withdrawn"),
        _row("Onlywithdrawn Inc", status="Certified - Withdrawn"),
    ]
    doc = _build(tmp_path, _write_xlsx(tmp_path / "a.xlsx", rows))
    employers = _employers(doc)
    assert set(employers) == {"keeper"}
    assert employers["keeper"]["certified_rows"] == 1
    assert doc["sources"] == [
        {
            "file": "a.xlsx",
            "rows_read": 7,
            "h1b_rows": 5,
            "status_counts": {
                "Certified": 1,
                "Certified - Withdrawn": 2,
                "Denied": 1,
                "Withdrawn": 1,
            },
            "rows_counted": 1,
        }
    ]


def test_employer_without_a_computing_row_is_excluded(tmp_path: Path) -> None:
    rows = [
        _row("Bridgeworks Inc", soc="17-2051.00"),
        _row("Bridgeworks Inc", soc="13-1111.00"),
        _row("Codeshop Inc", soc="15-1252.00"),
    ]
    employers = _employers(_build(tmp_path, _write_xlsx(tmp_path / "a.xlsx", rows)))
    assert set(employers) == {"codeshop"}


def test_staffing_employer_over_half_secondary_is_excluded_and_half_is_too(tmp_path: Path) -> None:
    rows = (
        [_row("Bodyshop Inc", secondary="Yes")] * 3
        + [_row("Bodyshop Inc")]  # 3 of 4: 75%
        + [_row("Halfway Inc", secondary="Yes")] * 2
        + [_row("Halfway Inc")] * 2  # exactly 50%: the rule is "under 50%"
        + [_row("Mostlydirect Inc", secondary="Yes")]
        + [_row("Mostlydirect Inc")] * 3  # 25%
    )
    employers = _employers(_build(tmp_path, _write_xlsx(tmp_path / "a.xlsx", rows)))
    assert set(employers) == {"mostlydirect"}
    assert employers["mostlydirect"]["secondary_entity_rows"] == 1


def test_new_employment_counts_workers_above_zero_not_a_yes(tmp_path: Path) -> None:
    rows = [
        _row("Counted Inc", new="0"),
        _row("Counted Inc", new="1"),
        _row("Counted Inc", new="25"),  # a worker count, not "Y"
        _row("Counted Inc", new="3", soc="17-2051.00"),  # not computing: not counted
    ]
    record = _employers(_build(tmp_path, _write_xlsx(tmp_path / "a.xlsx", rows)))["counted"]
    assert record["certified_rows"] == 4
    assert record["computing_rows"] == 3
    assert record["computing_new_employment_rows"] == 2


def test_wage_levels_one_and_two_are_counted_among_computing_rows(tmp_path: Path) -> None:
    rows = [
        _row("Leveled Inc", wage="I"),
        _row("Leveled Inc", wage="II"),
        _row("Leveled Inc", wage="III"),
        _row("Leveled Inc", wage="IV"),
        _row("Leveled Inc", wage="N/A"),
        _row("Leveled Inc", wage=""),
        _row("Leveled Inc", wage="I", soc="17-2051.00"),
    ]
    record = _employers(_build(tmp_path, _write_xlsx(tmp_path / "a.xlsx", rows)))["leveled"]
    assert record["computing_rows"] == 6
    assert record["computing_low_wage_rows"] == 2


def test_record_carries_name_feins_modal_naics_modal_state_and_latest_decision(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            "Acme, Inc.", fein="22-2222222", naics="541511", state="NY", decided=SERIAL_2026_01_05
        ),
        _row("ACME INC", fein="11-1111111", naics="541512", state="CA", decided=SERIAL_2026_03_01),
        _row("Acme Inc", fein="11-1111111", naics="541512", state="CA", decided=SERIAL_2026_01_05),
    ]
    record = _employers(_build(tmp_path, _write_xlsx(tmp_path / "a.xlsx", rows)))["acme"]
    assert record["name"] == "Acme, Inc."
    assert record["feins"] == ["11-1111111", "22-2222222"]
    assert record["naics2"] == "54"
    assert record["state"] == "CA"
    assert record["latest_decision"] == "2026-03-01"


def test_names_normalizing_under_four_characters_are_not_written(tmp_path: Path) -> None:
    rows = [_row("Abc Inc"), _row("Abcd Inc"), _row("Inc")]
    employers = _employers(_build(tmp_path, _write_xlsx(tmp_path / "a.xlsx", rows)))
    assert set(employers) == {"abcd"}


def test_merge_across_files_sums_counts_and_judges_the_merged_totals(tmp_path: Path) -> None:
    first = _write_xlsx(
        tmp_path / "a.xlsx",
        [_row("Split Inc", decided=SERIAL_2026_03_01), _row("Nocode Inc", soc="17-2051.00")],
    )
    second = _write_xlsx(
        tmp_path / "b.xlsx",
        [
            _row("SPLIT, INC.", new="0", wage="III", decided=SERIAL_2026_01_05),
            _row("Nocode Inc", soc="15-1252.00"),
        ],
    )
    doc = _build(tmp_path, first, second)
    split = _employers(doc)["split"]
    assert split["certified_rows"] == 2
    assert split["computing_rows"] == 2
    assert split["computing_new_employment_rows"] == 1
    assert split["computing_low_wage_rows"] == 1
    assert split["latest_decision"] == "2026-03-01"
    assert split["name"] == "Split Inc"  # the first file's spelling
    # Neither file alone qualifies "nocode" except by the second; merged it does, with 2 rows.
    assert _employers(doc)["nocode"]["certified_rows"] == 2
    sources = doc["sources"]
    assert isinstance(sources, list)
    assert [s["file"] for s in sources] == ["a.xlsx", "b.xlsx"]


def test_header_records_build_date_and_row_counts(tmp_path: Path) -> None:
    doc = _build(tmp_path, _write_xlsx(tmp_path / "a.xlsx", [_row("Acme Inc")] * 2))
    assert doc["built"] == "2026-11-04"
    assert doc["format"] == 1
    sources = doc["sources"]
    assert isinstance(sources, list)
    assert (sources[0]["rows_read"], sources[0]["rows_counted"]) == (2, 2)  # blank rows not read


def test_missing_required_column_raises_typed_error(tmp_path: Path) -> None:
    short = tuple(h for h in HEADER if h != "PW_WAGE_LEVEL")
    path = _write_xlsx(tmp_path / "a.xlsx", [_row("Acme Inc")], header=short)
    with pytest.raises(MissingColumnError) as raised:
        build_sponsors([path], tmp_path / "cfg", today=TODAY)
    assert raised.value.missing == ("PW_WAGE_LEVEL",)
    assert isinstance(raised.value, SponsorBuildError)
    assert not (tmp_path / "cfg" / SPONSORS_FILENAME).exists()


def test_a_file_that_is_not_a_workbook_raises_typed_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(SponsorBuildError):
        build_sponsors([bad], tmp_path / "cfg", today=TODAY)


# ---- lookup ----------------------------------------------------------------------------------


def _index(tmp_path: Path, rows: list[dict[str, str | int]]) -> SponsorIndex:
    build_sponsors([_write_xlsx(tmp_path / "a.xlsx", rows)], tmp_path / "cfg", today=TODAY)
    return load_sponsor_index(tmp_path / "cfg")


def test_lookup_is_exact_so_state_does_not_match_a_longer_name(tmp_path: Path) -> None:
    index = _index(tmp_path, [_row("State and Liberty Clothing Co"), _row("Stateline Inc")])
    assert index.problem is None
    assert index.lookup("State and Liberty Clothing") is not None
    assert index.lookup("state") is None
    assert index.lookup("State & Liberty") is None
    assert index.lookup("Stateline") is not None
    assert index.lookup("State") is None


def test_lookup_finds_a_decorated_store_name(tmp_path: Path) -> None:
    index = _index(tmp_path, [_row("PayPal, Inc.")])
    record = index.lookup("🔥 PayPal")
    assert record is not None and record.name == "PayPal, Inc."
    assert index.lookup("PayPal Holdings") is None


def test_visa_group_does_not_return_visa(tmp_path: Path) -> None:
    index = _index(tmp_path, [_row("Visa Inc.")])
    assert index.lookup("Visa") is not None
    assert index.lookup("Visa Group") is None


def test_names_that_normalize_under_four_characters_are_never_matched(tmp_path: Path) -> None:
    # Planted in the file directly: a hand-edited or older file must not make "abc" match.
    _index(tmp_path, [_row("Acme Inc")])
    planted = json.loads((tmp_path / "cfg" / SPONSORS_FILENAME).read_text())
    planted["employers"]["abc"] = planted["employers"]["acme"]
    (tmp_path / "cfg" / SPONSORS_FILENAME).write_text(json.dumps(planted))
    index = load_sponsor_index(tmp_path / "cfg")
    assert index.lookup("ABC Inc") is None
    assert index.lookup("Inc") is None
    assert index.lookup("") is None
    assert index.lookup("Acme") is not None


def test_an_exclusion_removes_a_hit(tmp_path: Path) -> None:
    rows = [_row("Opal Inc"), _row("Acme Inc")]
    build_sponsors([_write_xlsx(tmp_path / "a.xlsx", rows)], tmp_path / "cfg", today=TODAY)
    assert load_sponsor_index(tmp_path / "cfg").lookup("Opal") is not None
    (tmp_path / "cfg" / EXCLUSIONS_FILENAME).write_text(
        "# reviewed as the wrong company\nopal  # a common word\n\n", encoding="utf-8"
    )
    index = load_sponsor_index(tmp_path / "cfg")
    assert index.problem is None
    assert index.lookup("Opal") is None
    assert index.lookup("OPAL, INC.") is None
    assert index.lookup("Acme") is not None


def test_missing_file_gives_an_empty_index_with_a_problem(tmp_path: Path) -> None:
    index = load_sponsor_index(tmp_path / "nowhere")
    assert index.problem is not None and SPONSORS_FILENAME in index.problem
    assert index.records == {}
    assert index.lookup("Acme") is None


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"format": 1}',
        '{"format": 2, "built": "x", "sources": [], "employers": {}}',
    ],
)
def test_unreadable_or_foreign_file_gives_an_empty_index_with_a_problem(
    tmp_path: Path, content: str
) -> None:
    (tmp_path / SPONSORS_FILENAME).write_text(content, encoding="utf-8")
    index = load_sponsor_index(tmp_path)
    assert index.problem is not None
    assert index.records == {}


def test_unreadable_exclusions_file_empties_the_index(tmp_path: Path) -> None:
    build_sponsors(
        [_write_xlsx(tmp_path / "a.xlsx", [_row("Opal Inc")])], tmp_path / "cfg", today=TODAY
    )
    (tmp_path / "cfg" / EXCLUSIONS_FILENAME).write_bytes(b"\xff\xfe\x00bad")
    index = load_sponsor_index(tmp_path / "cfg")
    assert index.problem is not None
    assert index.lookup("Opal") is None


# ---- command and isolation -------------------------------------------------------------------


def test_cli_build_reports_counts_and_writes_no_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, data = tmp_path / "config", tmp_path / "data"
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(data))
    rows = [_row("Acme Inc"), _row("Staffing Inc", secondary="Yes"), _row("Bridge Inc", soc="17-1")]
    path = _write_xlsx(tmp_path / "a.xlsx", rows)
    result = CliRunner().invoke(app, ["sponsors", "build", str(path)])
    assert result.exit_code == 0, result.output
    assert "read 3 rows" in result.output
    assert "kept 1" in result.output
    assert (config / SPONSORS_FILENAME).is_file()
    assert not data.exists()  # the store was never opened


def test_cli_build_missing_column_exits_one_with_the_column_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    short = tuple(h for h in HEADER if h != "SOC_CODE")
    path = _write_xlsx(tmp_path / "a.xlsx", [_row("Acme Inc")], header=short)
    result = CliRunner().invoke(app, ["sponsors", "build", str(path)])
    assert result.exit_code == 1
    assert "SOC_CODE" in result.output


def test_nothing_under_eligibility_imports_the_sponsor_signal() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "boardwatch" / "eligibility"
    offenders = [
        str(p) for p in root.rglob("*.py") if "rank.sponsors" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
