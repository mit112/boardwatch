"""Import a prior application history recorded in some other tool.

The ranker already suppresses a job that carries a submitted application: `applied_job_ids`
feeds `hidden_applied` in `cli/top_cmd.py`, and `delivered_unapplied` keeps the same job out
of the delivery queue. On a store whose user applied through a different tool that machinery
is starved — `applications` is empty, so a role that was applied to months ago re-surfaces and
is re-tailored on every run. This module is the one path that fills it from outside.

The file format is deliberately generic: five named columns — `company`, `title`, `url`,
`applied_at`, `status` — as CSV or JSONL. Nothing here knows about any particular source tool,
because the tool a user is migrating from is not knowable from inside boardwatch. Producing
five columns is the whole contract.

**Every input row lands in exactly one bucket and every bucket is reported.** A row that
matches nothing is the normal outcome — most of anyone's history predates the store, and a
history row for a job boardwatch does not hold cannot be recorded at all, since
`applications.job_id` is a foreign key to `jobs`. But it is never silently dropped: it is
counted as `unmatched`, and `import_report_rows` renders every row with the key that matched
it so the result can be audited by hand.

Two keys, kept apart and never blended, because they have different confidence:

* `url` is exact. Both sides fold through `core.normalize_url`, the same canonicaliser the
  duplicate suppressor and the ledger use, so "same URL" means one thing in this repo.
* `company_title` is **weaker** — a large employer reposts one title across many requisitions,
  so it can match a different req at the same company. It is off unless the caller passes
  `allow_title_match`, and the key that matched is recorded per row so a human can check it.
  **When it resolves to more than one job the row writes nothing** and is reported `ambiguous`:
  the cost of guessing wrong is asymmetric. A job wrongly marked applied is dropped from the
  queue for good and nothing ever reports that it was, whereas a job left unmarked merely
  re-surfaces. Refusing keeps the loss recoverable. The `url` key is exact, so a fan-out there
  is one posting stored twice rather than two requisitions, and it still writes to all of them.

Matching runs against **every** posting, open or closed. `applications` records what the user
did, keyed on the canonical `job_id`, and restricting the index to open postings would make
the same file import differently depending on the day it was run.
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, Any, get_args

from sqlalchemy import Connection, select

from boardwatch.core.clock import to_naive_utc
from boardwatch.core.normalize import normalize_company, normalize_title, normalize_url
from boardwatch.store.applications import (
    ApplicationStatus,
    create_application,
    get_applications,
)
from boardwatch.store.tables import companies, postings

# The closed column catalog. Extra columns in the file are ignored, so a richer export from
# another tool imports unchanged, but a header carrying none of the key columns is refused
# outright (see `parse_history`) — that is what catches a misspelled header, which would
# otherwise present as "every row unmatched".
COLUMNS: tuple[str, ...] = ("company", "title", "url", "applied_at", "status")

_STATUSES: frozenset[str] = frozenset(get_args(ApplicationStatus))

# Absent status means applied: the file is an *application* history, and a row that records
# nothing else still records that a submission happened.
DEFAULT_STATUS: ApplicationStatus = "applied"


class ImportBucket(StrEnum):
    """Where an input row ended up. Closed: the five are exhaustive and disjoint.

    A row matching several jobs where some already carry an application is `MATCHED` when this
    import wrote at least one row and `ALREADY_PRESENT` when it wrote none, so the buckets
    still sum to the input and "how many did this import write" stays answerable.

    `AMBIGUOUS` is judged before either of those and outranks both: it says the *match* could
    not be trusted, which is a fact about the key rather than about what the store already
    holds, so a re-import classifies the same row the same way whatever was written meanwhile.
    """

    MATCHED = "matched"
    ALREADY_PRESENT = "already_present"
    UNMATCHED = "unmatched"
    MALFORMED = "malformed"
    AMBIGUOUS = "ambiguous"


class MatchKey(StrEnum):
    """Which key matched a row. Reported per row: the two are not equally trustworthy."""

    URL = "url"
    COMPANY_TITLE = "company_title"


class MalformedReason(StrEnum):
    """Why a row could not be read. Typed at the raise site, never string-matched."""

    NOT_AN_OBJECT = "not_an_object"
    BAD_JSON = "bad_json"
    NO_KEY = "no_key"
    UNKNOWN_STATUS = "unknown_status"
    BAD_APPLIED_AT = "bad_applied_at"


class HistoryFormatError(ValueError):
    """The input as a whole cannot be read.

    A file with the wrong suffix or a header carrying no key column, or a directory that
    cannot be listed. One type because there is one thing the caller can do about any of
    them: report the path and stop, having read nothing.
    """


@dataclass(frozen=True)
class HistoryRow:
    """One readable input row. `line_no` is 1-based within the file, for the audit report."""

    line_no: int
    company: str | None
    title: str | None
    url: str | None
    applied_at: datetime | None
    status: ApplicationStatus


@dataclass(frozen=True)
class MalformedRow:
    """One row that could not be read. Carried, never discarded."""

    line_no: int
    reason: MalformedReason
    raw: dict[str, str]


@dataclass(frozen=True)
class RowResult:
    """The outcome for one input row: its bucket, the key that got it there, and what it wrote."""

    line_no: int
    bucket: ImportBucket
    company: str | None = None
    title: str | None = None
    url: str | None = None
    match_key: MatchKey | None = None
    job_ids: tuple[int, ...] = ()
    application_ids: tuple[int, ...] = ()
    reason: MalformedReason | None = None


@dataclass(frozen=True)
class ImportReport:
    results: tuple[RowResult, ...]

    def counts(self) -> dict[ImportBucket, int]:
        """Every bucket present, including the zeroes — absent must not read as zero."""
        tally = dict.fromkeys(ImportBucket, 0)
        for result in self.results:
            tally[result.bucket] += 1
        return tally


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_row(line_no: int, raw: dict[str, str]) -> HistoryRow | MalformedRow:
    company = _clean(raw.get("company"))
    title = _clean(raw.get("title"))
    url = _clean(raw.get("url"))
    if url is None and (company is None or title is None):
        return MalformedRow(line_no, MalformedReason.NO_KEY, raw)
    status_text = _clean(raw.get("status"))
    if status_text is None:
        status = DEFAULT_STATUS
    elif status_text.lower() in _STATUSES:
        status = status_text.lower()  # type: ignore[assignment]
    else:
        return MalformedRow(line_no, MalformedReason.UNKNOWN_STATUS, raw)
    applied_text = _clean(raw.get("applied_at"))
    applied_at: datetime | None = None
    if applied_text is not None:
        try:
            applied_at = to_naive_utc(datetime.fromisoformat(applied_text))
        except ValueError:
            return MalformedRow(line_no, MalformedReason.BAD_APPLIED_AT, raw)
    return HistoryRow(line_no, company, title, url, applied_at, status)


def _parse_csv(text: str) -> tuple[list[HistoryRow], list[MalformedRow]]:
    # StringIO rather than splitlines(): a quoted field may contain a newline, and only a
    # source that keeps its line endings lets csv reassemble it. `reader.line_num` is used for
    # the same reason — a record is not always one line, so counting records would misreport
    # which line of the file a malformed row is on.
    reader = csv.DictReader(io.StringIO(text))
    header = {(name or "").strip().lower() for name in (reader.fieldnames or [])}
    if "url" not in header and not {"company", "title"} <= header:
        raise HistoryFormatError(
            "the header needs a 'url' column, or both 'company' and 'title'. "
            f"Recognised columns: {', '.join(COLUMNS)}."
        )
    rows: list[HistoryRow] = []
    malformed: list[MalformedRow] = []
    for record in reader:
        cleaned = {
            (name or "").strip().lower(): value
            for name, value in record.items()
            if isinstance(name, str) and isinstance(value, str)
        }
        read = _read_row(reader.line_num, cleaned)
        (rows if isinstance(read, HistoryRow) else malformed).append(read)  # type: ignore[arg-type]
    return rows, malformed


def _parse_jsonl(text: str) -> tuple[list[HistoryRow], list[MalformedRow]]:
    rows: list[HistoryRow] = []
    malformed: list[MalformedRow] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed.append(MalformedRow(line_no, MalformedReason.BAD_JSON, {}))
            continue
        if not isinstance(record, dict):
            malformed.append(MalformedRow(line_no, MalformedReason.NOT_AN_OBJECT, {}))
            continue
        read = _read_row(line_no, {str(k).strip().lower(): v for k, v in record.items()})
        (rows if isinstance(read, HistoryRow) else malformed).append(read)  # type: ignore[arg-type]
    return rows, malformed


def parse_history(path: Path) -> tuple[list[HistoryRow], list[MalformedRow]]:
    """Read a history file. Format comes from the suffix; anything else is refused.

    Refused rather than sniffed: a file this writes to the funnel on the strength of a guess
    is not something to be clever about.
    """
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix in {".jsonl", ".ndjson"}:
        return _parse_jsonl(text)
    if suffix == ".csv":
        return _parse_csv(text)
    raise HistoryFormatError(f"{path.name}: expected a .csv, .jsonl or .ndjson file.")


@dataclass(frozen=True)
class MatchIndex:
    """Store-side lookup from either key to the canonical jobs behind it."""

    by_url: dict[str, frozenset[int]]
    by_company_title: dict[tuple[str, str], frozenset[int]]


def build_match_index(conn: Connection, *, include_company_title: bool) -> MatchIndex:
    """One pass over every posting. The (company, title) half is built only when it is used.

    Both keys fold through the same normalisers the duplicate suppressor uses, so "same URL"
    and "same company and title" mean here exactly what they mean everywhere else in the repo.
    """
    by_url: defaultdict[str, set[int]] = defaultdict(set)
    by_ct: defaultdict[tuple[str, str], set[int]] = defaultdict(set)
    stmt = select(
        postings.c.job_id, postings.c.url, postings.c.title, companies.c.name
    ).join(companies, postings.c.company_id == companies.c.id)
    for job_id, url, title, company_name in conn.execute(stmt):
        if job_id is None:
            continue
        if url:
            by_url[normalize_url(str(url))].add(int(job_id))
        if include_company_title and company_name and title:
            key = (normalize_company(str(company_name)), normalize_title(str(title)))
            if all(key):
                by_ct[key].add(int(job_id))
    return MatchIndex(
        by_url={key: frozenset(value) for key, value in by_url.items()},
        by_company_title={key: frozenset(value) for key, value in by_ct.items()},
    )


def _match(row: HistoryRow, index: MatchIndex) -> tuple[MatchKey, frozenset[int]] | None:
    """URL first, then the weaker key. Never both: the reported key must be the one used."""
    if row.url is not None:
        jobs = index.by_url.get(normalize_url(row.url))
        if jobs:
            return MatchKey.URL, jobs
    if row.company is not None and row.title is not None:
        key = (normalize_company(row.company), normalize_title(row.title))
        if all(key):
            jobs = index.by_company_title.get(key)
            if jobs:
                return MatchKey.COMPANY_TITLE, jobs
    return None


def import_history(
    conn: Connection,
    rows: Sequence[HistoryRow],
    malformed: Sequence[MalformedRow],
    *,
    allow_title_match: bool,
    source: str = "import",
) -> ImportReport:
    """Write an application for every matched job that does not already carry one.

    Except when the weak key fanned out: a `company_title` match covering several jobs writes
    nothing and is reported `ambiguous`. Marking a job applied hides it from the queue for
    good, so guessing which requisition the row meant is the one error this cannot take back.

    Idempotent on the job, not on the file: a job with **any** application — at any status,
    including `withdrawn` — is left alone and reported `already_present`. Two consequences,
    both deliberate. Re-importing the same file writes nothing and never bumps `attempt_no`.
    And a lead the owner deliberately withdrew (the documented drain out of the applied set)
    stays withdrawn instead of being silently re-applied by the next import.

    Runs entirely in the caller's transaction; it never begins or commits, which is what lets
    the CLI offer a dry run by simply not committing.
    """
    index = build_match_index(conn, include_company_title=allow_title_match)
    results = [
        RowResult(line_no=bad.line_no, bucket=ImportBucket.MALFORMED, reason=bad.reason)
        for bad in malformed
    ]
    for row in rows:
        found = _match(row, index)
        if found is None:
            results.append(
                RowResult(
                    line_no=row.line_no,
                    bucket=ImportBucket.UNMATCHED,
                    company=row.company,
                    title=row.title,
                    url=row.url,
                )
            )
            continue
        match_key, job_ids = found
        if match_key is MatchKey.COMPANY_TITLE and len(job_ids) > 1:
            # Refuse rather than guess. Both ids are kept so the audit names the requisitions
            # this declined to choose between; resolving it means supplying a url for the row.
            results.append(
                RowResult(
                    line_no=row.line_no,
                    bucket=ImportBucket.AMBIGUOUS,
                    company=row.company,
                    title=row.title,
                    url=row.url,
                    match_key=match_key,
                    job_ids=tuple(sorted(job_ids)),
                )
            )
            continue
        written: list[int] = []
        for job_id in sorted(job_ids):
            if get_applications(conn, job_id):
                continue
            written.append(
                create_application(
                    conn,
                    job_id=job_id,
                    status=row.status,
                    source=source,
                    occurred_at=row.applied_at,
                )
            )
        results.append(
            RowResult(
                line_no=row.line_no,
                bucket=ImportBucket.MATCHED if written else ImportBucket.ALREADY_PRESENT,
                company=row.company,
                title=row.title,
                url=row.url,
                match_key=match_key,
                job_ids=tuple(sorted(job_ids)),
                application_ids=tuple(written),
            )
        )
    results.sort(key=lambda result: result.line_no)
    return ImportReport(results=tuple(results))


def import_report_rows(results: Iterable[RowResult]) -> Iterator[dict[str, Any]]:
    """Flat per-row audit: which bucket, which key, which jobs. One row in, one row out."""
    for result in results:
        yield {
            "line_no": result.line_no,
            "bucket": str(result.bucket),
            "match_key": str(result.match_key) if result.match_key else None,
            "company": result.company,
            "title": result.title,
            "url": result.url,
            "job_ids": list(result.job_ids),
            "application_ids": list(result.application_ids),
            "reason": str(result.reason) if result.reason else None,
        }


def write_import_report(results: Iterable[RowResult], stream: IO[str]) -> int:
    count = 0
    for row in import_report_rows(results):
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        count += 1
    return count
