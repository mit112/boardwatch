"""The delivery queue on disk (design §4, §4.3).

A real schema on `tmp_path`, a real applications tree on `tmp_path`, a real queue root on
`tmp_path`. Nothing here opens the live store or writes anywhere near `~/boardwatch-queue` or
`~/boardwatch-applications`; `_scratch_config` forces both boardwatch directories onto `tmp_path`
because `queue_detail` resolves the eligibility identity through `load_settings()`.

Three things these tests are built to catch, because each is a defect that passes a naive suite:

- **An implementation that created empty directories.** Every creation test asserts the *bytes* of
  the copied PDF, the *text* of the JD, and the URL inside the link file — never only that a path
  exists. `_files_under` is used for the exhaustive-contents assertions so an extra file is a
  failure rather than an unnoticed pass.
- **A "second sync wrote nothing" test that is really "second sync did nothing useful".** The
  idempotence test compares `st_mtime_ns` of every file, and its control
  (`test_a_changed_jd_rewrites_the_folder`) proves the same comparison does trip when the data
  moves. Without the control, an implementation that never wrote at all would be green.
- **A sidecar assertion aimed at a folder that never had sidecars.** The source lead folder
  created by `_lead_folder` *always* contains `resume.projected.yaml` and
  `projection-manifest.json`, so the trap sits exactly where a `shutil.copytree` would pick it up.
  The two names are spelled out here rather than imported from the implementation: importing them
  would let a change that emptied the constant make this test vacuous.

Where a test patches a private seam to simulate a crash, `monkeypatch.undo()` runs *before* the
assertions. A patch left active while pytest renders an assertion failure turns that failure into
an INTERNALERROR that aborts the whole run, which can mask a vacuous test elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import plistlib
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from filelock import FileLock
from sqlalchemy import Connection, Engine, insert, select, update

from boardwatch.core import lock_reclaim
from boardwatch.core.settings import load_settings
from boardwatch.delivery import DRAIN_DIRS, queue
from boardwatch.delivery.queue import (
    APPLIED_DIR,
    CLOSED_DIR,
    DETAILS_FILE,
    INELIGIBLE_DIR,
    JD_FILE,
    LINK_FILE,
    LOCK_FILE,
    REPORTED_DIR,
    REVIEW_DIR,
    SKIPPED_DIR,
    URL_FILE,
    WEBLOC_FILE,
    _identity_hash,
    _plan,
    reconcile_queue,
    sync_queue,
)
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate, write_evaluation
from boardwatch.eligibility.facts import Facts, Policy, WorkAuthFact, facts_payload
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.store.applications import create_application, set_application_status
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.delivery_queries import QueueDetail, QueueRow
from boardwatch.store.queries import save_eligibility, save_profile
from boardwatch.store.queue_state import (
    mark_job_reported,
    mark_job_skipped,
    unmark_job_reported,
    unmark_job_skipped,
)
from boardwatch.store.tables import (
    artifacts,
    companies,
    jobs,
    posting_versions,
    postings,
    runs,
)

NOW = datetime(2026, 8, 26, 12, 0, 0)
OWNER = "Mit Sheth"
JD = (
    "Bachelor's degree in Computer Science required. 2+ years of professional experience with "
    "Python and distributed systems. This role is based in Boston."
)
APPLY_URL = "https://boards.test/apply?gh_jid=1&src=a&b=c"

# Spelled out, never imported: the fabrication audit
# (`.agent/2026-08-25-craft-findings/b4_fabrication_audit.py:127-129`) identifies a delivered
# résumé as a directory holding BOTH of these names, and a queue folder holding them would make
# that gate double-count today and audit nothing after a refactor.
SIDECARS = ("resume.projected.yaml", "projection-manifest.json")


@pytest.fixture(autouse=True)
def _scratch_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "queue"


@pytest.fixture()
def apps(tmp_path: Path) -> Path:
    """Stands in for `~/boardwatch-applications`. Never touched by anything under test."""
    return tmp_path / "applications"


# --------------------------------------------------------------------------------------- seeding


def _lead_folder(apps: Path, key: str, *, pdf: bool = True) -> tuple[Path, Path]:
    """One canonical lead folder, shaped like the dated tree: `(typ_path, pdf_path)`.

    The two projection sidecars are always written. They are the fixture trap for constraint 3 and
    they sit where the code reads — a `copytree` implementation copies them out of here.
    """
    folder = apps / "2026-08-26" / key
    folder.mkdir(parents=True)
    typ = folder / f"tailored-{key}.typ"
    typ.write_text(f"#typ for {key}\n", encoding="utf-8")
    pdf_path = folder / f"tailored-{key}.pdf"
    if pdf:
        pdf_path.write_bytes(b"%PDF-1.7\n" + key.encode() + b"\n%%EOF\n")
    for sidecar in SIDECARS:
        (folder / sidecar).write_text(f"{sidecar} for {key}\n", encoding="utf-8")
    return typ, pdf_path


def _queue_row(posting_id: int, company: str, title: str) -> QueueRow:
    """A minimal `QueueRow` for the naming pass, which reads only these fields."""
    return QueueRow(
        posting_id=posting_id,
        job_id=posting_id,
        title=title,
        company=company,
        location=None,
        locations=(),
        remote_policy=None,
        posted_days=None,
        first_seen=NOW,
        status="open",
        verdict="eligible",
        apply_url=f"https://example.test/{posting_id}",
        delivered_run_id=1,
        tex_uri="file:///lead.tex",
        pdf_uri="file:///lead.pdf",
        target_flag=None,
    )


def _deliver(
    conn: Connection,
    apps: Path,
    key: str,
    *,
    job_id: int | None = None,
    company: str = "Acme Corp",
    title: str = "Software Engineer",
    url: str | None = APPLY_URL,
    body: str = JD,
    pdf: bool = True,
    pdf_uri: str | None | bool = True,
    delivered_at: datetime = NOW,
    watched: bool = True,
    locations: tuple[str, ...] = ("Boston, MA",),
) -> tuple[int, int]:
    """One delivered lead: company, job, posting, frozen version, tailored artifact, disk folder.

    Returns `(posting_id, job_id)`. `pdf=False` writes no PDF on disk; `pdf_uri=None` records an
    artifact whose `meta_json` names no PDF at all. The two are different absences.
    """
    typ, pdf_path = _lead_folder(apps, key, pdf=pdf)
    run_id = int(
        conn.execute(insert(runs).values(started_at=NOW, boards_attempted=1)).inserted_primary_key[
            0
        ]
    )
    company_id = int(
        conn.execute(
            insert(companies).values(
                name=company,
                provider="greenhouse",
                slug=f"slug-{key}",
                source="user",
                watched=watched,
                tags_json=None,
            )
        ).inserted_primary_key[0]
    )
    job = (
        int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        if job_id is None
        else job_id
    )
    posting_id = int(
        conn.execute(
            insert(postings).values(
                company_id=company_id,
                job_id=job,
                provider_posting_id=key,
                title=title,
                normalized_title=title.lower(),
                url=url,
                locations_json=list(locations),
                remote_policy="hybrid",
                posted_at=NOW - timedelta(days=4),
                first_seen_at=NOW - timedelta(days=4),
                last_seen_at=NOW,
                status="open",
                closed_at=None,
                consecutive_missing=0,
                content_hash=f"hash-{key}",
                body_text=body,
            )
        ).inserted_primary_key[0]
    )
    version_id = int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id,
                content_hash=f"v-{key}",
                body_text=body,
                captured_at=NOW,
                run_id=run_id,
                capture_reason="new",
            )
        ).inserted_primary_key[0]
    )
    meta: dict[str, object] = {}
    if pdf_uri is True:
        meta["pdf_uri"] = str(pdf_path)
    elif pdf_uri is None:
        meta["pdf_uri"] = None
    conn.execute(
        insert(artifacts).values(
            posting_version_id=version_id,
            kind="resume_tailored",
            uri=str(typ),
            generator="boardwatch.tailor",
            media_type="text/x-typst",
            meta_json=meta,
            created_at=delivered_at,
            run_id=run_id,
        )
    )
    return posting_id, job


# ------------------------------------------------------------------------------------- assertions


def _folders(base: Path) -> list[str]:
    if not base.is_dir():
        return []
    return sorted(
        path.name
        for path in base.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and path.name not in DRAIN_DIRS
    )


def _files_under(base: Path) -> list[str]:
    """Every file below `base`, relative and sorted. Used so an EXTRA file fails a test."""
    return sorted(str(path.relative_to(base)) for path in base.rglob("*") if path.is_file())


def _details(folder: Path) -> dict[str, object]:
    parsed = json.loads((folder / DETAILS_FILE).read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _snapshot(base: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(base)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def _link_url(folder: Path) -> str:
    """The apply URL read back out of whichever shortcut format was written.

    Parsed per format rather than grepped: a `.webloc` is XML, so it escapes the `&` in a query
    string, and a substring check against the raw bytes would fail against a CORRECT plist while
    passing against a hand-rolled one that forgot to escape.
    """
    if (folder / WEBLOC_FILE).exists():
        parsed = plistlib.loads((folder / WEBLOC_FILE).read_bytes())
        assert isinstance(parsed, dict)
        return str(parsed["URL"])
    if (folder / URL_FILE).exists():
        body = (folder / URL_FILE).read_text(encoding="utf-8")
        return body.split("URL=", 1)[1].strip()
    return (folder / LINK_FILE).read_text(encoding="utf-8").strip()


def _sole_folder(root: Path) -> Path:
    names = _folders(root)
    assert len(names) == 1, names
    return root / names[0]


# ------------------------------------------------------------------------------------- creation


def test_sync_creates_a_folder_holding_the_pdf_the_link_the_jd_and_the_details(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The whole contract of one entry, asserted on CONTENT — an implementation that created four
    empty files passes none of these."""
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, apps, "one")
    source_pdf = (apps / "2026-08-26" / "one" / "tailored-one.pdf").read_bytes()

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.updated, report.unchanged, report.failed) == (1, 0, 0, 0)
    folder = root / "Acme_Corp_Software_Engineer"
    assert folder.is_dir()
    pdf = folder / "Mit_Sheth_Acme_Corp_Software_Engineer.pdf"
    assert pdf.read_bytes() == source_pdf
    assert (folder / JD_FILE).read_text(encoding="utf-8") == JD
    link = folder / queue._apply_link(APPLY_URL, queue.PLATFORM)[0]
    assert _link_url(folder) == APPLY_URL

    details = _details(folder)
    assert details["posting_id"] == posting_id
    assert details["job_id"] == job_id
    assert details["company"] == "Acme Corp"
    assert details["title"] == "Software Engineer"
    assert details["apply_url"] == APPLY_URL
    assert details["pdf_missing"] is False
    assert details["pdf_filename"] == pdf.name
    assert details["job_description_file"] == JD_FILE
    # Lineage (design §4.2): the artifact row, the file that was copied, and its content hash.
    assert isinstance(details["source_artifact_id"], int)
    assert details["source_uri"] == str(apps / "2026-08-26" / "one" / "tailored-one.pdf")
    assert details["source_tex_uri"] == str(apps / "2026-08-26" / "one" / "tailored-one.typ")
    assert isinstance(details["pdf_sha256"], str) and len(details["pdf_sha256"]) == 64
    assert details["board_target"] == "greenhouse:slug-one"

    assert _files_under(folder) == sorted([pdf.name, link.name, JD_FILE, DETAILS_FILE])


def test_details_json_records_unverifiable_for_a_board_nobody_enumerates(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The folder on disk states what the page states. `details.json` is the owner's own copy of
    the lead, so writing `open` there would put the claim D-314 says is unsupported into a file
    that outlives the store.
    """
    with engine.begin() as conn:
        _deliver(conn, apps, "unwatched", company="Unwatched Co", watched=False)
        _deliver(conn, apps, "watched", company="Watched Co", watched=True)
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)

    assert _details(root / "Unwatched_Co_Software_Engineer")["status"] == "unverifiable"
    assert _details(root / "Watched_Co_Software_Engineer")["status"] == "open"


def test_the_recorded_pdf_hash_is_the_hash_of_the_bytes_actually_copied(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A hash of the wrong bytes is worse than none — it is lineage that lies. Recomputed here
    through a different path than the implementation used to produce it."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root)
    copied = (folder / "Mit_Sheth_Acme_Corp_Software_Engineer.pdf").read_bytes()
    assert _details(folder)["pdf_sha256"] == hashlib.sha256(copied).hexdigest()


def test_the_owner_name_comes_from_the_argument_and_never_from_a_constant(
    engine: Engine, root: Path, apps: Path
) -> None:
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name="Ana María Ruiz")
    folder = _sole_folder(root)
    assert (folder / "Ana_María_Ruiz_Acme_Corp_Software_Engineer.pdf").is_file()


# ------------------------------------------------------------------------------------ idempotence


def test_a_second_sync_rewrites_nothing_at_all(engine: Engine, root: Path, apps: Path) -> None:
    """Mtimes, not "no error". `st_mtime_ns` of every file must be untouched, and the report must
    say `unchanged` rather than `updated` — an implementation that rewrote identical bytes would
    pass a bytes-only comparison."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    before = _snapshot(root)
    assert before, "nothing was written, so the comparison below would be vacuous"
    # A coarse filesystem timestamp would hide a rewrite; sleep past it.
    time.sleep(0.02)

    with engine.connect() as conn:
        second = sync_queue(conn, root=root, owner_name=OWNER)

    assert (second.created, second.updated, second.unchanged, second.failed) == (0, 0, 1, 0)
    assert _snapshot(root) == before


def test_a_changed_jd_rewrites_the_folder(engine: Engine, root: Path, apps: Path) -> None:
    """The control that makes the idempotence test mean something: the same mtime comparison DOES
    trip when the database moves under the queue."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    before = _snapshot(root)
    time.sleep(0.02)

    revised = JD + " Updated: now also requires Rust."
    with engine.begin() as conn:
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id,
                content_hash="v-one-revised",
                body_text=revised,
                captured_at=NOW + timedelta(hours=1),
                run_id=None,
                capture_reason="revised",
            )
        )
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.updated, report.unchanged) == (0, 1, 0)
    folder = _sole_folder(root)
    assert (folder / JD_FILE).read_text(encoding="utf-8") == revised
    assert _snapshot(root) != before


def test_a_replaced_source_pdf_rewrites_the_folder(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The other half of the control: the PDF enters the idempotence key through its content hash,
    so re-tailoring the same lead must re-copy it."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    (apps / "2026-08-26" / "one" / "tailored-one.pdf").write_bytes(b"%PDF-1.7\nnew bytes\n%%EOF\n")

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.updated, report.unchanged) == (0, 1, 0)
    folder = _sole_folder(root)
    assert (folder / "Mit_Sheth_Acme_Corp_Software_Engineer.pdf").read_bytes().endswith(
        b"new bytes\n%%EOF\n"
    )


# ------------------------------------------------------------- the dated tree, and the sidecars


def test_no_projection_sidecar_ever_appears_under_the_queue_root(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Constraint 3. The source folders hold both sidecar names, so this fails against any
    implementation that copies a directory rather than naming its files."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
        _deliver(conn, apps, "two", title="Backend Engineer")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)

    for sidecar in SIDECARS:
        assert list(root.rglob(sidecar)) == []
        # The control: the name really is present in the population being copied FROM, so the
        # absence above is a fact about the queue and not about the fixture.
        assert len(list(apps.rglob(sidecar))) == 2


def test_the_applications_tree_is_untouched_byte_for_byte(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Constraint 1. `pipeline/freshness.py:97-110` treats a moved lead folder as a run-level
    fatal, so a sync that moved or rewrote anything here would break every future run."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
        _deliver(conn, apps, "two", title="Backend Engineer")
    before = _snapshot(apps)
    assert len(before) == 8, before  # two folders x (typ, pdf, two sidecars)

    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
        reconcile_queue(conn, root=root)

    assert _snapshot(apps) == before


def test_sync_writes_no_artifacts_row_pointing_into_the_queue(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Constraint 2. Lineage lives in `details.json`; a stored URI a folder move can invalidate is
    the defect this design exists to avoid."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        before = conn.execute(select(artifacts.c.id, artifacts.c.uri)).all()
        report = sync_queue(conn, root=root, owner_name=OWNER)
        # Checked on the SAME connection, before it closes. An insert on a connection nobody
        # commits is rolled back at close, so the fresh-connection check below alone would be
        # blind to it.
        assert conn.execute(select(artifacts.c.id, artifacts.c.uri)).all() == before
    assert report.created == 1, "the check above would be vacuous if nothing was synced"
    with engine.connect() as conn:
        rows = conn.execute(select(artifacts.c.id, artifacts.c.uri)).all()
    assert rows == before
    assert [str(row.uri) for row in rows if str(root) in str(row.uri)] == []


# -------------------------------------------------------------------------------- absences


def test_a_missing_source_pdf_still_delivers_the_link_and_the_jd(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A missing PDF must not cost the owner the apply link and the JD."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one", pdf=False)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.failed) == (1, 0)
    folder = _sole_folder(root)
    details = _details(folder)
    assert details["pdf_missing"] is True
    assert details["pdf_absent_reason"] == "source_file_missing"
    assert details["pdf_filename"] is None
    assert details["pdf_sha256"] is None
    assert list(folder.glob("*.pdf")) == []
    # The point of the test: everything else still arrived.
    assert (folder / JD_FILE).read_text(encoding="utf-8") == JD
    assert _link_url(folder) == APPLY_URL


def test_an_artifact_naming_no_pdf_is_a_different_absence_from_a_missing_file(
    engine: Engine, root: Path, apps: Path
) -> None:
    with engine.begin() as conn:
        _deliver(conn, apps, "one", pdf=False, pdf_uri=None)
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    details = _details(_sole_folder(root))
    assert details["pdf_missing"] is True
    assert details["pdf_absent_reason"] == "no_pdf_artifact"
    assert details["source_uri"] is None


def test_a_posting_with_no_url_writes_no_link_file_at_all(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Not an empty link file. An empty URL is a broken shortcut the owner would click on."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one", url=None)
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)

    folder = _sole_folder(root)
    assert _files_under(folder) == sorted(
        ["Mit_Sheth_Acme_Corp_Software_Engineer.pdf", JD_FILE, DETAILS_FILE]
    )
    for name in (WEBLOC_FILE, URL_FILE, LINK_FILE):
        assert not (folder / name).exists()
    details = _details(folder)
    assert details["apply_link_file"] is None
    assert details["apply_link_absent_reason"] == "no_apply_url"
    assert details["apply_url"] is None


def test_a_posting_with_no_jd_body_writes_no_description_file(
    engine: Engine, root: Path, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`queue_detail` documents `jd_body is None` — never `""` — for a posting with no current
    version, and this asserts the queue honours that distinction.

    Reached by patching the read this module binds rather than by seeding it, because the schema
    makes the state unreachable end to end: `posting_versions.body_text` is NOT NULL and
    `delivered_unapplied` INNER-JOINs a delivered lead to its version, so a delivered lead always
    resolves one. The contract still admits `None`, and a queue that wrote an empty
    `job_description.txt` for it would be claiming the employer published a blank JD.
    """
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    real = queue.queue_detail

    def bodyless(conn: Connection, posting_id: int) -> QueueDetail | None:
        detail = real(conn, posting_id)
        assert detail is not None
        return QueueDetail(
            row=detail.row,
            jd_body=None,
            requirements=detail.requirements,
            board_target=detail.board_target,
        )

    monkeypatch.setattr(queue, "queue_detail", bodyless)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    monkeypatch.undo()

    assert (report.created, report.failed) == (1, 0)
    folder = _sole_folder(root)
    assert not (folder / JD_FILE).exists()
    details = _details(folder)
    assert details["job_description_file"] is None
    assert details["job_description_absent_reason"] == "no_current_version"


# ------------------------------------------------------------------------- the apply-link format


@pytest.mark.parametrize(
    ("platform", "name"),
    [("darwin", WEBLOC_FILE), ("win32", URL_FILE), ("linux", LINK_FILE), ("freebsd13", LINK_FILE)],
)
def test_the_apply_link_filename_is_chosen_by_platform(platform: str, name: str) -> None:
    assert queue._apply_link(APPLY_URL, platform)[0] == name


def test_the_webloc_is_a_plist_a_plist_reader_can_read() -> None:
    """Asserted by PARSING it, not by substring. A hand-rolled plist that failed to escape the
    ampersand in the URL would pass a substring check and fail here."""
    _, body = queue._apply_link(APPLY_URL, "darwin")
    assert plistlib.loads(body) == {"URL": APPLY_URL}


def test_the_windows_shortcut_is_an_internet_shortcut_section() -> None:
    _, body = queue._apply_link(APPLY_URL, "win32")
    assert body.decode("utf-8") == f"[InternetShortcut]\r\nURL={APPLY_URL}\r\n"


def test_the_fallback_link_is_the_bare_url() -> None:
    _, body = queue._apply_link(APPLY_URL, "linux")
    assert body.decode("utf-8") == f"{APPLY_URL}\n"


def test_sync_writes_the_platform_the_module_bound(
    engine: Engine, root: Path, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The choice is made through this module's own binding, so a Windows owner gets `apply.url`
    from the same code path a macOS owner gets `apply.webloc` from."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    monkeypatch.setattr(queue, "PLATFORM", "win32")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    monkeypatch.undo()

    folder = _sole_folder(root)
    assert (folder / URL_FILE).read_text(encoding="utf-8").startswith("[InternetShortcut]")
    assert not (folder / WEBLOC_FILE).exists()
    assert _details(folder)["apply_link_file"] == URL_FILE


# ------------------------------------------------------------------------------- drain and undrain


def test_an_applied_lead_drains_to_applied(engine: Engine, root: Path, apps: Path) -> None:
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name
    contents = _snapshot(root / folder)
    assert contents, "an empty folder would make the move below unfalsifiable"

    with engine.begin() as conn:
        create_application(conn, job_id=job_id, status="applied", source="test")
    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root)

    assert (report.to_applied, report.to_skipped, report.to_queue, report.failed) == (1, 0, 0, 0)
    assert _folders(root) == []
    assert _folders(root / APPLIED_DIR) == [folder]
    # Moved, not re-created: the same bytes, and the same inode's mtimes.
    assert _snapshot(root / APPLIED_DIR / folder) == contents


def test_withdrawing_the_application_returns_the_lead_to_the_queue(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`withdrawn` is outside `APPLIED_STATUSES`, which is the documented drain, so the folder must
    come back. The database is authoritative in BOTH directions."""
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name
    with engine.begin() as conn:
        app_id = create_application(conn, job_id=job_id, status="applied", source="test")
    with engine.connect() as conn:
        reconcile_queue(conn, root=root)
    assert _folders(root / APPLIED_DIR) == [folder]

    with engine.begin() as conn:
        set_application_status(conn, application_id=app_id, to_status="withdrawn", source="test")
    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root)

    assert (report.to_queue, report.to_applied, report.failed) == (1, 0, 0)
    assert _folders(root) == [folder]
    assert _folders(root / APPLIED_DIR) == []


def test_a_skipped_lead_drains_to_skipped_and_unskipping_brings_it_back(
    engine: Engine, root: Path, apps: Path
) -> None:
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name

    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=job_id, at=NOW)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert (drained.to_skipped, drained.to_applied, drained.failed) == (1, 0, 0)
    assert _folders(root / SKIPPED_DIR) == [folder]
    assert _folders(root) == []

    with engine.begin() as conn:
        unmark_job_skipped(conn, job_id=job_id)
    with engine.connect() as conn:
        restored = reconcile_queue(conn, root=root)
    assert (restored.to_queue, restored.failed) == (1, 0)
    assert _folders(root) == [folder]
    assert _folders(root / SKIPPED_DIR) == []


def test_a_reported_lead_drains_to_its_own_folder_and_comes_back_when_un_reported(
    engine: Engine, root: Path, apps: Path
) -> None:
    """D-427's deferral, closed. The Report action hid a lead from the web queue but left its
    folder at the top level, so the owner still saw it in the apply pile.

    **The drain runs on BOTH sides, which is what makes it a drain and not a trapdoor** — the
    quarantine rule requires the re-entry path be designed in the same change, and `Report` ships
    an Undo, so un-reporting has to return the lead by the same mechanism that removed it.

    `to_reported` is asserted alongside `moved`: the count is reported on the run line, and a
    drain omitted from `moved` prints "0 moved" while folders move — the exact unreported-number
    defect the `moved` property was added to fix.
    """
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name

    with engine.begin() as conn:
        mark_job_reported(conn, job_id=job_id, at=NOW)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert (drained.to_reported, drained.moved, drained.failed) == (1, 1, 0)
    assert _folders(root / REPORTED_DIR) == [folder]
    assert _folders(root) == []

    with engine.begin() as conn:
        unmark_job_reported(conn, job_id=job_id)
    with engine.connect() as conn:
        restored = reconcile_queue(conn, root=root)
    assert (restored.to_queue, restored.failed) == (1, 0)
    assert _folders(root) == [folder]
    assert _folders(root / REPORTED_DIR) == []


def test_the_sync_that_follows_a_report_does_not_mint_the_folder_again(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The half a reconcile-only test cannot see, and the reason `_reported` is NOT `_ineligible`.

    `_sync_queue` calls `reconcile_queue` and then `sync_queue` in ONE call. Without withholding
    the reported job from `delivered_unapplied`, reconcile moves the folder into `_reported/` and
    the sync immediately behind it **RELOCATES IT STRAIGHT BACK OUT** — so the lead the owner
    reported is in the apply queue again every run, while the reconcile count reads a healthy 1.

    **`moved` is the tell, and `created` is NOT** — that distinction was got wrong first time and
    a review caught it. `_index` scans `_reported/`, so `_entry_for` finds the drained folder and
    the relocation pass MOVES it; nothing is ever created, so `report.created == 0` holds against
    the broken implementation too and pins nothing. Verified by mutation, both ways round.

    A reported lead's verdict is still `eligible`, which is exactly why reusing `_ineligible`
    would fail here: reconcile pulls an ineligible folder back out the moment the verdict clears,
    and this one never was ineligible.
    """
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name

    with engine.begin() as conn:
        mark_job_reported(conn, job_id=job_id, at=NOW)
    with engine.connect() as conn:
        reconcile_queue(conn, root=root)
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert report.moved == 0, "sync relocated a reported lead back to the apply queue"
    assert report.created == 0
    assert _folders(root) == []
    assert _folders(root / REPORTED_DIR) == [folder]


def test_an_applied_or_skipped_lead_keeps_that_folder_even_when_also_reported(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The precedence boundary, asserted from the side that could silently swallow a lead.

    `reported` outranks the derived drains — it is an owner statement — but ranks below the two
    statements about what the owner DID with the lead. Nothing is lost by that: the
    `queue.reported.<job_id>` marker is the record a later investigation reads, and it survives
    whichever folder holds the copy.

    Asserted with `_skipped` rather than `_applied` because `closed_job_ids` and the applied set
    are both built from `delivered_unapplied`, which excludes applied leads unconditionally — so
    the applied-versus-reported ordering is unobservable by construction, exactly as the closed
    tests already record.
    """
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name

    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=job_id, at=NOW)
        mark_job_reported(conn, job_id=job_id, at=NOW)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)

    assert (drained.to_skipped, drained.to_reported) == (1, 0)
    assert _folders(root / SKIPPED_DIR) == [folder]
    assert _folders(root / REPORTED_DIR) == []


INELIGIBLE_JD = "Applicants must be authorized to work in the United States."


def _make_ineligible(conn: Connection, posting_id: int) -> None:
    """Give the lead a REAL `ineligible` verdict under a real stored profile identity.

    Goes through `evaluate` + `write_evaluation` under the same facts/policy the profile stores,
    so `current_identity` recomputes the identity the read actually looks up — a hand-written
    `profile_hash` would pass against any implementation that hand-wrote the same constant.

    The `assert` on the verdict is the test's own premise, stated out loud: if the engine ever
    stops calling this body ineligible, these tests fail loudly instead of silently draining
    nothing and passing.
    """
    facts = Facts(
        work_authorization=WorkAuthFact(status="needs_sponsorship", jurisdiction="us")
    )
    policy = Policy(families={"work_auth": "blocker"})
    save_profile(
        conn, text="resume", target_titles=["software engineer"], exclude_titles=[],
        locations=["Boston, MA"], remote_only=False, skills=["python"],
        taxonomy_version="v1", resume_max_pages=1,
    )
    save_eligibility(
        conn, facts_json=facts_payload(facts), policy_json=policy.model_dump(mode="json")
    )
    version_id = int(
        conn.execute(
            select(posting_versions.c.id).where(posting_versions.c.posting_id == posting_id)
        ).scalar_one()
    )
    catalog = load_rules(load_settings().config_dir)
    result = evaluate(INELIGIBLE_JD, facts, policy, catalog)
    assert result.verdict == "ineligible", (
        f"premise broken: this body now resolves {result.verdict!r}, so the drain tests below "
        f"would pass without draining anything"
    )
    identity = build_identity(
        posting_version_id=version_id, facts=facts, policy=policy, catalog=catalog,
        declared_fields=declared_fields(),
    )
    write_evaluation(conn, posting_version_id=version_id, identity=identity, result=result)


def test_an_ineligible_lead_drains_and_sync_does_not_rebuild_it(
    engine: Engine, root: Path, apps: Path
) -> None:
    """An ineligible lead is not work, so it leaves the queue — and STAYS gone.

    The second `sync_queue` is the load-bearing half: excluding the row from the drain without
    excluding it from sync would move the folder out and immediately build a second one beside
    it, which is worse than leaving it where it was.
    """
    with engine.begin() as conn:
        posting_id, _job_id = _deliver(conn, apps, "one", body=INELIGIBLE_JD)
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name

    with engine.begin() as conn:
        _make_ineligible(conn, posting_id)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert (drained.to_ineligible, drained.to_applied, drained.to_skipped, drained.failed) == (
        1, 0, 0, 0,
    )
    assert _folders(root / INELIGIBLE_DIR) == [folder]
    assert _folders(root) == []

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root) == [], "sync rebuilt a folder for a lead the gate rejects"
    assert _folders(root / INELIGIBLE_DIR) == [folder]
    assert report.created == 0


def test_a_verdict_that_no_longer_governs_returns_the_lead_to_the_queue(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The drain self-heals in BOTH directions, exactly as `_applied` and `_skipped` do.

    The verdict is retired the way production retires one: `eligibility_evaluations` is
    append-only (its own trigger says so), so a stored verdict is never deleted — it stops
    governing when the profile identity moves and `current_verdicts` no longer matches it. That
    is precisely what D-319 did to 267,434 rows, so this exercises the real mechanism rather
    than a delete the schema forbids.
    """
    # Deliver and sync FIRST, so a real folder exists to be drained. Making it ineligible before
    # the first sync would mean no folder was ever built, which is a different behaviour (and the
    # one the previous test's second half pins).
    with engine.begin() as conn:
        posting_id, _job_id = _deliver(conn, apps, "one", body=INELIGIBLE_JD)
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    drained_folder = _folders(root)
    assert len(drained_folder) == 1, "premise: a folder must exist before it can drain"

    with engine.begin() as conn:
        _make_ineligible(conn, posting_id)
    with engine.connect() as conn:
        reconcile_queue(conn, root=root)
    assert _folders(root) == [], "premise: the lead must be drained before it can come back"
    assert _folders(root / INELIGIBLE_DIR) == drained_folder

    with engine.begin() as conn:
        save_eligibility(
            conn,
            facts_json=facts_payload(Facts()),
            policy_json=Policy().model_dump(mode="json"),
        )
    with engine.connect() as conn:
        restored = reconcile_queue(conn, root=root)
    assert restored.to_queue == 1
    assert _folders(root / INELIGIBLE_DIR) == []
    assert _folders(root) == drained_folder


def test_an_applied_lead_that_is_also_ineligible_stays_in_applied(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Precedence, and it matters: an application is a statement the OWNER made about what they
    did. A rule tightening months later must not sweep that record into an eligibility drain.

    Note what actually holds this: `ineligible_job_ids` derives from `delivered_unapplied`, which
    already excludes applied jobs, so an applied lead never reaches `_wanted_location`'s ordering
    at all. Reordering the branches does NOT break this test — verified by mutation. It pins the
    end state, and `test_wanted_location_prefers_an_owner_statement` pins the ordering itself.
    """
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, apps, "one", body=INELIGIBLE_JD)
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name

    with engine.begin() as conn:
        _make_ineligible(conn, posting_id)
        create_application(conn, job_id=job_id, status="applied", source="test")
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert (drained.to_applied, drained.to_ineligible) == (1, 0)
    assert _folders(root / APPLIED_DIR) == [folder]
    assert _folders(root / INELIGIBLE_DIR) == []


def test_a_skipped_lead_that_is_also_ineligible_stays_in_skipped(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Same precedence rule as applied: a skip is the owner's record of a decision they made."""
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, apps, "one", body=INELIGIBLE_JD)
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name

    with engine.begin() as conn:
        _make_ineligible(conn, posting_id)
        mark_job_skipped(conn, job_id=job_id, at=NOW)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert (drained.to_skipped, drained.to_ineligible) == (1, 0)
    assert _folders(root / SKIPPED_DIR) == [folder]
    assert _folders(root / INELIGIBLE_DIR) == []


def test_the_drain_set_has_exactly_one_source_of_truth() -> None:
    """`names.DRAIN_DIRS` prices the byte budget; `queue._LOCATIONS` decides what is scanned and
    created. They must name the same drains.

    They diverged once already and it was silent: `_ineligible` was added to `queue.py` alone, so
    every planned name was priced against an 8-byte drain while an 11-byte one existed, and
    `NameBudgetError` accepted names whose drained destination it had promised to refuse. Nothing
    failed — the cap simply stopped meaning what it says. `_LOCATIONS` is now derived, and this
    pins the named constants to it so adding a fourth drain cannot repeat the trick.
    """
    assert set(queue._LOCATIONS) - {""} == set(DRAIN_DIRS)
    assert set(DRAIN_DIRS) == {
        APPLIED_DIR,
        SKIPPED_DIR,
        REPORTED_DIR,
        INELIGIBLE_DIR,
        REVIEW_DIR,
        CLOSED_DIR,
    }


def test_no_drain_directory_is_ever_reported_as_unclassified(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`unclassified` means "a folder the owner must go and look at", so a drain appearing in it is
    a false alarm that never clears.

    `_child_dirs` has to skip every drain. It skipped only two, and the bug was invisible because
    `_ineligible` did not exist until the first rejection created it — so this asserts against a
    root where all three drains exist AND one holds a real drained folder.
    """
    with engine.begin() as conn:
        posting_id, _job_id = _deliver(conn, apps, "one", body=INELIGIBLE_JD)
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        _make_ineligible(conn, posting_id)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert drained.to_ineligible == 1, "premise: a folder must actually be in the drain"

    with engine.connect() as conn:
        again = reconcile_queue(conn, root=root)
        synced = sync_queue(conn, root=root, owner_name=OWNER)
    for name in (APPLIED_DIR, SKIPPED_DIR, INELIGIBLE_DIR, REVIEW_DIR):
        assert name not in again.unclassified, f"{name} was reported as a lead folder"
    assert again.unclassified == ()
    assert synced.failed == 0


def test_wanted_location_prefers_an_owner_statement_over_a_derived_verdict() -> None:
    """The ordering inside `_wanted_location`, tested directly.

    The two integration tests above cannot both reach this: `ineligible_job_ids` never reports an
    APPLIED job, so that path is decided upstream. Calling the function with all five sets
    populated is the only way to pin the branch order, and reordering the branches fails this.
    """
    entry = queue._Entry(
        path=Path("x"), location="", posting_id=1, job_id=7, content_hash=None
    )
    both = {7: "2026-08-26"}
    verdict = {7: "ineligible"}
    review = {7}
    closed = {7}
    assert queue._wanted_location(
        entry, applied=both, skipped=both, reported=both, closed=closed,
        ineligible=verdict, review=review,
    ) == APPLIED_DIR
    assert queue._wanted_location(
        entry, applied={}, skipped=both, reported=both, closed=closed,
        ineligible=verdict, review=review,
    ) == SKIPPED_DIR
    # `reported` is an owner statement, so it outranks both derived drains AND `closed` -- but it
    # ranks below the two statements about what the owner DID with the lead. Nothing is lost by
    # that: the `queue.reported.<job_id>` marker is the record an investigation reads, and it
    # survives whichever folder holds the copy (D-427).
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported=both, closed=closed,
        ineligible=verdict, review=review,
    ) == REPORTED_DIR
    # closed ranks below BOTH owner statements and above both derived drains: the employer taking
    # the requisition down does not un-say what the owner already decided, but it does settle a
    # lead the gate could only have held for a second look.
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported={}, closed=closed,
        ineligible=verdict, review=review,
    ) == CLOSED_DIR
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported={}, closed=set(),
        ineligible=verdict, review=review,
    ) == INELIGIBLE_DIR
    # review ranks below ineligible (a lead that is both is ineligible) and above the apply queue.
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported={}, closed=set(),
        ineligible={}, review=review,
    ) == REVIEW_DIR
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported={}, closed=set(),
        ineligible={}, review=set(),
    ) == ""


def test_a_job_that_is_both_applied_and_skipped_drains_to_applied(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Skip and applied are independent dimensions (`queue_state`'s own docstring) and a job can be
    both, so the precedence is a decision rather than an accident: an application is the stronger
    claim about the employer, so it decides where the folder lives."""
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name

    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=job_id, at=NOW)
        create_application(conn, job_id=job_id, status="applied", source="test")
    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root)

    assert (report.to_applied, report.to_skipped) == (1, 0)
    assert _folders(root / APPLIED_DIR) == [folder]
    assert _folders(root / SKIPPED_DIR) == []


def test_a_skipped_lead_is_never_given_a_live_folder(
    engine: Engine, root: Path, apps: Path
) -> None:
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
        _deliver(conn, apps, "two", title="Backend Engineer")
        mark_job_skipped(conn, job_id=job_id, at=NOW)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert report.created == 1
    assert _folders(root) == ["Acme_Corp_Backend_Engineer"]


def test_sync_pulls_a_lead_back_out_of_a_drain_rather_than_making_a_second_folder(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The hazard this closes: if sync ignored the drains, an un-applied lead whose folder still
    sat in `_applied/` would get a SECOND live folder, and the owner would have two copies of one
    lead with no way to tell which is current."""
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        app_id = create_application(conn, job_id=job_id, status="applied", source="test")
    with engine.connect() as conn:
        reconcile_queue(conn, root=root)
    assert _folders(root / APPLIED_DIR) == ["Acme_Corp_Software_Engineer"]

    with engine.begin() as conn:
        set_application_status(conn, application_id=app_id, to_status="withdrawn", source="test")
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert report.moved == 1
    assert report.created == 0, "a second folder was created for a lead that already had one"
    assert _folders(root) == ["Acme_Corp_Software_Engineer"]
    assert _folders(root / APPLIED_DIR) == []


# ---------------------------------------------------------------------------- naming and collisions


def test_two_postings_with_the_same_company_and_title_each_keep_their_own_folder(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`plan_lead_names` cannot disambiguate this — it has no view of disk and returns the
    identical folder for both — so the queue must, and by the posting identity in `details.json`,
    never by parsing a name. Silently overwriting is the live defect this design exists to fix."""
    with engine.begin() as conn:
        first, _ = _deliver(conn, apps, "one")
        second, _ = _deliver(conn, apps, "two")
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.failed) == (2, 0), report.failures
    folders = _folders(root)
    assert len(folders) == 2, folders
    claimed = {}
    for name in folders:
        folder = root / name
        details = _details(folder)
        pdfs = list(folder.glob("*.pdf"))
        assert len(pdfs) == 1
        claimed[int(str(details["posting_id"]))] = pdfs[0].read_bytes()
    assert set(claimed) == {first, second}
    assert claimed[first] != claimed[second], "both folders hold the same PDF, so one was lost"


def test_two_leads_whose_names_differ_only_in_case_are_still_disambiguated(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`onX` and `OnX` are two strings and, on macOS and Windows, ONE path.

    The collision pass therefore keys on the case-FOLDED name. A case-sensitive `Counter` finds
    no collision here, disambiguates neither lead, and the second one written finds its target
    held by a folder that does not identify it — which cost run 139 two real leads.

    **The assertion is on the folded name, not on the folder count, and that is the whole point.**
    On a case-SENSITIVE filesystem the unfixed code creates two folders and reports no failure, so
    `len(folders) == 2` passes against the defect and this test would be vacuous on Linux CI —
    which is exactly where it runs. Requiring the two names to differ AFTER folding fails against
    the unfixed code on every filesystem.
    """
    with engine.begin() as conn:
        first, _ = _deliver(conn, apps, "one", company="onX", title="Full-Stack Engineer")
        second, _ = _deliver(conn, apps, "two", company="OnX", title="Full-Stack Engineer")
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.failed) == (2, 0), report.failures
    folders = _folders(root)
    assert len(folders) == 2, folders
    assert len({name.casefold() for name in folders}) == 2, (
        f"{folders} collapse to one path on a case-insensitive filesystem"
    )
    claimed = {int(str(_details(root / name)["posting_id"])) for name in folders}
    assert claimed == {first, second}


def test_a_lead_whose_canonical_job_MOVED_keeps_the_folder_it_already_has(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Identity resolution can converge a lane copy onto a native find, and then the posting a
    folder was written under is no longer the posting `delivered_unapplied` offers — it dedups by
    `job_id` and returns the most recently delivered posting of that job.

    Run 139's measured case: the folder recorded posting 131367 while the store had moved it to
    `job_id = 69007`, so the folder identified neither the offered posting nor the current job, the
    sync raised `QueueConflictError`, and the lead got no folder at all. 896 such convergences were
    measured in the Workday dereference, so this is a recurring shape, not a one-off.

    Both postings share company and title on purpose: that is what makes the planned name collide
    with the existing folder, which is what turns a stale claim into a FAILURE rather than a
    harmless second folder. Fails against a version that matches folders by `posting_id` alone.
    """
    with engine.begin() as conn:
        first, _ = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root) == ["Acme_Corp_Software_Engineer"], _folders(root)

    with engine.begin() as conn:
        # Delivered LATER, so it wins the per-job dedup, and it has no folder of its own yet.
        second, second_job = _deliver(conn, apps, "two")
        # The convergence itself: the first posting is now recognised as the second's job.
        conn.execute(update(postings).where(postings.c.id == first).values(job_id=second_job))

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert report.failed == 0, report.failures
    folders = _folders(root)
    assert len(folders) == 1, f"the existing folder was orphaned or duplicated: {folders}"
    claimed = int(str(_details(root / folders[0])["posting_id"]))
    assert claimed == second, (
        f"folder still claims posting {claimed}; it must be re-stamped to the offered posting "
        f"{second}"
    )


def test_TWO_folders_converging_on_one_job_are_consolidated_not_refused_forever(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The two-folder variant of the convergence above, and the one that shipped a permanent bug.

    The test above delivers the second posting only AFTER the first sync, so the second posting
    never has a folder of its own and the conflict cannot arise. Here BOTH postings are delivered
    and synced first, so both get folders — disambiguated by the eight-hex identity suffix,
    because they share company and title. The convergence then re-keys the loser's planned name
    onto the name the winner's folder already occupies.

    Against the version that DROPPED an ambiguous job from the by-job index, `_entry_for` returned
    the stale folder, `_relocate` refused an occupied destination, and nothing ever removed either
    folder or re-offered the losing posting — so it raised `QueueConflictError` on this sync and
    on every sync after it. Measured in production as posting 131368, in all of runs 140-144.
    """
    with engine.begin() as conn:
        first, _ = _deliver(conn, apps, "one")
        second, second_job = _deliver(conn, apps, "two")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert len(_folders(root)) == 2, _folders(root)

    with engine.begin() as conn:
        conn.execute(update(postings).where(postings.c.id == first).values(job_id=second_job))

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert report.failed == 0, report.failures
    assert report.retired == 1, f"the duplicate folder was left on disk: {_folders(root)}"
    folders = _folders(root)
    assert len(folders) == 1, f"one job must hold one folder, got: {folders}"
    assert int(str(_details(root / folders[0])["posting_id"])) == second

    # And it must STAY consolidated: a second pass has nothing left to retire and must not
    # oscillate between the two names.
    with engine.connect() as conn:
        again = sync_queue(conn, root=root, owner_name=OWNER)
    assert (again.failed, again.retired) == (0, 0), (again.failures, again.retired)
    assert _folders(root) == folders


def test_a_name_still_taken_after_disambiguation_is_REPORTED_not_returned_twice(
    tmp_path: Path,
) -> None:
    """Disambiguation is one pass, so a retried name can still collide.

    The reachable shape: two leads collide by case and both retry with an eight-hex suffix, and a
    THIRD lead whose ORDINARY title happens to carry the first one's suffix plans the identical
    folder. Before the final check, `_plan` returned two leads with the same folder and **no
    failure at all**, and the loss landed later at write time on whichever was attempted second —
    blaming the folder rather than the plan, and depending on write order for which lead survived.

    Now the lowest `posting_id` keeps the folder and the rest are reported. Asserts on `_plan`
    directly because the collision is a property of the PLAN; a two-lead test cannot reach it, and
    a database-backed one cannot easily contrive a title carrying another row's digest.
    """
    first = _queue_row(1, "Acme", "Engineer")
    second = _queue_row(2, "acme", "Engineer")
    third = _queue_row(3, "Acme", f"Engineer {_identity_hash(first)[:8]}")

    planned, failures = _plan([first, second, third], root=tmp_path, owner_name=OWNER)

    folded = [names.folder.casefold() for names in planned.values()]
    assert len(folded) == len(set(folded)), f"_plan returned a colliding folder twice: {folded}"
    assert sorted(planned) == [1, 2], sorted(planned)
    assert [failure.posting_id for failure in failures] == [3], failures
    assert "still taken after disambiguation" in failures[0].detail, failures[0].detail


def test_the_disambiguated_names_are_stable_across_syncs(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A name that churns is a folder the owner cannot keep open. The second sync must find both
    folders already correct."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
        _deliver(conn, apps, "two")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    first = _folders(root)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert (report.unchanged, report.moved, report.created, report.updated) == (2, 0, 0, 0)
    assert _folders(root) == first


def test_a_retitled_posting_moves_its_folder_instead_of_duplicating_it(
    engine: Engine, root: Path, apps: Path
) -> None:
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root) == ["Acme_Corp_Software_Engineer"]

    with engine.begin() as conn:
        conn.execute(
            update(postings).where(postings.c.id == posting_id).values(title="Platform Engineer")
        )
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert report.moved == 1
    assert _folders(root) == ["Acme_Corp_Platform_Engineer"]
    folder = root / "Acme_Corp_Platform_Engineer"
    assert (folder / "Mit_Sheth_Acme_Corp_Platform_Engineer.pdf").is_file()
    assert _details(folder)["posting_id"] == posting_id
    assert _files_under(folder) == sorted(
        [
            "Mit_Sheth_Acme_Corp_Platform_Engineer.pdf",
            queue._apply_link(APPLY_URL, queue.PLATFORM)[0],
            JD_FILE,
            DETAILS_FILE,
        ]
    ), "the old PDF name survived the move"


def test_the_identity_hash_does_not_move_when_a_lead_is_delivered_again(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Derived from the posting's own identity, never from a run id or a clock: a second delivery
    of the same lead by a later run must not rename the folder."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    first = _details(_sole_folder(root))["identity_hash"]

    with engine.begin() as conn:
        version_id = int(
            conn.execute(
                insert(posting_versions).values(
                    posting_id=posting_id, content_hash="v-one-b", body_text=JD,
                    captured_at=NOW + timedelta(hours=2), run_id=None, capture_reason="revised",
                )
            ).inserted_primary_key[0]
        )
        run_id = int(
            conn.execute(
                insert(runs).values(started_at=NOW + timedelta(hours=2), boards_attempted=1)
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(artifacts).values(
                posting_version_id=version_id, kind="resume_tailored",
                uri=str(apps / "2026-08-27" / "one" / "tailored-one.typ"),
                generator="boardwatch.tailor", media_type="text/x-typst",
                meta_json={"pdf_uri": str(apps / "2026-08-26" / "one" / "tailored-one.pdf")},
                created_at=NOW + timedelta(hours=2), run_id=run_id,
            )
        )
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert report.moved == 0
    assert _details(_sole_folder(root))["identity_hash"] == first


# -------------------------------------------------------------------------- crashes and isolation


def test_a_crash_inside_the_staging_build_leaves_no_visible_folder(
    engine: Engine, root: Path, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of staging. `details.json` is written last, so failing there is exactly the
    half-written folder the review page must never list as a lead."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one")

    def boom(built: Path, payload: object) -> None:
        raise OSError("simulated crash after the PDF was copied")

    monkeypatch.setattr(queue, "_write_details", boom)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    monkeypatch.undo()

    assert report.failed == 1
    assert report.failures[0].posting_id == posting_id
    assert (report.created, report.updated, report.unchanged) == (0, 0, 0)
    assert _folders(root) == []
    assert list(root.glob(".staging-*")) == [], "a staging directory outlived the sync"
    assert _files_under(root) == [], "a partial file is visible under the queue root"


def test_a_crash_does_not_damage_the_folder_it_was_replacing(
    engine: Engine, root: Path, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An update that fails must leave the previous folder intact, not a hole where it was."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    before = _snapshot(root)
    (apps / "2026-08-26" / "one" / "tailored-one.pdf").write_bytes(b"%PDF-1.7\nnew\n%%EOF\n")

    def boom(built: Path, payload: object) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(queue, "_write_details", boom)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    monkeypatch.undo()

    assert report.failed == 1
    assert _snapshot(root) == before


def test_one_failing_lead_does_not_stop_the_other_three(
    engine: Engine, root: Path, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#168's lesson, applied here: one board's failure once aborted a whole scan."""
    titles = ["Software Engineer", "Backend Engineer", "Platform Engineer", "Data Engineer"]
    with engine.begin() as conn:
        ids = [_deliver(conn, apps, f"k{i}", title=title)[0] for i, title in enumerate(titles)]
    doomed = ids[2]
    real = queue._write_lead

    def flaky(built: Path, payload: queue._Payload) -> None:
        if payload.details["posting_id"] == doomed:
            raise OSError("simulated per-lead failure")
        real(built, payload)

    monkeypatch.setattr(queue, "_write_lead", flaky)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    monkeypatch.undo()

    assert report.created == 3
    assert report.failed == 1
    assert [failure.posting_id for failure in report.failures] == [doomed]
    assert len(_folders(root)) == 3
    survivors = {int(str(_details(root / name)["posting_id"])) for name in _folders(root)}
    assert survivors == set(ids) - {doomed}
    # Each survivor is whole, not a shell.
    for name in _folders(root):
        assert len(_files_under(root / name)) == 4


def test_stale_staging_directories_are_cleared_by_the_next_sync(
    engine: Engine, root: Path, apps: Path
) -> None:
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    stale = root / ".staging-deadbeef"
    stale.mkdir(parents=True)
    (stale / "half-written.pdf").write_bytes(b"junk")

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert not stale.exists()
    assert report.created == 1
    # And it was never mistaken for a lead on the way out.
    assert _folders(root) == ["Acme_Corp_Software_Engineer"]


# -------------------------------------------------------------------------------------- reconcile


def test_reconcile_reports_a_folder_it_cannot_classify_and_leaves_it_alone(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Nothing is ever guessed at from a folder name, and nothing unclassifiable is deleted."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    mystery = root / "Something_The_Owner_Made"
    mystery.mkdir()
    (mystery / "notes.txt").write_text("mine\n", encoding="utf-8")
    broken = root / "Broken_Details"
    broken.mkdir()
    (broken / DETAILS_FILE).write_text("{not json", encoding="utf-8")

    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root)

    assert sorted(report.unclassified) == ["Broken_Details", "Something_The_Owner_Made"]
    assert report.moved == 0
    assert (mystery / "notes.txt").read_text(encoding="utf-8") == "mine\n"
    assert (broken / DETAILS_FILE).is_file()


def test_reconcile_refuses_an_occupied_destination_instead_of_merging_into_it(
    engine: Engine, root: Path, apps: Path
) -> None:
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name
    squatter = root / APPLIED_DIR / folder
    squatter.mkdir(parents=True)
    (squatter / "keep-me.txt").write_text("older copy\n", encoding="utf-8")

    with engine.begin() as conn:
        create_application(conn, job_id=job_id, status="applied", source="test")
    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root)

    assert report.to_applied == 0
    assert [failure.folder for failure in report.failures] == [folder]
    assert (squatter / "keep-me.txt").read_text(encoding="utf-8") == "older copy\n"
    assert _folders(root) == [folder], "the source folder was lost to a refused move"


def test_reconcile_ignores_a_lead_that_is_already_where_it_belongs(
    engine: Engine, root: Path, apps: Path
) -> None:
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
        report = reconcile_queue(conn, root=root)
    assert (report.moved, report.failed, report.unclassified) == (0, 0, ())


# ------------------------------------------------------------------------------------ the lock


def test_sync_reports_lock_contention_rather_than_waiting_for_it(
    engine: Engine, root: Path, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-blocking is contractual: a second holder must be told, not queued. The reclaim window
    is pinned to zero so this measures the refusal and not the platform's window."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(queue, "RECLAIM_WINDOW_SECONDS", 0.0)
    holder = FileLock(str(root / LOCK_FILE))
    holder.acquire(blocking=False)
    try:
        started = time.monotonic()
        with engine.connect() as conn:
            sync = sync_queue(conn, root=root, owner_name=OWNER)
            recon = reconcile_queue(conn, root=root)
        elapsed = time.monotonic() - started
    finally:
        holder.release()
    monkeypatch.undo()

    assert sync.contended is True
    assert (sync.created, sync.updated, sync.unchanged, sync.moved, sync.failed) == (0, 0, 0, 0, 0)
    assert recon.contended is True
    assert elapsed < 2.0, "the acquire queued instead of reporting"
    assert _folders(root) == [], "a contended sync wrote anyway"


def test_the_reclaim_window_is_bound_in_this_module_and_is_honoured(
    engine: Engine, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`core/lock_reclaim.py` says consumers bind the window by name and a test must patch the
    consumer it exercises. So: patch THIS module's binding and prove the acquire re-asks for that
    long before believing the refusal — a decorative import would refuse instantly."""
    assert queue.RECLAIM_WINDOW_SECONDS == lock_reclaim.RECLAIM_WINDOW_SECONDS
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(queue, "RECLAIM_WINDOW_SECONDS", 0.25)
    holder = FileLock(str(root / LOCK_FILE))
    holder.acquire(blocking=False)
    try:
        started = time.monotonic()
        with engine.connect() as conn:
            report = reconcile_queue(conn, root=root)
        elapsed = time.monotonic() - started
    finally:
        holder.release()
    monkeypatch.undo()

    assert report.contended is True
    assert elapsed >= 0.2, f"the window was not waited out: {elapsed:.3f}s"


def test_the_lock_is_released_so_a_second_sync_can_run(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A lock held past the critical section would show up as every later call reporting
    contention, which is the failure mode a `finally` exists to prevent."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        first = sync_queue(conn, root=root, owner_name=OWNER)
        second = sync_queue(conn, root=root, owner_name=OWNER)
        third = reconcile_queue(conn, root=root)
    assert (first.contended, second.contended, third.contended) == (False, False, False)
    assert (first.created, second.unchanged) == (1, 1)


# ---------------------------------------------------------------------------------- housekeeping


def test_sync_creates_every_drain_and_the_lockfile_and_nothing_else(
    engine: Engine, root: Path
) -> None:
    """An empty database is not an error, and the queue is still a well-formed root afterwards."""
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert (report.created, report.failed, report.contended) == (0, 0, False)
    assert (root / APPLIED_DIR).is_dir()
    assert (root / SKIPPED_DIR).is_dir()
    # Created up front, not lazily on the first rejection. A drain that springs into existence
    # only once a folder lands in it is invisible to every test whose root never produces one,
    # which is what let `_child_dirs` ship without knowing `_ineligible` existed.
    assert (root / INELIGIBLE_DIR).is_dir()
    assert (root / REVIEW_DIR).is_dir()
    assert (root / CLOSED_DIR).is_dir()
    assert (root / REPORTED_DIR).is_dir()
    assert _folders(root) == []
    assert sorted(path.name for path in root.iterdir() if path.is_dir()) == sorted(
        [APPLIED_DIR, SKIPPED_DIR, INELIGIBLE_DIR, REVIEW_DIR, CLOSED_DIR, REPORTED_DIR]
    )
    # The lockfile is excluded rather than asserted either way: `filelock`'s POSIX release unlinks
    # it, and `profile_bundle/locking.py` is explicit that its presence is not a signal.
    assert [name for name in _files_under(root) if name != LOCK_FILE] == []


def test_failed_is_derived_from_failures_so_the_two_cannot_disagree() -> None:
    report = queue.SyncReport(failures=(queue.LeadFailure(posting_id=7, detail="x"),))
    assert report.failed == 1
    # EVERY drain is set, and each contributes a distinct value, so a `moved` that forgets one
    # cannot land on the right total by accident. Omitting `to_ineligible` here is exactly how the
    # first version of this change shipped a `moved` that printed 0 while 294 folders moved.
    #
    # `to_closed` and `to_reported` were absent from this literal for a while and the comment above
    # still claimed "EVERY drain" — a stale claim rather than a hole, since each is covered by its
    # own end-to-end drain test, but a reader trusting it believed this guarded fields it did not.
    recon = queue.ReconcileReport(
        to_applied=1, to_skipped=2, to_reported=4, to_ineligible=8, to_review=16,
        to_closed=32, to_queue=64,
    )
    assert recon.moved == 127
    assert recon.failed == 0


# ---------------------------------------------------------------------- refusing to overwrite


def test_sync_refuses_a_target_occupied_by_a_folder_that_is_not_the_lead(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The worst possible outcome inside the queue would be silently overwriting a folder, since
    that is the live defect this whole design exists to fix. A folder that cannot identify itself
    is left exactly as it is and the lead is reported failed."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one")
    squatter = root / "Acme_Corp_Software_Engineer"
    squatter.mkdir(parents=True)
    (squatter / "the-owners-own-notes.txt").write_text("do not delete\n", encoding="utf-8")

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.updated, report.failed) == (0, 0, 1)
    assert report.failures[0].posting_id == posting_id
    assert "QueueConflictError" in report.failures[0].detail
    assert _files_under(squatter) == ["the-owners-own-notes.txt"]
    assert (squatter / "the-owners-own-notes.txt").read_text(encoding="utf-8") == "do not delete\n"


def test_two_folders_claiming_one_posting_are_both_reported_and_neither_is_used(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Picking one would silently orphan the other's contents, and only the owner can say which is
    real — so the claim is withdrawn from both and nothing is moved or overwritten."""
    import shutil as _shutil

    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    original = _sole_folder(root)
    twin = root / "A_Copy_The_Owner_Made"
    _shutil.copytree(original, twin)

    with engine.begin() as conn:
        create_application(conn, job_id=job_id, status="applied", source="test")
    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root)

    assert report.moved == 0
    assert sorted(report.unclassified) == ["A_Copy_The_Owner_Made", original.name]
    assert sorted(_folders(root)) == sorted([twin.name, original.name])
    assert _folders(root / APPLIED_DIR) == []


def test_a_root_too_long_to_name_fails_each_lead_and_never_raises(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`plan_lead_names` raises `NameBudgetError` before anything is created when no name can fit
    the destination cap. One pathological root must be reported per lead, not thrown at the run
    hook, which swallows every exception and would record the sync as merely absent."""
    with engine.begin() as conn:
        first, _ = _deliver(conn, apps, "one")
        second, _ = _deliver(conn, apps, "two", title="Backend Engineer")
    long_root = root / ("q" * 120) / ("u" * 120)

    with engine.connect() as conn:
        report = sync_queue(conn, root=long_root, owner_name=OWNER)

    assert (report.created, report.updated, report.unchanged, report.moved) == (0, 0, 0, 0)
    assert report.failed == 2
    assert sorted(failure.posting_id for failure in report.failures) == sorted([first, second])
    assert all("NameBudgetError" in failure.detail for failure in report.failures)
    assert _folders(long_root) == []


def test_a_failure_report_names_the_error_without_pasting_a_path(
    engine: Engine, root: Path, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`profile_bundle/locking.py`'s rule, applied here: an `OSError`'s stringified form embeds the
    offending absolute path, and a report the owner copies out of a terminal would carry their home
    directory with it. The lead is already identified by its posting id."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")

    def boom(built: Path, payload: object) -> None:
        raise OSError(28, "No space left on device", str(built / DETAILS_FILE))

    monkeypatch.setattr(queue, "_write_details", boom)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    monkeypatch.undo()

    assert report.failed == 1
    detail = report.failures[0].detail
    assert detail == "OSError: No space left on device"
    assert str(root) not in detail
    assert DETAILS_FILE not in detail


# --------------------------------------------------------- the apply / review split (verified-uncertain)


def test_a_us_software_lead_lands_in_the_apply_queue(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The verified-uncertain lead — US location, software title — is blindly-appliable."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one", title="Software Engineer", locations=("Boston, MA",))
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert report.created == 1
    assert _folders(root) == ["Acme_Corp_Software_Engineer"]
    assert _folders(root / REVIEW_DIR) == []


def test_a_foreign_location_lead_is_born_in_the_review_lane(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A lead whose location is not positively US is held for review — the Kaunas/Zhubei class that
    fails open at the hard US gate. It is CREATED directly in `_review`, not excluded."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one", title="Software Engineer", locations=("Kaunas, Lithuania",))
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert report.created == 1
    assert _folders(root) == []
    assert _folders(root / REVIEW_DIR) == ["Acme_Corp_Software_Engineer"]


def test_a_non_software_lead_is_born_in_the_review_lane(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A lead whose title carries no software signal is held for review — the Front-Office-Agent /
    Field-Auto-Appraiser class that fails open at the role gate as `uncertain`."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one", title="Front Office Agent")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root) == []
    assert len(_folders(root / REVIEW_DIR)) == 1


def test_reconcile_moves_a_lead_into_review_when_it_stops_being_software(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A lead already in the apply queue is drawn into review when its class changes, counted in
    `to_review`, and NOT rebuilt at the top level by the sync that follows."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one", title="Software Engineer")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert len(_folders(root)) == 1

    with engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == posting_id)
            .values(title="Front Office Agent", normalized_title="front office agent")
        )
    with engine.connect() as conn:
        recon = reconcile_queue(conn, root=root)
    assert recon.to_review == 1
    assert _folders(root) == []
    assert len(_folders(root / REVIEW_DIR)) == 1

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root) == [], "sync rebuilt a top-level folder for a review lead"
    assert len(_folders(root / REVIEW_DIR)) == 1
    assert report.created == 0


def _set_status(conn: Connection, posting_id: int, status: str) -> None:
    conn.execute(update(postings).where(postings.c.id == posting_id).values(status=status))


@pytest.mark.parametrize(
    ("status", "watched", "expected_lane"),
    [
        ("closed", True, CLOSED_DIR),
        ("open", True, ""),
        # `watched=False` is what makes `_status` render `unverifiable` (D-324): the posting is
        # open, but nothing enumerates its board. THIS is the arm that fails against a drain
        # keyed on `!= "open"`, which is the mutation the other two arms cannot see.
        ("open", False, ""),
    ],
    ids=["closed-drains", "open-stays", "unverifiable-stays"],
)
def test_only_a_closed_posting_drains_to_the_closed_lane(
    engine: Engine, root: Path, apps: Path, status: str, watched: bool, expected_lane: str
) -> None:
    """The three rendered statuses, one test, because any single arm passes vacuously.

    An arm asserting only that `closed` drains is satisfied by a drain that sweeps everything;
    an arm asserting only that `open` stays is satisfied by a drain that fires never. The
    `unverifiable` arm is the one that pins the fail-open direction a liveness judge is owed.
    """
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one", title="Software Engineer", watched=watched)
        _set_status(conn, posting_id, status)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert report.created == 1
    assert _folders(root / expected_lane if expected_lane else root) == [
        "Acme_Corp_Software_Engineer"
    ]
    if expected_lane != CLOSED_DIR:
        assert _folders(root / CLOSED_DIR) == []


def test_reconcile_drains_a_lead_to_closed_when_its_posting_closes(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The half that matters for a queue nobody has re-synced: a lead delivered while the
    requisition was live is drawn out when it comes down, counted in `to_closed`, and NOT rebuilt
    at the top level by the sync that follows."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one", title="Software Engineer")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert len(_folders(root)) == 1

    with engine.begin() as conn:
        _set_status(conn, posting_id, "closed")
    with engine.connect() as conn:
        recon = reconcile_queue(conn, root=root)
    assert recon.to_closed == 1
    assert recon.moved == 1, "`moved` omits the new drain, so the run line reports 0"
    assert _folders(root) == []
    assert _folders(root / CLOSED_DIR) == ["Acme_Corp_Software_Engineer"]

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root) == [], "sync rebuilt a top-level folder for a closed lead"
    assert report.created == 0


def test_a_closed_lead_returns_to_the_apply_queue_when_its_posting_reopens(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The drain runs on BOTH sides of the gate. A quarantine with no re-entry path is a leak, and
    a reopened requisition is exactly the case that proves this one has a drain rather than a
    one-way trapdoor."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one", title="Software Engineer")
        _set_status(conn, posting_id, "closed")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root / CLOSED_DIR) == ["Acme_Corp_Software_Engineer"]

    with engine.begin() as conn:
        _set_status(conn, posting_id, "open")
    with engine.connect() as conn:
        recon = reconcile_queue(conn, root=root)
        sync_queue(conn, root=root, owner_name=OWNER)
    assert recon.to_queue == 1
    assert _folders(root) == ["Acme_Corp_Software_Engineer"]
    assert _folders(root / CLOSED_DIR) == []


def test_a_jobs_live_posting_is_offered_even_when_a_closed_sibling_was_delivered_later(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The measured lost delivery (D-432), asserted through the disk path rather than the query.

    eBay job 35249 held an open Workday requisition delivered at run 73 and a dead lane copy of
    the same job delivered at run 137. `delivered_unapplied` offered a job's MOST RECENTLY
    delivered posting, so the dead copy decided the job and a live requisition was filed under
    `_closed`, which nothing ever offers again.

    Asserted here as well as in `test_delivery_queries` because `closed_job_ids` reporting on
    itself is a component's self-report; the folder on disk is a different path to the same claim.
    The two postings carry different titles so the folder NAME says which one was offered.

    The second phase is the control. Without it, `_folders(root / CLOSED_DIR) == []` is satisfied
    by a sync that never files anything as closed at all.
    """
    with engine.begin() as conn:
        live, job = _deliver(
            conn, apps, "live", title="Software Engineer",
            delivered_at=NOW - timedelta(days=2),
        )
        dead, _ = _deliver(
            conn, apps, "dead", job_id=job, title="Software Engineer II", delivered_at=NOW
        )
        _set_status(conn, dead, "closed")
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert report.created == 1
    assert _folders(root) == ["Acme_Corp_Software_Engineer"]
    assert _folders(root / CLOSED_DIR) == []

    # Control: with NO live posting left on the job, the drain still fires.
    with engine.begin() as conn:
        _set_status(conn, live, "closed")
    with engine.connect() as conn:
        recon = reconcile_queue(conn, root=root)
    assert recon.to_closed == 1
    assert _folders(root) == []
    assert _folders(root / CLOSED_DIR) == ["Acme_Corp_Software_Engineer"]


def test_a_lead_already_buried_in_closed_walks_out_on_the_next_run_by_itself(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The repair path, which is the whole user-visible payoff of D-432 and had no pin.

    The live store holds ONE folder already filed this way — eBay job 35249, sitting in `_closed`
    under a dead lane copy while its Workday requisition is open. D-432 claims it comes back out
    on the next run with nothing to run by hand, on the grounds that `reconcile_queue` runs BEFORE
    `sync_queue`, `_index` scans `_closed`, and `_entry_for` falls back to the by-job index. That
    was a claim read off the code; this asserts it.

    The starting state is built the way the store reached it: the dead posting is delivered and
    synced ALONE, so the folder is genuinely stamped for it and genuinely in `_closed`. The live
    sibling is only then given its EARLIER delivery, which is what run 73 was.

    `created == 0` is the load-bearing half. Without the by-job fallback the changed winner would
    find no folder for its own posting id and mint a SECOND one — leaving the first orphaned in
    `_closed`, which is the two-folder state D-430's conflict was made of.
    """
    with engine.begin() as conn:
        dead, job = _deliver(conn, apps, "dead", title="Software Engineer II", delivered_at=NOW)
        _set_status(conn, dead, "closed")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root / CLOSED_DIR) == ["Acme_Corp_Software_Engineer_II"]
    assert _folders(root) == []

    # The live sibling, delivered EARLIER — exactly the shape that buried job 35249.
    with engine.begin() as conn:
        _deliver(
            conn, apps, "live", job_id=job, title="Software Engineer",
            delivered_at=NOW - timedelta(days=2),
        )
    with engine.connect() as conn:
        recon = reconcile_queue(conn, root=root)
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert recon.to_queue == 1
    assert _folders(root / CLOSED_DIR) == []
    assert _folders(root) == ["Acme_Corp_Software_Engineer"]
    assert report.created == 0, "a second folder was minted instead of re-stamping the first"


def test_closed_outranks_the_derived_drains_but_never_an_owner_statement(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Precedence, at both of its boundaries.

    A closed lead that is ALSO non-software goes to `_closed`, not `_review`: asking the owner to
    read a job that no longer exists is the cost this drain removes. But a lead the owner SKIPPED
    stays in `_skipped` when the requisition comes down — a skip is a statement about what they
    decided, and it does not stop being true.

    `_skipped` is the owner statement asserted here rather than `_applied`, and the choice is
    forced rather than stylistic: `closed_job_ids` is built from `delivered_unapplied`, which
    excludes applied leads unconditionally, so an applied lead can never enter the closed set and
    the closed-vs-applied ordering is unobservable by construction. `skipped=set()` keeps skipped
    leads IN, so that boundary is real and a reordering there is a live defect.
    """
    with engine.begin() as conn:
        review_id, _ = _deliver(conn, apps, "one", title="Front Office Agent")
        _set_status(conn, review_id, "closed")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root / CLOSED_DIR) == ["Acme_Corp_Front_Office_Agent"]
    assert _folders(root / REVIEW_DIR) == []

    with engine.begin() as conn:
        skipped_id, skipped_job = _deliver(conn, apps, "two", title="Software Engineer")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root) == ["Acme_Corp_Software_Engineer"]
    with engine.begin() as conn:
        _set_status(conn, skipped_id, "closed")
        mark_job_skipped(conn, job_id=skipped_job, at=NOW)
    with engine.connect() as conn:
        reconcile_queue(conn, root=root)
    assert _folders(root / SKIPPED_DIR) == ["Acme_Corp_Software_Engineer"]
    assert _folders(root / CLOSED_DIR) == ["Acme_Corp_Front_Office_Agent"]


def test_a_review_lead_returns_to_the_apply_queue_when_it_becomes_software(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The split self-heals in both directions: a review lead re-promotes once it is US + software."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one", title="Front Office Agent")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    assert len(_folders(root / REVIEW_DIR)) == 1

    with engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == posting_id)
            .values(title="Software Engineer", normalized_title="software engineer")
        )
    with engine.connect() as conn:
        reconcile_queue(conn, root=root)
        sync_queue(conn, root=root, owner_name=OWNER)
    assert len(_folders(root)) == 1
    assert _folders(root / REVIEW_DIR) == []
