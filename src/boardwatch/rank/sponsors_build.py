"""Build `sponsors.json` from US Department of Labor LCA disclosure workbooks (.xlsx).

The workbooks are large (hundreds of MB of XML) and untrusted, so they are streamed with the
standard library alone: the shared-strings table is read once, then worksheet rows are consumed
one at a time and discarded. Memory stays bounded by the shared strings and the per-employer
tallies, not by the row count.

A required column that is absent raises `MissingColumnError` instead of guessing: DOL changes its
layout between years, and a guessed column would count the wrong thing without any error.
"""

from __future__ import annotations

import json
import os
import re
import zipfile
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError, iterparse

from boardwatch.rank.sponsors import (
    FORMAT_VERSION,
    MIN_KEY_LENGTH,
    SPONSORS_FILENAME,
    SponsorRecord,
    normalize_employer,
)

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_SHEET = "xl/worksheets/sheet1.xml"
_STRINGS = "xl/sharedStrings.xml"

VISA_CLASS = "H-1B"
# Exactly this. DOL also publishes "Certified - Withdrawn" (certified, then the filing was
# withdrawn); a prefix test would count those, and they are not evidence of a live filing.
STATUS_COUNTED = "Certified"
COMPUTING_SOC_PREFIX = "15-"
LOW_WAGE_LEVELS = frozenset({"I", "II"})
MAX_SECONDARY_SHARE = 0.5

REQUIRED_COLUMNS = (
    "CASE_STATUS",
    "VISA_CLASS",
    "EMPLOYER_NAME",
    "EMPLOYER_FEIN",
    "EMPLOYER_STATE",
    "NAICS_CODE",
    "SOC_CODE",
    "NEW_EMPLOYMENT",
    "PW_WAGE_LEVEL",
    "SECONDARY_ENTITY",
    "DECISION_DATE",
)

_EXCEL_EPOCH = date(1899, 12, 30)
_COLUMN_LETTERS = re.compile(r"[A-Z]+")


class SponsorBuildError(Exception):
    """The input cannot be read as an LCA disclosure workbook."""


class MissingColumnError(SponsorBuildError):
    def __init__(self, path: Path, missing: Sequence[str]) -> None:
        self.path = path
        self.missing = tuple(missing)
        super().__init__(f"{path}: required column(s) missing: {', '.join(self.missing)}")


@dataclass
class _Tally:
    name: str
    feins: set[str] = field(default_factory=set)
    certified: int = 0
    computing: int = 0
    computing_new: int = 0
    computing_low_wage: int = 0
    secondary: int = 0
    naics2: Counter[str] = field(default_factory=Counter)
    states: Counter[str] = field(default_factory=Counter)
    latest: str | None = None


@dataclass(frozen=True)
class SourceStats:
    file: str
    rows_read: int
    h1b_rows: int
    status_counts: dict[str, int]
    rows_counted: int


@dataclass(frozen=True)
class BuildResult:
    sources: tuple[SourceStats, ...]
    employers_seen: int
    kept: int
    dropped_short_name: int
    dropped_no_computing: int
    dropped_secondary: int
    path: Path


def _column_index(ref: str) -> int:
    match = _COLUMN_LETTERS.match(ref)
    if match is None:
        raise SponsorBuildError(f"bad cell reference {ref!r}")
    index = 0
    for char in match.group():
        index = index * 26 + ord(char) - 64
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    strings: list[str] = []
    with archive.open(_STRINGS) as handle:
        for _, element in iterparse(handle):
            if element.tag == _NS + "si":
                strings.append("".join(t.text or "" for t in element.iter(_NS + "t")))
                element.clear()
    return strings


def iter_rows(path: Path) -> Iterator[dict[str, str]]:
    """Yield each non-blank data row as `{REQUIRED_COLUMN: value}`, streaming the worksheet.

    Raises `MissingColumnError` before the first row if the header lacks a required column.
    Blank rows (the sheet carries about half a million trailing ones) are skipped.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if _SHEET not in names or _STRINGS not in names:
                raise SponsorBuildError(f"{path}: not an LCA workbook (no sheet or strings part)")
            strings = _shared_strings(archive)
            header: dict[int, str] | None = None
            with archive.open(_SHEET) as handle:
                sheet_data: Element | None = None
                for event, element in iterparse(handle, events=("start", "end")):
                    if event == "start":
                        if element.tag == _NS + "sheetData":
                            sheet_data = element
                        continue
                    if element.tag != _NS + "row":
                        continue
                    cells: dict[int, str] = {}
                    position = -1
                    for cell in element.iter(_NS + "c"):
                        reference = cell.get("r")
                        position = _column_index(reference) if reference else position + 1
                        value = cell.find(_NS + "v")
                        if value is None or value.text is None:
                            continue
                        cells[position] = (
                            strings[int(value.text)] if cell.get("t") == "s" else value.text
                        )
                    # Detach the row, not just empty it: a cleared row stays a child of
                    # `sheetData`, and these files carry about 800k trailing blank rows.
                    if sheet_data is not None:
                        sheet_data.clear()
                    if not cells:
                        continue
                    if header is None:
                        header = _read_header(path, cells)
                        continue
                    yield {name: cells.get(index, "") for index, name in header.items()}
    except (zipfile.BadZipFile, ParseError, IndexError, ValueError, KeyError) as exc:
        raise SponsorBuildError(f"{path}: {exc}") from exc


def _read_header(path: Path, cells: dict[int, str]) -> dict[int, str]:
    by_name = {name: index for index, name in cells.items()}
    missing = [name for name in REQUIRED_COLUMNS if name not in by_name]
    if missing:
        raise MissingColumnError(path, missing)
    return {by_name[name]: name for name in REQUIRED_COLUMNS}


def _decision_date(raw: str) -> str | None:
    """ISO date from an Excel day serial; an ISO date string passes through; else None."""
    try:
        return (_EXCEL_EPOCH + timedelta(days=int(float(raw)))).isoformat()
    except (ValueError, OverflowError):
        # Not a serial number: an ISO string is accepted, anything else carries no date.
        try:
            return date.fromisoformat(raw[:10]).isoformat()
        except ValueError:
            return None


def _new_workers(raw: str) -> int:
    # A worker COUNT (0, 1, 10, ...), not Y/N.
    try:
        return int(float(raw))
    except ValueError:
        return 0


def _accumulate(tallies: dict[str, _Tally], row: dict[str, str]) -> None:
    key = normalize_employer(row["EMPLOYER_NAME"])
    if not key:
        return
    tally = tallies.get(key)
    if tally is None:
        tally = tallies[key] = _Tally(name=row["EMPLOYER_NAME"].strip())
    tally.certified += 1
    if row["EMPLOYER_FEIN"]:
        tally.feins.add(row["EMPLOYER_FEIN"])
    if row["SECONDARY_ENTITY"].strip().lower() in {"yes", "y"}:
        tally.secondary += 1
    tally.naics2[row["NAICS_CODE"][:2]] += 1
    tally.states[row["EMPLOYER_STATE"]] += 1
    decided = _decision_date(row["DECISION_DATE"])
    if decided is not None and (tally.latest is None or decided > tally.latest):
        tally.latest = decided
    if row["SOC_CODE"].startswith(COMPUTING_SOC_PREFIX):
        tally.computing += 1
        if _new_workers(row["NEW_EMPLOYMENT"]) > 0:
            tally.computing_new += 1
        if row["PW_WAGE_LEVEL"].strip() in LOW_WAGE_LEVELS:
            tally.computing_low_wage += 1


def _tally_file(path: Path, tallies: dict[str, _Tally]) -> SourceStats:
    read = h1b = counted = 0
    statuses: Counter[str] = Counter()
    for row in iter_rows(path):
        read += 1
        if row["VISA_CLASS"] != VISA_CLASS:
            continue
        h1b += 1
        statuses[row["CASE_STATUS"]] += 1
        if row["CASE_STATUS"] != STATUS_COUNTED or not row["EMPLOYER_NAME"]:
            continue
        counted += 1
        _accumulate(tallies, row)
    return SourceStats(path.name, read, h1b, dict(sorted(statuses.items())), counted)


def _top(counter: Counter[str]) -> str:
    return counter.most_common(1)[0][0] if counter else ""


def build_sponsors(files: Sequence[Path], config_dir: Path, *, today: date) -> BuildResult:
    """Tally every file into one set of employers, keep the qualifying ones, write the data file.

    Files merge by summing counts per normalized name, and the keep rules apply to the merged
    totals, so an employer split across files is judged on all of its rows.
    """
    tallies: dict[str, _Tally] = {}
    sources = tuple(_tally_file(path, tallies) for path in files)

    employers: dict[str, SponsorRecord] = {}
    short = no_computing = secondary = 0
    for key, tally in sorted(tallies.items()):
        if len(key) < MIN_KEY_LENGTH:
            short += 1
        elif tally.computing == 0:
            no_computing += 1
        elif tally.secondary / tally.certified >= MAX_SECONDARY_SHARE:
            secondary += 1
        else:
            employers[key] = SponsorRecord(
                name=tally.name,
                feins=tuple(sorted(tally.feins)),
                certified_rows=tally.certified,
                computing_rows=tally.computing,
                computing_new_employment_rows=tally.computing_new,
                computing_low_wage_rows=tally.computing_low_wage,
                secondary_entity_rows=tally.secondary,
                naics2=_top(tally.naics2),
                state=_top(tally.states),
                latest_decision=tally.latest,
            )

    document = {
        "format": FORMAT_VERSION,
        "built": today.isoformat(),
        "sources": [
            {
                "file": s.file,
                "rows_read": s.rows_read,
                "h1b_rows": s.h1b_rows,
                "status_counts": s.status_counts,
                "rows_counted": s.rows_counted,
            }
            for s in sources
        ],
        "employers": {key: record.model_dump(mode="json") for key, record in employers.items()},
    }
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / SPONSORS_FILENAME
    staging = target.with_name(f".{target.name}.tmp")
    staging.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    os.replace(staging, target)
    return BuildResult(
        sources, len(tallies), len(employers), short, no_computing, secondary, target
    )
