"""`read_jobapps_dir`: turning job-apps' `_applied/` folder tree into generic history rows.

job-apps never exports the five-column format `application_history.py` reads. This is the one
adapter that derives (company, title, url) from its folder layout so the existing matcher and
writer — already covered in `test_application_history_import.py` — need not change at all.
Fixtures below are synthetic: invented companies, titles and URLs, never a real folder name.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, func, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.store.application_history import (
    ImportBucket,
    MalformedReason,
    import_history,
)
from boardwatch.store.applications import applied_job_ids
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.jobapps_history import read_jobapps_dir
from boardwatch.store.tables import applications, companies, jobs, postings

NOW = utcnow()


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "store")
    ensure_schema(eng)
    return eng


def _posting(
    conn: Connection, *, company: str, title: str, url: str | None, key: str
) -> int:
    company_id = int(
        conn.execute(
            insert(companies).values(
                name=company, provider="lever", slug=f"slug-{key}", source="user", watched=True,
            )
        ).inserted_primary_key[0]
    )
    job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    conn.execute(
        insert(postings).values(
            company_id=company_id, job_id=job_id, provider_posting_id=key, title=title,
            normalized_title=title.lower(), url=url, locations_json=["Remote"],
            remote_policy="remote", first_seen_at=NOW, last_seen_at=NOW, status="open",
            consecutive_missing=0, content_hash=key, body_text=f"body {key}",
        )
    )
    return job_id


def _webloc(folder: Path, url: str, name: str = "1_apply.webloc") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(plistlib.dumps({"URL": url}))


def _job_description(
    folder: Path,
    *,
    company: str | None = None,
    title: str | None = None,
    reversed_order: bool = False,
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    company_line = f"Company:  {company}" if company is not None else None
    role_line = f"Role:     {title}" if title is not None else None
    lines = [role_line, company_line] if reversed_order else [company_line, role_line]
    body = "\n".join(line for line in lines if line is not None)
    body += "\nLocation: Remote\n" + "=" * 40 + "\nSome job text.\n"
    (folder / "job_description.txt").write_text(body, encoding="utf-8")


# --- parsing one folder --------------------------------------------------------------------


def test_a_folder_with_both_files_resolves_company_title_and_url(tmp_path: Path) -> None:
    root = tmp_path / "_applied"
    folder = root / "Synthco_Widget_Engineer"
    _webloc(folder, "https://jobs.example-ats.test/synthco/abc123/apply")
    _job_description(folder, company="Synthco", title="Widget Engineer")
    rows, malformed = read_jobapps_dir(root)
    assert malformed == []
    assert len(rows) == 1
    row = rows[0]
    assert (row.company, row.title, row.url, row.applied_at, row.status) == (
        "Synthco", "Widget Engineer", "https://jobs.example-ats.test/synthco/abc123/apply",
        None, "applied",
    )


def test_the_reversed_header_order_reads_the_same(tmp_path: Path) -> None:
    root = tmp_path / "_applied"
    folder = root / "Reversed_Co"
    _webloc(folder, "https://jobs.example-ats.test/reversed/1")
    _job_description(folder, company="Reversed Co", title="Backend Engineer", reversed_order=True)
    rows, _ = read_jobapps_dir(root)
    assert (rows[0].company, rows[0].title) == ("Reversed Co", "Backend Engineer")


def test_the_bare_apply_webloc_name_is_also_read(tmp_path: Path) -> None:
    root = tmp_path / "_applied"
    folder = root / "Barename_Co"
    _webloc(folder, "https://jobs.example-ats.test/barename/1", name="apply.webloc")
    _job_description(folder, company="Barename Co", title="Engineer")
    rows, _ = read_jobapps_dir(root)
    assert rows[0].url == "https://jobs.example-ats.test/barename/1"


def test_a_folder_missing_the_job_description_still_resolves_on_url(tmp_path: Path) -> None:
    root = tmp_path / "_applied"
    folder = root / "NoJD_Co"
    _webloc(folder, "https://jobs.example-ats.test/nojd/1")
    rows, malformed = read_jobapps_dir(root)
    assert malformed == []
    assert (rows[0].company, rows[0].title, rows[0].url) == (
        None, None, "https://jobs.example-ats.test/nojd/1",
    )


def test_a_folder_missing_the_webloc_still_resolves_on_company_title(tmp_path: Path) -> None:
    root = tmp_path / "_applied"
    folder = root / "NoWebloc_Co"
    _job_description(folder, company="NoWebloc Co", title="Engineer")
    rows, malformed = read_jobapps_dir(root)
    assert malformed == []
    assert (rows[0].company, rows[0].title, rows[0].url) == ("NoWebloc Co", "Engineer", None)


def test_a_folder_with_neither_is_reported_malformed_not_dropped(tmp_path: Path) -> None:
    root = tmp_path / "_applied"
    folder = root / "Empty_Co"
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text("nothing useful here", encoding="utf-8")
    rows, malformed = read_jobapps_dir(root)
    assert rows == []
    assert len(malformed) == 1
    assert malformed[0].reason is MalformedReason.NO_KEY
    assert malformed[0].raw == {"folder": "Empty_Co"}


def test_a_malformed_webloc_falls_back_to_company_title(tmp_path: Path) -> None:
    root = tmp_path / "_applied"
    folder = root / "BadPlist_Co"
    folder.mkdir(parents=True)
    (folder / "1_apply.webloc").write_text("not a plist", encoding="utf-8")
    _job_description(folder, company="BadPlist Co", title="Engineer")
    rows, malformed = read_jobapps_dir(root)
    assert malformed == []
    assert (rows[0].company, rows[0].title, rows[0].url) == ("BadPlist Co", "Engineer", None)


def test_an_unescaped_ampersand_falls_back_instead_of_crashing(tmp_path: Path) -> None:
    """Observed in 9 of the 64 real folders: job-apps writes some Greenhouse embed apply
    links into the plist with a literal, unescaped `&` — invalid XML that `plistlib` raises
    `xml.parsers.expat.ExpatError` on, not the `ValueError` a garbage file raises."""
    root = tmp_path / "_applied"
    folder = root / "Unescaped_Co"
    folder.mkdir(parents=True)
    (folder / "1_apply.webloc").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n\t<key>URL</key>\n'
        "\t<string>https://job-boards.greenhouse.io/embed/job_app?for=x&token=1</string>\n"
        "</dict>\n</plist>",
        encoding="utf-8",
    )
    _job_description(folder, company="Unescaped Co", title="Engineer")
    rows, malformed = read_jobapps_dir(root)
    assert malformed == []
    assert (rows[0].company, rows[0].title, rows[0].url) == ("Unescaped Co", "Engineer", None)


def test_non_directory_entries_are_skipped_not_counted(tmp_path: Path) -> None:
    root = tmp_path / "_applied"
    root.mkdir(parents=True)
    (root / ".DS_Store").write_bytes(b"\x00\x01")
    folder = root / "OnlyRealOne_Co"
    _webloc(folder, "https://jobs.example-ats.test/only/1")
    _job_description(folder, company="OnlyRealOne Co", title="Engineer")
    rows, malformed = read_jobapps_dir(root)
    assert len(rows) + len(malformed) == 1


def test_folders_are_read_in_a_stable_sorted_order(tmp_path: Path) -> None:
    root = tmp_path / "_applied"
    for name in ("Zeta_Co", "Alpha_Co"):
        folder = root / name
        _webloc(folder, f"https://jobs.example-ats.test/{name}/1")
        _job_description(folder, company=name, title="Engineer")
    rows, _ = read_jobapps_dir(root)
    assert [row.company for row in rows] == ["Alpha_Co", "Zeta_Co"]
    assert [row.line_no for row in rows] == [1, 2]


# --- feeding the existing matcher/writer ----------------------------------------------------


def test_a_resolved_row_writes_an_application_the_ranker_then_suppresses(
    tmp_path: Path, engine: Engine
) -> None:
    """This is the whole point: the derived row must land in `applied_job_ids`."""
    with engine.begin() as conn:
        job_id = _posting(
            conn, company="Synthco", title="Widget Engineer",
            url="https://jobs.example-ats.test/synthco/abc123", key="a",
        )
    root = tmp_path / "_applied"
    folder = root / "Synthco_Widget_Engineer"
    # The captured apply link carries a suffix path segment the stored posting URL lacks —
    # exactly the shape lever/ashby apply links take — so this row resolves on company/title.
    _webloc(folder, "https://jobs.example-ats.test/synthco/abc123/apply")
    _job_description(folder, company="Synthco", title="Widget Engineer")
    rows, malformed = read_jobapps_dir(root)
    with engine.begin() as conn:
        report = import_history(conn, rows, malformed, allow_title_match=True, source="jobapps")
    assert [result.bucket for result in report.results] == [ImportBucket.MATCHED]
    with engine.connect() as conn:
        assert applied_job_ids(conn) == {job_id: "applied"}


def test_running_the_import_twice_is_idempotent(tmp_path: Path, engine: Engine) -> None:
    with engine.begin() as conn:
        _posting(
            conn, company="Synthco", title="Widget Engineer",
            url="https://jobs.example-ats.test/synthco/abc123", key="a",
        )
    root = tmp_path / "_applied"
    folder = root / "Synthco_Widget_Engineer"
    _webloc(folder, "https://jobs.example-ats.test/synthco/abc123")
    _job_description(folder, company="Synthco", title="Widget Engineer")

    rows, malformed = read_jobapps_dir(root)
    with engine.begin() as conn:
        first = import_history(conn, rows, malformed, allow_title_match=True)
    assert first.results[0].bucket is ImportBucket.MATCHED
    written = first.results[0].application_ids

    rows2, malformed2 = read_jobapps_dir(root)
    with engine.begin() as conn:
        second = import_history(conn, rows2, malformed2, allow_title_match=True)
    assert second.results[0].bucket is ImportBucket.ALREADY_PRESENT
    assert second.results[0].application_ids == ()

    with engine.connect() as conn:
        total = int(conn.execute(select(func.count()).select_from(applications)).scalar_one())
    assert total == len(written) == 1
