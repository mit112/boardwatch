"""`boardwatch track import` end to end: the wiring, the dry run, and the audit file.

The store-level contract is covered in tests/unit/test_application_history_import.py. What is
asserted here is what only the command can get wrong: that `--dry-run` leaves the store
untouched (it works by not committing, which is invisible to the store tests), that every
bucket is printed even at zero, and that `--report` writes one line per input row.
"""

import json
import plistlib
from pathlib import Path

from sqlalchemy import func, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import applications, companies, jobs, postings

NOW = utcnow()
URL = "https://boards.example.test/acme/1"


def _seed(data_dir: Path) -> None:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        conn.execute(
            insert(postings).values(
                company_id=company_id, job_id=job_id, provider_posting_id="a",
                title="Software Engineer", normalized_title="software engineer", url=URL,
                locations_json=["Remote"], remote_policy="remote", first_seen_at=NOW,
                last_seen_at=NOW, status="open", consecutive_missing=0, content_hash="a",
                body_text="body a",
            )
        )


def _applications(data_dir: Path) -> int:
    with get_engine(data_dir).connect() as conn:
        return int(conn.execute(select(func.count()).select_from(applications)).scalar_one())


def _history(tmp_path: Path) -> Path:
    path = tmp_path / "history.csv"
    path.write_text(
        f"company,title,url,applied_at,status\n"
        f"Acme,Software Engineer,{URL},2026-03-09,applied\n"
        f"Nowhere,Analyst,https://boards.example.test/nowhere,2026-03-10,applied\n",
        encoding="utf-8",
    )
    return path


def _run(data_dir: Path, args: list[str]):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(app, ["--data-dir", str(data_dir), *args])


def test_dry_run_reports_the_same_counts_and_writes_nothing(tmp_path: Path) -> None:
    data_dir = tmp_path / "store"
    _seed(data_dir)
    result = _run(data_dir, ["track", "import", str(_history(tmp_path)), "--dry-run"])
    assert result.exit_code == 0, result.output
    # Every bucket is printed, including the zeroes: absent must not read as zero.
    for bucket in ("matched", "already_present", "unmatched", "malformed"):
        assert bucket in result.output
    assert "would write 1 application" in result.output
    assert _applications(data_dir) == 0


def test_import_writes_and_the_report_carries_every_row(tmp_path: Path) -> None:
    data_dir = tmp_path / "store"
    _seed(data_dir)
    report = tmp_path / "audit.jsonl"
    result = _run(
        data_dir, ["track", "import", str(_history(tmp_path)), "--report", str(report)]
    )
    assert result.exit_code == 0, result.output
    assert "wrote 1 application(s) from 2 row(s)." in result.output
    assert _applications(data_dir) == 1
    rows = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines()]
    assert [(row["bucket"], row["match_key"]) for row in rows] == [
        ("matched", "url"),
        ("unmatched", None),
    ]
    assert rows[0]["application_ids"] == [1]


def test_an_unreadable_file_exits_one_without_touching_the_store(tmp_path: Path) -> None:
    data_dir = tmp_path / "store"
    _seed(data_dir)
    bad = tmp_path / "history.csv"
    bad.write_text("companyy,titel\nAcme,SWE\n", encoding="utf-8")
    result = _run(data_dir, ["track", "import", str(bad)])
    assert result.exit_code == 1
    assert "cannot read" in result.output
    assert _applications(data_dir) == 0


def _jobapps_dir(tmp_path: Path) -> Path:
    """A synthetic job-apps `_applied/` tree: one folder, matching the seeded posting by URL."""
    root = tmp_path / "_applied"
    folder = root / "Synthco_Widget_Engineer"
    folder.mkdir(parents=True)
    (folder / "1_apply.webloc").write_bytes(plistlib.dumps({"URL": URL}))
    (folder / "job_description.txt").write_text(
        "Company:  Acme\nRole:     Software Engineer\n" + "=" * 40 + "\ntext\n",
        encoding="utf-8",
    )
    return root


def test_a_directory_is_read_as_a_jobapps_applied_tree(tmp_path: Path) -> None:
    """Pre-change, `dir_okay=False` rejects a directory outright with a usage error (exit 2)
    before the store is ever touched. This is the one thing only the CLI wiring can get wrong."""
    data_dir = tmp_path / "store"
    _seed(data_dir)
    result = _run(data_dir, ["track", "import", str(_jobapps_dir(tmp_path))])
    assert result.exit_code == 0, result.output
    assert "wrote 1 application(s) from 1 row(s)." in result.output
    assert _applications(data_dir) == 1
