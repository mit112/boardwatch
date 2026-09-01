"""Read job-apps' `_applied/` folder tree into the rows `application_history.py` expects.

job-apps (a separate, external tool) never produces an application-history export in the
five-column format `parse_history` reads. What it produces instead, once the owner marks a
role applied, is one directory per application under `_applied/`: the rendered résumé and
cover letter, the job description text, and the URL the owner opened to apply. This module is
the one adapter that bridges that gap — for each subdirectory it derives (company, title,
url) and returns them in exactly the shape `parse_history` produces, so everything downstream
of that point (matching against `postings`, writing `applications`, the bucket report) is
unchanged. It feeds `import_history`; it does not duplicate it.

The *mechanism* here is generic — company/title/url is a description any prior tool's export
could supply — but the *layout* it reads (a directory of folders, an `*.webloc` apply link,
a `job_description.txt` with a `Company:`/`Role:`/`URL:` header) is job-apps' own convention,
observed empirically in its `_applied/` output. A folder that yields neither a url nor both a
company and a title is `MalformedRow(reason=NO_KEY)` — the same closed reason a CSV row with
no key column gets, since the failure is identical: nothing to match on.

`applied_at` is never fabricated: job-apps stamps a folder's own mtime (and its files') with
authoring time, not application time — the move into `_applied/` does not touch it — so every
row here carries `applied_at=None` and takes `import_history`'s documented default of "now".
"""

from __future__ import annotations

import plistlib
import re
import xml.parsers.expat
from pathlib import Path

from boardwatch.store.application_history import (
    DEFAULT_STATUS,
    HistoryRow,
    MalformedReason,
    MalformedRow,
)

# Case-insensitive: observed files spell the labels capitalised, but nothing else requires it.
_HEADER_LINE = re.compile(r"^\s*(company|role|url)\s*:\s*(.*)$", re.IGNORECASE)

# Generous: the richest observed header (company, role, location, salary, source, posted, url,
# template, fit) is 9 lines before the "====" divider or the job text begins.
_HEADER_SCAN_LIMIT = 20


def _read_header(job_description: Path) -> tuple[str | None, str | None, str | None]:
    """(company, title, url) from a job-apps `job_description.txt` header.

    The two observed layouts disagree on order (`Company:` then `Role:`, or the reverse), so
    this scans by label, not by position, and stops at the first blank line once something has
    matched or at a `====` divider — both mark the header's end in every sample seen. That
    boundary is what keeps a `URL:` line inside the job text from being read as a key.
    """
    if not job_description.is_file():
        return None, None, None
    try:
        text = job_description.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None, None
    company: str | None = None
    title: str | None = None
    url: str | None = None
    for line in text.splitlines()[:_HEADER_SCAN_LIMIT]:
        stripped = line.strip()
        if not stripped:
            if company is not None or title is not None or url is not None:
                break
            continue
        if stripped.startswith("="):
            break
        match = _HEADER_LINE.match(line)
        if match is None:
            continue
        label, value = match.group(1).lower(), match.group(2).strip()
        if label == "company" and company is None:
            company = value or None
        elif label == "role" and title is None:
            title = value or None
        elif label == "url" and url is None:
            url = value or None
    return company, title, url


def _read_apply_url(folder: Path) -> str | None:
    """The URL from the folder's `*.webloc` — the apply link job-apps opened for this role.

    Two file names are observed (`1_apply.webloc`, `apply.webloc`); `*.webloc` covers both and
    any other numbering. A `.webloc` is a plist, read with `plistlib` rather than parsed by
    hand. A missing, unreadable, or malformed file yields `None`, which `read_jobapps_dir`
    then covers from the header's own `URL:` line rather than falling straight through to the
    weak key. `ExpatError` is caught alongside `ValueError` because it is observed in the wild:
    job-apps writes some Greenhouse embed URLs (`...?for=x&token=y`) into the plist with the
    `&` left unescaped, which is invalid XML.
    """
    candidates = sorted(folder.glob("*.webloc"))
    if not candidates:
        return None
    try:
        with candidates[0].open("rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, ValueError, xml.parsers.expat.ExpatError):
        return None
    url = plist.get("URL") if isinstance(plist, dict) else None
    if not url:
        return None
    cleaned = str(url).strip()
    return cleaned or None


def read_jobapps_dir(path: Path) -> tuple[list[HistoryRow], list[MalformedRow]]:
    """One row per immediate subdirectory of `path` — job-apps' `_applied/` layout.

    Non-directory entries (job-apps leaves a `.DS_Store` alongside the folders) are skipped;
    they were never an application record, so they are not counted at all — counting them
    would inflate the "how many folders" denominator with entries that were never candidates.
    Every subdirectory becomes exactly one `HistoryRow` or one `MalformedRow`: the same closed
    contract `parse_history` gives a CSV/JSONL row, so nothing here is silently dropped.
    """
    rows: list[HistoryRow] = []
    malformed: list[MalformedRow] = []
    folders = sorted(child for child in path.iterdir() if child.is_dir())
    for line_no, folder in enumerate(folders, start=1):
        company, title, header_url = _read_header(folder / "job_description.txt")
        # The webloc is the link job-apps actually opened to apply, so it leads; the header's
        # own `URL:` is the same posting seen through whatever surface found it, and covers
        # the folders whose plist cannot be parsed. Keeping a row off the weak key is the
        # point: `import_history` refuses a (company, title) match covering several
        # requisitions, so a recoverable url is the difference between a row landing and not.
        url = _read_apply_url(folder) or header_url
        if url is None and (company is None or title is None):
            malformed.append(
                MalformedRow(line_no, MalformedReason.NO_KEY, {"folder": folder.name})
            )
            continue
        rows.append(HistoryRow(line_no, company, title, url, None, DEFAULT_STATUS))
    return rows, malformed
