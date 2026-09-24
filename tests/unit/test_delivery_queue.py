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
import io
import json
import plistlib
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest
from filelock import FileLock
from rich.console import Console
from sqlalchemy import Connection, Engine, event, insert, select, update

from boardwatch.core import lock_reclaim
from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION
from boardwatch.core.politeness import FetchFailure
from boardwatch.core.settings import load_settings
from boardwatch.delivery import DRAIN_DIRS, plan_lead_names, queue
from boardwatch.delivery.api import ApiContext
from boardwatch.delivery.form_questions import FormQuestionSweep, sweep_form_questions
from boardwatch.delivery.queue import (
    APPLIED_DIR,
    CLOSED_DIR,
    DETAILS_FILE,
    INELIGIBLE_DIR,
    JD_FILE,
    LANE_COPY_DIR,
    LINK_FILE,
    LOCK_FILE,
    REPORTED_DIR,
    REVIEW_DIR,
    SKIPPED_DIR,
    URL_FILE,
    WEBLOC_FILE,
    ReconcileReport,
    _identity_hash,
    _plan,
    reconcile_queue,
    sync_queue,
)
from boardwatch.delivery.review_gate import LaneDecision, ReviewReason
from boardwatch.delivery.server import prime_queue
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.engine import evaluate, write_evaluation
from boardwatch.eligibility.facts import Facts, Policy, WorkAuthFact, facts_payload
from boardwatch.eligibility.hashing import build_identity
from boardwatch.eligibility.resolve import declared_fields
from boardwatch.pipeline import runner as runner_mod
from boardwatch.store.applications import (
    applied_job_ids,
    create_application,
    mark_job_applied,
    set_application_status,
)
from boardwatch.store.db import ensure_schema, get_engine, get_readonly_engine
from boardwatch.store.delivery_queries import (
    QueueDetail,
    QueueRow,
    delivered_unapplied,
    lane_decision,
)
from boardwatch.store.form_question_queries import cached_form_questions
from boardwatch.store.quarantine_queries import record_quarantine
from boardwatch.store.queries import (
    current_posting_versions,
    insert_run,
    save_eligibility,
    save_profile,
)
from boardwatch.store.queue_state import (
    mark_job_reported,
    mark_job_skipped,
    skipped_job_ids,
    unmark_job_reported,
    unmark_job_skipped,
)
from boardwatch.store.tables import (
    artifacts,
    board_scans,
    companies,
    jobs,
    posting_identities,
    posting_versions,
    postings,
    quarantined_bodies,
    runs,
)
from tests.conftest import write_bundled_role_taxonomy

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


#: The facts `_deliver` stores, and the reason they are not the empty `Facts()`: a work-auth rule
#: with nothing to resolve against ABSTAINS (`unknown`), which sets `eligibility_unconfirmed` and
#: holds the lead for review. Resolved US authorization makes the same rule report `met`, so every
#: seeded body — `INELIGIBLE_JD` included — reaches the APPLY queue, which is where the drain
#: tests below need the lead to start before `_make_ineligible` turns its verdict.
FACTS = Facts(
    work_authorization=WorkAuthFact(
        status="citizen", jurisdiction="us", needs_sponsorship=False
    )
)
#: The bundled default policy. `_make_ineligible` stores DIFFERENT facts (needs_sponsorship) with
#: `work_auth: blocker`, which is a different identity — that is how a lead's verdict turns
#: mid-test, and why nothing else may depend on this identity surviving that call.
POLICY = Policy()


def _judge_version(conn: Connection, version_id: int, body: str) -> None:
    """Evaluate one frozen version under the identity `_save_identity` stores.

    A revision is a new evaluation subject: `current_verdicts` keys on the CURRENT version, so a
    version inserted without one leaves the lead with NO verdict, which since A3 routes it to
    `_review`. Production writes the evaluation alongside the revision; these fixtures do too.
    """
    catalog = load_rules(load_settings().config_dir)
    write_evaluation(
        conn,
        posting_version_id=version_id,
        identity=build_identity(
            posting_version_id=version_id, facts=FACTS, policy=POLICY,
            catalog=catalog, declared_fields=declared_fields(),
        ),
        result=evaluate(body, FACTS, POLICY, catalog),
    )


def _save_identity(conn: Connection) -> None:
    """The stored profile + eligibility `current_identity` recomputes the read's identity from.

    Written by content, so calling it once per delivered lead stores the same hashes every time.
    """
    save_profile(
        conn, text="resume", target_titles=["software engineer"], exclude_titles=[],
        locations=["Boston, MA"], remote_only=False, skills=["python"],
        taxonomy_version="v1", resume_max_pages=1, target_countries=["USA"],
    )
    save_eligibility(
        conn, facts_json=facts_payload(FACTS), policy_json=POLICY.model_dump(mode="json")
    )


@pytest.fixture(autouse=True)
def _scratch_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))
    # A software user (T184b): the lane reads the role gate from the user's taxonomy.
    write_bundled_role_taxonomy(tmp_path / "config")


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
        provider="greenhouse",
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
        role="in_field",
    )


def _plant_folder(
    root: Path,
    location: str,
    name: str,
    *,
    posting_id: int,
    job_id: int,
    company: str = "Acme Corp",
    title: str = "Backend Engineer",
    identity_hash: str = "aaaaaaaa",
) -> Path:
    """A queue folder written straight to disk, bypassing `sync_queue`, so its exact on-disk name
    and job/posting identity can be forced independently of what `plan_lead_names` would itself
    choose for it. T172's shape is two REAL jobs whose planned names collide, which `_plan`'s
    in-pass disambiguation prevents whenever both are offered to it together — reaching the
    collision needs one of the two already parked in a drain, which needs full control over what
    is on disk rather than what one `sync_queue` pass would produce.

    Written with only the fields `_index` and `_widen_for_a_different_job` read; an ordinary
    `sync_queue` folder carries more, and nothing here reads any of the rest back.
    """
    folder = (root / location / name) if location else root / name
    folder.mkdir(parents=True)
    (folder / DETAILS_FILE).write_text(
        json.dumps(
            {
                "posting_id": posting_id,
                "job_id": job_id,
                "content_hash": f"hash-{posting_id}",
                "company": company,
                "title": title,
                "identity_hash": identity_hash,
            }
        ),
        encoding="utf-8",
    )
    (folder / "marker.txt").write_text(f"lead-{posting_id}\n", encoding="utf-8")
    return folder


def _complete_scan(conn: Connection, company_id: int, run_id: int) -> None:
    """The `board_scans` row that makes a watched board ENUMERATED rather than merely configured.

    Without one, `delivery_queries._status` renders every open posting `unverifiable` (T122):
    absence closure needs a `complete` snapshot, so a board that has never produced one can no
    more retire a posting than an unwatched board can.
    """
    conn.execute(
        insert(board_scans).values(
            run_id=run_id, company_id=company_id, started_at=NOW, finished_at=NOW,
            status="complete", postings_listed=1,
        )
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
    provider: str = "greenhouse",
) -> tuple[int, int]:
    """One delivered lead: company, job, posting, frozen version, tailored artifact, disk folder.

    Returns `(posting_id, job_id)`. `pdf=False` writes no PDF on disk; `pdf_uri=None` records an
    artifact whose `meta_json` names no PDF at all. The two are different absences.

    It is EVALUATED, which is the production shape and is what puts it in the APPLY lane: a
    delivered posting has been through the eligibility gate, and since A3 a lead with no current
    evaluation routes to `_review` — nothing cleared it, so it is not blindly appliable. These
    fixtures used to store no profile at all, which made every verdict `None` and every lead
    appliable by default; the folder-tree behaviour they assert is the apply lane's, so the
    fixture now says so out loud.
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
                provider=provider,
                slug=f"slug-{key}",
                source="user",
                watched=watched,
                tags_json=None,
            )
        ).inserted_primary_key[0]
    )
    _complete_scan(conn, company_id, run_id)
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
    _save_identity(conn)
    _judge_version(conn, version_id, body)
    return posting_id, job


def _quarantine_version(
    conn: Connection,
    posting_id: int,
    *,
    version_id: int | None = None,
    reopened_at: datetime | None = None,
) -> int:
    if version_id is None:
        version_id = int(
            conn.execute(
                select(posting_versions.c.id)
                .where(posting_versions.c.posting_id == posting_id)
                .order_by(posting_versions.c.id.desc())
                .limit(1)
            ).scalar_one()
        )
    record_quarantine(
        conn,
        posting_version_id=version_id,
        posting_id=posting_id,
        markers=("apply on employer site", "sign in join now"),
        now=NOW,
    )
    if reopened_at is not None:
        conn.execute(
            update(quarantined_bodies)
            .where(quarantined_bodies.c.posting_version_id == version_id)
            .values(reopened_at=reopened_at)
        )
    return version_id


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
    assert second.repaired == 0, "an untouched destination repairs nothing"
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
        revised_version = int(
            conn.execute(
                insert(posting_versions).values(
                    posting_id=posting_id,
                    content_hash="v-one-revised",
                    body_text=revised,
                    captured_at=NOW + timedelta(hours=1),
                    run_id=None,
                    capture_reason="revised",
                )
            ).inserted_primary_key[0]
        )
        _judge_version(conn, revised_version, revised)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.updated, report.unchanged) == (0, 1, 0)
    # Control for T120: a GENUINE content change is `updated` and must NOT be `repaired`.
    assert report.repaired == 0
    folder = _sole_folder(root)
    assert (folder / JD_FILE).read_text(encoding="utf-8") == revised
    assert _snapshot(root) != before


def test_an_ordinary_update_keeps_the_owners_own_files(
    engine: Engine, root: Path, apps: Path
) -> None:
    """T121. `_install` swaps the whole directory, which took the owner's work with it.

    `_repair` goes file-by-file precisely to protect a hand-written cover letter and its `.tex`
    source, and `_destination_intact` refuses to call an unrecognised file an integrity failure.
    Both had already decided the folder is partly the owner's. The ordinary `updated` path had
    not, so every genuine content change silently deleted work boardwatch cannot regenerate.
    """
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)

    folder = _sole_folder(root)
    letter = folder / "cover-letter.tex"
    letter.write_text("\\documentclass{article} % mine, not boardwatch's\n", encoding="utf-8")
    notes = folder / "notes"
    notes.mkdir()
    (notes / "call.md").write_text("recruiter call 3pm\n", encoding="utf-8")

    revised = JD + " Updated: now also requires Rust."
    with engine.begin() as conn:
        revised_version = int(
            conn.execute(
                insert(posting_versions).values(
                    posting_id=posting_id,
                    content_hash="v-one-revised",
                    body_text=revised,
                    captured_at=NOW + timedelta(hours=1),
                    run_id=None,
                    capture_reason="revised",
                )
            ).inserted_primary_key[0]
        )
        _judge_version(conn, revised_version, revised)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 1, 0, 0)
    # The owner's work survives -- a file AND a directory, since the swap took both.
    assert letter.read_text(encoding="utf-8").endswith("% mine, not boardwatch's\n")
    assert (notes / "call.md").read_text(encoding="utf-8") == "recruiter call 3pm\n"
    # Control: carrying the old files over must NOT resurrect the superseded JD. Without this the
    # test would pass against an implementation that simply skipped the update.
    assert (folder / JD_FILE).read_text(encoding="utf-8") == revised


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


# ------------------------------------------------- destination integrity (the tamper population)
#
# Every test below damages a file the sync itself wrote, leaving `details.json`'s recorded
# `content_hash` exactly as it was. That hash is what the fast path consults, so a matching hash
# must not be allowed to make any of them pass: each asserts the destination's ACTUAL bytes
# against the store or the source file, and re-reads the recorded hash afterwards to show it
# never moved.


PDF_NAME = "Mit_Sheth_Acme_Corp_Software_Engineer.pdf"


def _synced_lead(engine: Engine, root: Path, apps: Path) -> Path:
    """One delivered lead, synced once: the folder the tamper tests damage."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    return _sole_folder(root)


def _resync(engine: Engine, root: Path) -> queue.SyncReport:
    with engine.connect() as conn:
        return sync_queue(conn, root=root, owner_name=OWNER)


def test_a_tampered_destination_jd_is_rewritten_from_the_store(
    engine: Engine, root: Path, apps: Path
) -> None:
    folder = _synced_lead(engine, root, apps)
    recorded = _details(folder)["content_hash"]
    (folder / JD_FILE).write_text("TAMPERED\n", encoding="utf-8")

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 1, 0, 0)
    assert report.repaired == 1, "a rewritten-from-store lead is a REPAIR, not an edit"
    assert (folder / JD_FILE).read_text(encoding="utf-8") == JD
    assert _details(folder)["content_hash"] == recorded


def test_a_deleted_destination_jd_is_written_again(
    engine: Engine, root: Path, apps: Path
) -> None:
    folder = _synced_lead(engine, root, apps)
    recorded = _details(folder)["content_hash"]
    (folder / JD_FILE).unlink()

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 1, 0, 0)
    assert report.repaired == 1, "a rewritten-from-store lead is a REPAIR, not an edit"
    assert (folder / JD_FILE).read_text(encoding="utf-8") == JD
    assert _details(folder)["content_hash"] == recorded


def test_a_tampered_destination_apply_link_is_rewritten(
    engine: Engine, root: Path, apps: Path
) -> None:
    folder = _synced_lead(engine, root, apps)
    link_name = queue._apply_link(APPLY_URL, queue.PLATFORM)[0]
    (folder / link_name).write_bytes(b"https://phishing.test/\n")

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 1, 0, 0)
    assert _link_url(folder) == APPLY_URL


def test_a_deleted_destination_apply_link_is_written_again(
    engine: Engine, root: Path, apps: Path
) -> None:
    folder = _synced_lead(engine, root, apps)
    link_name = queue._apply_link(APPLY_URL, queue.PLATFORM)[0]
    (folder / link_name).unlink()

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 1, 0, 0)
    assert _link_url(folder) == APPLY_URL


def test_a_replaced_destination_pdf_is_copied_again_from_the_source(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`details["pdf_sha256"]` already records the expected digest, so this needs no new state —
    only that the digest be compared against the bytes actually present."""
    folder = _synced_lead(engine, root, apps)
    source = (apps / "2026-08-26" / "one" / "tailored-one.pdf").read_bytes()
    (folder / PDF_NAME).write_bytes(b"%PDF-1.7\nnot the delivered resume\n%%EOF\n")

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 1, 0, 0)
    assert (folder / PDF_NAME).read_bytes() == source
    assert _details(folder)["pdf_sha256"] == hashlib.sha256(source).hexdigest()


def test_a_deleted_destination_pdf_is_copied_again_with_details_intact(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The folder still claims a PDF, so the claim is the thing to repair. Nothing else detects
    this: the fast path skips `_install`, and no other command reads the queue's copy."""
    folder = _synced_lead(engine, root, apps)
    source = (apps / "2026-08-26" / "one" / "tailored-one.pdf").read_bytes()
    (folder / PDF_NAME).unlink()
    assert _details(folder)["pdf_filename"] == PDF_NAME

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 1, 0, 0)
    assert (folder / PDF_NAME).read_bytes() == source


def test_a_tampered_details_body_is_rewritten_even_though_its_hash_still_matches(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`details.json` is inside its own digest, so editing the body without the hash is exactly
    the case the recorded stamp cannot see."""
    folder = _synced_lead(engine, root, apps)
    body = _details(folder)
    recorded = body["content_hash"]
    body["company"] = "Not Acme"
    (folder / DETAILS_FILE).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 1, 0, 0)
    assert _details(folder)["company"] == "Acme Corp"
    assert _details(folder)["content_hash"] == recorded


def test_an_untouched_folder_still_reports_unchanged(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The control for the whole section: verifying the destination must not turn every sync into
    a rewrite. Bytes AND mtimes, so a read-then-rewrite-identical implementation fails."""
    folder = _synced_lead(engine, root, apps)
    before = _snapshot(folder)
    assert before, "nothing was written, so the comparison below would be vacuous"
    time.sleep(0.02)

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 0, 1, 0)
    assert _snapshot(folder) == before


def test_an_unrecognised_file_in_a_folder_is_not_an_integrity_failure(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The owner keeps their own work in these folders — one live folder holds a hand-written
    cover letter. Verification decides only whether the names this module WRITES still match."""
    folder = _synced_lead(engine, root, apps)
    extra = folder / "cover_letter.tex"
    extra.write_text("\\documentclass{article}\n", encoding="utf-8")

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 0, 1, 0)
    assert extra.read_text(encoding="utf-8") == "\\documentclass{article}\n"


def test_the_owners_own_file_survives_a_repair_of_a_damaged_known_file(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The constraint that rules out a wholesale staged replace as the repair: the live folder
    `_applied/Tailscale_…` holds `3_Cover_Letter_Tailscale.pdf` and `cover_letter.tex`, covered by
    no naming constant and no hash. Repairing the JD must not take them with it."""
    folder = _synced_lead(engine, root, apps)
    letter = folder / "3_Cover_Letter_Acme.pdf"
    letter.write_bytes(b"%PDF-1.7\nhand written\n%%EOF\n")
    (folder / "cover_letter.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    (folder / JD_FILE).write_text("TAMPERED\n", encoding="utf-8")

    report = _resync(engine, root)

    assert (report.created, report.updated, report.unchanged, report.failed) == (0, 1, 0, 0)
    assert (folder / JD_FILE).read_text(encoding="utf-8") == JD
    assert letter.read_bytes() == b"%PDF-1.7\nhand written\n%%EOF\n"
    assert (folder / "cover_letter.tex").read_text(encoding="utf-8") == (
        "\\documentclass{article}\n"
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
            jd_absent_reason="no_current_version",
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


def test_a_live_quarantine_withholds_only_the_job_description_file(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A live body quarantine is a JD absence, not a lead absence."""
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, apps, "quarantined")
        _quarantine_version(conn, posting_id)

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.failed) == (1, 0)
    folder = _sole_folder(root)
    assert not (folder / JD_FILE).exists()
    details = _details(folder)
    assert details["job_description_file"] is None
    assert details["job_description_absent_reason"] == "quarantined_foreign_body"


def test_a_quarantined_lead_still_has_its_pdf_and_apply_link(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Suppressing a quarantined body must not filter the delivered lead."""
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, apps, "quarantined-lead")
        _quarantine_version(conn, posting_id)

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.failed) == (1, 0)
    folder = _sole_folder(root)
    pdfs = list(folder.glob("*.pdf"))
    assert len(pdfs) == 1
    assert pdfs[0].read_bytes().startswith(b"%PDF-1.7\nquarantined-lead")
    assert _link_url(folder) == APPLY_URL
    details = _details(folder)
    assert details["posting_id"] == posting_id
    assert details["job_description_absent_reason"] == "quarantined_foreign_body"


def test_a_reopened_quarantine_delivers_the_body_normally(
    engine: Engine, root: Path, apps: Path
) -> None:
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, apps, "reopened")
        _quarantine_version(conn, posting_id, reopened_at=NOW + timedelta(minutes=1))

    with engine.connect() as conn:
        detail = queue.queue_detail(conn, posting_id)

    assert detail is not None
    assert detail.jd_body == JD
    assert detail.jd_absent_reason is None

    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.failed) == (1, 0)
    folder = _sole_folder(root)
    assert (folder / JD_FILE).read_text(encoding="utf-8") == JD
    details = _details(folder)
    assert details["job_description_file"] == JD_FILE
    assert details["job_description_absent_reason"] is None


def test_a_quarantine_on_an_older_version_does_not_suppress_the_current_body(
    engine: Engine, apps: Path
) -> None:
    current_body = "The employer's current description."
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, apps, "superseded", body="The older description.")
        old_version_id = int(
            conn.execute(
                select(posting_versions.c.id)
                .where(posting_versions.c.posting_id == posting_id)
                .order_by(posting_versions.c.id)
                .limit(1)
            ).scalar_one()
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id,
                content_hash="v-superseded-current",
                body_text=current_body,
                captured_at=NOW,
                capture_reason="revised",
            )
        )
        _quarantine_version(conn, posting_id, version_id=old_version_id)

    with engine.connect() as conn:
        detail = queue.queue_detail(conn, posting_id)

    assert detail is not None
    assert detail.jd_body == current_body
    assert detail.jd_absent_reason is None


def test_a_missing_current_version_keeps_the_no_current_version_reason(
    engine: Engine, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, apps, "no-current")

    monkeypatch.setattr(
        "boardwatch.store.delivery_queries.current_posting_versions",
        lambda *args, **kwargs: {},
    )
    with engine.connect() as conn:
        detail = queue.queue_detail(conn, posting_id)

    assert detail is not None
    assert detail.jd_body is None
    assert detail.jd_absent_reason == "no_current_version"


def test_an_unknown_job_description_absence_reason_fails_the_lead(
    engine: Engine, root: Path, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with engine.begin() as conn:
        posting_id, _job = _deliver(conn, apps, "unknown-reason")
    real = queue.queue_detail

    def invalid_detail(conn: Connection, posting_id: int) -> object:
        detail = real(conn, posting_id)
        assert detail is not None
        return SimpleNamespace(
            row=detail.row,
            jd_body=None,
            jd_absent_reason="invented_reason",
            requirements=detail.requirements,
            board_target=detail.board_target,
        )

    monkeypatch.setattr(queue, "queue_detail", invalid_detail)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.created, report.failed) == (0, 1)
    assert _folders(root) == []


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


#: A body the bundled catalog matches NOTHING in, so a real evaluation of it produces zero
#: requirement rows — A3's population. Its premise is asserted in the test that uses it.
SILENT_JD = "Join our team. We build delightful things and we value curiosity."


def test_a_lead_whose_JD_states_no_requirement_is_filed_under_review(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A3 through the FOLDER TREE, which is a different call site from the page's (D-332).

    `sync_queue` places a lead in the lane `review_gate.lane` returns, so dropping the new
    argument from that call puts this folder back at the queue root while the page still shows it
    under review — the exact disagreement `_review` exists to prevent. The control is the default
    `JD`, which states requirements and stays at the root.
    """
    # Different companies, so the two leads cannot share a folder NAME and each assertion below
    # names the lead it is about.
    with engine.begin() as conn:
        _deliver(conn, apps, "silent", company="Silent Co", body=SILENT_JD)
        _deliver(conn, apps, "stated", company="Stated Co")
    catalog = load_rules(load_settings().config_dir)
    # The premise, out loud: if a catalog edit ever finds a requirement in this body, this fails
    # here rather than silently testing nothing.
    assert evaluate(SILENT_JD, FACTS, POLICY, catalog).requirements == ()
    assert evaluate(JD, FACTS, POLICY, catalog).requirements != ()

    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)

    assert _folders(root) == ["Stated_Co_Software_Engineer"]
    assert _folders(root / REVIEW_DIR) == ["Silent_Co_Software_Engineer"]


def test_details_json_records_why_the_review_lane_holds_the_lead(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The reason travels to disk, so a run's review composition is readable without the web API.

    Asserted against `lane_decision` itself rather than against a hand-written string: the
    persisted reason and the folder the lead sits in must be the SAME decision (D-332), so a
    re-derivation that agreed today and drifted tomorrow would pass a literal-only assertion. The
    literal is pinned too, so a classifier that started returning the wrong member for this lead
    cannot make both sides of the comparison wrong together.
    """
    with engine.begin() as conn:
        silent_id, _ = _deliver(conn, apps, "silent", company="Silent Co", body=SILENT_JD)
        _deliver(conn, apps, "stated", company="Stated Co")
    with engine.connect() as conn:
        rows = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
        sync_queue(conn, root=root, owner_name=OWNER)

    expected = lane_decision(rows[silent_id]).reason
    assert expected == "no_requirements_found"

    held = _details(root / REVIEW_DIR / "Silent_Co_Software_Engineer")["review_reason"]
    assert held == expected
    assert held in get_args(ReviewReason)


def test_details_json_records_no_review_reason_for_an_apply_lane_lead(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`null`, not an empty string and not an absent key. A lead in the apply queue is held for no
    reason at all, and folding that into a review member would corrupt the composition the field
    exists to report."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)

    details = _details(_sole_folder(root))
    assert "review_reason" in details
    assert details["review_reason"] is None


def test_an_unknown_review_reason_fails_the_lead(
    engine: Engine, root: Path, apps: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Out-of-catalog is a failure, never a new bucket: a reason this module cannot name is one
    `details.json` would publish unexplained, and a folder written under it would be read by the
    composition report as a tenth member that does not exist."""
    with engine.begin() as conn:
        _deliver(conn, apps, "invented-reason")

    def invented(row: object) -> LaneDecision:
        return LaneDecision(REVIEW_DIR, "invented_reason")  # type: ignore[arg-type]

    monkeypatch.setattr(queue, "lane_decision", invented)
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    monkeypatch.undo()

    assert (report.created, report.failed) == (0, 1)
    assert _folders(root / REVIEW_DIR) == []


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
        taxonomy_version="v1", resume_max_pages=1, target_countries=["USA"],
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

    # Back to the identity `_deliver` wrote its evaluation under, so the ORIGINAL `eligible`
    # verdict governs again. A third identity would leave the lead unevaluated, which since A3
    # returns it to `_review` rather than to the apply queue — a true answer to a different
    # question than the one this test asks.
    with engine.begin() as conn:
        save_eligibility(
            conn,
            facts_json=facts_payload(FACTS),
            policy_json=POLICY.model_dump(mode="json"),
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
        LANE_COPY_DIR,
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
    APPLIED job, so that path is decided upstream. Calling the function with every set populated
    is the only way to pin the branch order, and reordering the branches fails this.
    """
    entry = queue._Entry(
        path=Path("x"), location="", posting_id=1, job_id=7, content_hash=None
    )
    both = {7: "2026-08-26"}
    verdict = {7: "ineligible"}
    review = {7}
    closed = {7}
    lane_copy = {7}
    assert queue._wanted_location(
        entry, applied=both, skipped=both, reported=both, closed=closed,
        ineligible=verdict, review=review, lane_copy=lane_copy,
    ) == APPLIED_DIR
    assert queue._wanted_location(
        entry, applied={}, skipped=both, reported=both, closed=closed,
        ineligible=verdict, review=review, lane_copy=lane_copy,
    ) == SKIPPED_DIR
    # `reported` is an owner statement, so it outranks both derived drains AND `closed` -- but it
    # ranks below the two statements about what the owner DID with the lead. Nothing is lost by
    # that: the `queue.reported.<job_id>` marker is the record an investigation reads, and it
    # survives whichever folder holds the copy (D-427).
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported=both, closed=closed,
        ineligible=verdict, review=review, lane_copy=lane_copy,
    ) == REPORTED_DIR
    # closed ranks below BOTH owner statements and above both derived drains: the employer taking
    # the requisition down does not un-say what the owner already decided, but it does settle a
    # lead the gate could only have held for a second look.
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported={}, closed=closed,
        ineligible=verdict, review=review, lane_copy=lane_copy,
    ) == CLOSED_DIR
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported={}, closed=set(),
        ineligible=verdict, review=review, lane_copy=lane_copy,
    ) == INELIGIBLE_DIR
    # `lane_copy` ranks below `ineligible` -- a verdict about the LEAD beats a fact about
    # REDUNDANCY -- and above `review`, because a lead whose employer-board twin is already in
    # front of the owner is not a second thing to look at.
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported={}, closed=set(),
        ineligible={}, review=review, lane_copy=lane_copy,
    ) == LANE_COPY_DIR
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported={}, closed=set(),
        ineligible={}, review=review, lane_copy=set(),
    ) == REVIEW_DIR
    assert queue._wanted_location(
        entry, applied={}, skipped={}, reported={}, closed=set(),
        ineligible={}, review=set(), lane_copy=set(),
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


def test_consolidating_two_folders_keeps_the_owners_files_from_BOTH(
    engine: Engine, root: Path, apps: Path
) -> None:
    """T189 F2. The consolidation above retires a whole folder, and a queue folder is partly the
    owner's (T121). The keeper is arbitrary, so the retired one is as likely as not the one the
    owner worked in: its own files move into the keeper, a name the keeper already holds is kept
    beside it under a suffix, and boardwatch's own files in it are not carried at all."""
    with engine.begin() as conn:
        first, _ = _deliver(conn, apps, "one")
        second, second_job = _deliver(conn, apps, "two")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    before = _folders(root)
    for name in before:
        (root / name / "cover-letter.tex").write_text(f"mine, in {name}\n", encoding="utf-8")
        (root / name / f"notes-{name}.txt").write_text("only here\n", encoding="utf-8")

    with engine.begin() as conn:
        conn.execute(update(postings).where(postings.c.id == first).values(job_id=second_job))
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)

    assert (report.retired, report.failures) == (1, ())
    (kept,) = _folders(root)
    folder = root / kept
    letters = sorted(
        path.read_text(encoding="utf-8") for path in folder.glob("cover-letter*.tex")
    )
    assert letters == sorted(f"mine, in {name}\n" for name in before)
    for name in before:
        assert (folder / f"notes-{name}.txt").read_text(encoding="utf-8") == "only here\n"
    # Nothing boardwatch wrote in the retired folder came along: one résumé, one details.json.
    assert len(list(folder.glob("*.pdf"))) == 1

    snapshot = _snapshot(root)
    with engine.connect() as conn:
        again = sync_queue(conn, root=root, owner_name=OWNER)
    assert (again.retired, again.moved, again.updated, again.failures) == (0, 0, 0, ())
    assert _snapshot(root) == snapshot


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


# ---------------------------------------------------------- T189: names that differ only by case


def _case_insensitive(base: Path) -> bool:
    probe = base / "Case-Probe"
    probe.mkdir(parents=True)
    try:
        return (base / "case-probe").exists()
    finally:
        probe.rmdir()


def test_a_case_only_retitle_renames_the_folder_instead_of_refusing_forever(
    engine: Engine, root: Path, apps: Path
) -> None:
    """T189 F3. On APFS and NTFS the new name and the old one are ONE path, so `_relocate` saw its
    destination "occupied" by the very folder it was moving and raised `QueueConflictError` on
    every sync, which also froze the lead's content. Only reproducible where the filesystem folds
    case, so it is skipped elsewhere rather than passing vacuously."""
    if not _case_insensitive(root.parent / "probe"):
        pytest.skip("needs a case-insensitive filesystem (APFS/NTFS default)")
    with engine.begin() as conn:
        pid, _ = _deliver(conn, apps, "k1", company="Acme Corp", title="Software Engineer")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    (old,) = _folders(root)
    (root / old / "cover-letter.tex").write_text("mine\n", encoding="utf-8")

    with engine.begin() as conn:
        conn.execute(update(postings).where(postings.c.id == pid).values(title="Software ENGINEER"))
    with engine.connect() as conn:
        report = sync_queue(conn, root=root, owner_name=OWNER)
    assert (report.failures, report.moved) == ((), 1)
    assert _folders(root) == ["Acme_Corp_Software_ENGINEER"]
    assert (root / "Acme_Corp_Software_ENGINEER" / "cover-letter.tex").read_text(
        encoding="utf-8"
    ) == "mine\n"
    assert _details(root / "Acme_Corp_Software_ENGINEER")["title"] == "Software ENGINEER"

    with engine.connect() as conn:
        again = sync_queue(conn, root=root, owner_name=OWNER)
    assert (again.failures, again.moved, again.updated, again.unchanged) == ((), 0, 0, 1)


def test_T172_widening_sees_an_occupant_that_differs_only_by_case(
    engine: Engine, root: Path
) -> None:
    """T189 F4. `_applied/onX_…` is job A; `OnX_…` at the root is job B, and B is applied. On a
    folding filesystem the plain destination exists, but its occupant is indexed under the other
    case, so an exact-path lookup missed it, T172's widening never fired, and `_relocate` refused
    on every run."""
    if not _case_insensitive(root.parent / "probe"):
        pytest.skip("needs a case-insensitive filesystem (APFS/NTFS default)")
    with engine.begin() as conn:
        a = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        b = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        create_application(conn, job_id=a, status="applied", source="t")
        create_application(conn, job_id=b, status="applied", source="t")
    _plant_folder(root, APPLIED_DIR, "onX_Backend_Engineer", posting_id=901, job_id=a,
                  company="onX", identity_hash="c0ffee01")
    _plant_folder(root, "", "OnX_Backend_Engineer", posting_id=902, job_id=b,
                  company="OnX", identity_hash="c0ffee02")
    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root, owner_name=OWNER)
    assert (report.failures, report.to_applied) == ((), 1)
    assert _folders(root / APPLIED_DIR) == ["OnX_Backend_Engineer_c0ffee02", "onX_Backend_Engineer"]
    assert _details(root / APPLIED_DIR / "onX_Backend_Engineer")["job_id"] == a
    assert _folders(root) == []


# --------------------------------------------------------------------- T172: cross-job collision


def _drain_two_jobs_with_colliding_names(
    engine: Engine, apps: Path, root: Path
) -> tuple[ReconcileReport, str, dict[str, tuple[bytes, int]]]:
    """Job A is delivered, synced and applied FIRST, so its folder lands in `_applied` while it is
    the only lead `_plan` ever sees. Job B, same company and title, is delivered and synced SECOND
    -- job A is no longer in `standing_queue_rows` to disambiguate against, so job B plans the
    identical PLAIN name at the queue root. Only once job B is ALSO applied does reconcile try to
    drain it into the name job A's folder already holds -- T172's measured shape, reached through
    the real pipeline rather than a hand-planted folder.

    Returns the report from the reconcile that meets the collision, job B's own identity hash
    (read back from its own `details.json`, written before either application, so a caller can
    compute the widened name it should have moved to), and a byte-and-mtime snapshot of job B's
    folder taken BEFORE that reconcile -- so a caller can prove the widened folder is the SAME
    files moved, not a re-created shell (Codex review round 1's follow-up).
    """
    with engine.begin() as conn:
        _, job_a = _deliver(conn, apps, "one", company="Acme Corp", title="Backend Engineer")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        create_application(conn, job_id=job_a, status="applied", source="test")
    with engine.connect() as conn:
        reconcile_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root / APPLIED_DIR) == ["Acme_Corp_Backend_Engineer"], "premise: job A drained"

    with engine.begin() as conn:
        _, job_b = _deliver(conn, apps, "two", company="Acme Corp", title="Backend Engineer")
    with engine.connect() as conn:
        planned = sync_queue(conn, root=root, owner_name=OWNER)
    assert planned.failed == 0, planned.failures
    assert _folders(root) == ["Acme_Corp_Backend_Engineer"], "premise: the plain name is free"
    identity_hash = str(_details(root / "Acme_Corp_Backend_Engineer")["identity_hash"])
    before_move = _snapshot(root / "Acme_Corp_Backend_Engineer")

    with engine.begin() as conn:
        create_application(conn, job_id=job_b, status="applied", source="test")
    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root, owner_name=OWNER)
    return report, identity_hash, before_move


def test_a_different_jobs_applied_folder_widens_instead_of_colliding(
    engine: Engine, root: Path, apps: Path
) -> None:
    """T172. Red on the code before this change: `reconcile_queue` raised `QueueConflictError`
    naming `Acme_Corp_Backend_Engineer already exists at its destination` and reported one folder
    failed to move -- on this reconcile and on every one after it, forever, because nothing ever
    renamed either folder."""
    report, identity_hash, before_move = _drain_two_jobs_with_colliding_names(engine, apps, root)

    assert report.failed == 0, report.failures
    assert _folders(root) == []
    applied_names = _folders(root / APPLIED_DIR)
    assert len(applied_names) == 2, applied_names
    assert "Acme_Corp_Backend_Engineer" in applied_names
    expected_widened = plan_lead_names(
        root=root.resolve(),
        owner_name=OWNER,
        company="Acme Corp",
        title=f"Backend Engineer {identity_hash[:8]}",
        identity_hash=identity_hash,
    ).folder
    assert expected_widened in applied_names, applied_names
    assert expected_widened != "Acme_Corp_Backend_Engineer"
    # Moved, not re-created or truncated to an empty shell: the SAME bytes and the SAME inode's
    # mtimes travel with job B's folder under the widened name (Codex review round 1's follow-up
    # -- `(root / APPLIED_DIR / expected_widened / DETAILS_FILE).exists()` alone would pass
    # against a version that rewrote the folder from the store instead of moving it).
    assert _snapshot(root / APPLIED_DIR / expected_widened) == before_move


def test_a_second_reconcile_after_the_widened_move_changes_nothing(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Idempotence. `_entry_for` locates a folder by the posting inside its `details.json`, never
    by name, so the widened folder must be found as job B's own next time -- not re-created, and
    not moved again looking for a plainer name."""
    report, _identity_hash, _before_move = _drain_two_jobs_with_colliding_names(engine, apps, root)
    assert report.failed == 0, report.failures
    before = _snapshot(root)

    with engine.connect() as conn:
        again_reconcile = reconcile_queue(conn, root=root, owner_name=OWNER)
    with engine.connect() as conn:
        again_sync = sync_queue(conn, root=root, owner_name=OWNER)

    assert (again_reconcile.moved, again_reconcile.failed) == (0, 0), again_reconcile.failures
    assert (again_sync.moved, again_sync.created, again_sync.updated, again_sync.failed) == (
        0, 0, 0, 0,
    ), again_sync.failures
    assert _snapshot(root) == before


def test_a_same_job_occupied_destination_still_refuses_as_before(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Control. TWO folders can share one job -- an identity-convergence duplicate
    `_resolve_job_identity` reports but does not consolidate (`_consolidate_duplicates` is
    `sync_queue`'s, not reconcile's) -- and that must still be refused exactly as before. Widening
    applies only to a DIFFERENT job's folder; dropping that check would let this collision through
    silently, which is the mutation this test exists to catch."""
    with engine.begin() as conn:
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        create_application(conn, job_id=job_id, status="applied", source="test")
    _plant_folder(
        root, APPLIED_DIR, "Acme_Corp_Backend_Engineer",
        posting_id=901, job_id=job_id, identity_hash="c0ffee01",
    )
    _plant_folder(
        root, "", "Acme_Corp_Backend_Engineer",
        posting_id=902, job_id=job_id, identity_hash="c0ffee02",
    )

    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root, owner_name=OWNER)

    assert report.failed == 1, report.failures
    assert "already exists" in report.failures[0].detail, report.failures[0].detail
    assert _folders(root) == ["Acme_Corp_Backend_Engineer"], "the source folder must be untouched"
    assert _folders(root / APPLIED_DIR) == ["Acme_Corp_Backend_Engineer"]
    assert int(str(_details(root / APPLIED_DIR / "Acme_Corp_Backend_Engineer")["posting_id"])) == 901


def test_a_converged_occupants_stale_stored_job_id_still_refuses(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Regression for review round 1's blocker. The OCCUPANT's own `details.json` can be STALE
    after an identity convergence (D-430's shape): its posting's canonical job moved on, but its
    folder was never rewritten, so it still names the OLD job. Reading that stale value back would
    make the occupant look like a DIFFERENT job from the mover and widen instead of refusing --
    leaving two folders for the one job that actually owns both. `_widen_for_a_different_job` must
    compare the REFRESHED job id `_reconcile_locked` computed (`known_job_ids`), never the
    occupant's own file.

    Built the way `test_a_lead_whose_canonical_job_MOVED_keeps_the_folder_it_already_has` and
    `test_TWO_folders_converging_on_one_job_are_consolidated_not_refused_forever` build a
    convergence: `postings.job_id` is updated directly, after each posting already has its own
    folder on disk. `reconcile_queue` is called ALONE, never `sync_queue` -- `_consolidate_
    duplicates` only ever runs inside `sync_queue`, so it never gets a chance to clean this up
    first, and reconcile's own refusal is what this test pins.
    """
    with engine.begin() as conn:
        occupant_posting, job_old = _deliver(
            conn, apps, "occ", company="Acme Corp", title="Backend Engineer"
        )
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        create_application(conn, job_id=job_old, status="applied", source="test")
    with engine.connect() as conn:
        reconcile_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root / APPLIED_DIR) == ["Acme_Corp_Backend_Engineer"], "premise: occupant drained"

    with engine.begin() as conn:
        _, job_canonical = _deliver(
            conn, apps, "mover", company="Acme Corp", title="Backend Engineer"
        )
    with engine.connect() as conn:
        planned = sync_queue(conn, root=root, owner_name=OWNER)
    assert planned.failed == 0, planned.failures
    assert _folders(root) == ["Acme_Corp_Backend_Engineer"], "premise: the mover's plain name is free"

    with engine.begin() as conn:
        # The convergence itself: the occupant's posting now belongs to the SAME job as the
        # mover, but its folder's own `details.json` (written back in the first reconcile above)
        # is never rewritten here -- it still names `job_old`.
        conn.execute(
            update(postings).where(postings.c.id == occupant_posting).values(job_id=job_canonical)
        )
        create_application(conn, job_id=job_canonical, status="applied", source="test")

    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root, owner_name=OWNER)

    assert report.failed == 1, report.failures
    assert "already exists" in report.failures[0].detail, report.failures[0].detail
    assert _folders(root) == ["Acme_Corp_Backend_Engineer"], "the mover must be left in place"
    assert _folders(root / APPLIED_DIR) == ["Acme_Corp_Backend_Engineer"], "no second folder"
    assert (
        int(str(_details(root / APPLIED_DIR / "Acme_Corp_Backend_Engineer")["posting_id"]))
        == occupant_posting
    ), "the occupant's own folder, untouched"


def test_a_folder_freed_then_filled_within_one_pass_is_not_read_from_the_stale_map(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Regression for review round 2's defect. `known_job_ids` is built ONCE before
    `_reconcile_locked`'s loop, but the loop itself MOVES folders -- so a LATER entry's
    occupied-destination check must see where an EARLIER entry in this SAME pass actually ended
    up, not the snapshot taken before the loop started.

    One pass, three folders sharing one name, all `Acme_Corp_Backend_Engineer`:
    - A (lowest posting id, processed first) sits in `_applied/NAME`; its application is
      WITHDRAWN, so it now wants the queue root -- vacating `_applied/NAME`.
    - B sits in `_skipped/NAME` and is now ALSO applied, so it wants `_applied/NAME` -- exactly
      the path A just vacated, and B is processed second (its posting id is between A's and C's).
    - C, converged onto B's job (the `update(postings)...job_id` trick `test_a_converged_
      occupants_stale_stored_job_id_still_refuses` uses, but reached WITHIN this one pass rather
      than before it starts), also wants `_applied/NAME`, and is processed last.

    Without following the loop's own moves, C's check reads the map entry for `_applied/NAME`
    exactly as it was seeded before the loop ran -- A's OLD job, still sitting there in the
    snapshot -- sees it differs from C's (converged) job, and widens C into a SECOND folder for
    B's job. Following the moves, the same path now maps to B's job by the time C is checked,
    which matches C's, and C is refused instead.

    C's own folder is planted directly (`_plant_folder`) rather than reached through its own
    `sync_queue`/`reconcile_queue` pass: a real `postings` row (so the `job_id` convergence update
    and `canonical_job_ids` resolve it) is all C needs, and planting the folder avoids a SEPARATE
    collision -- synced normally, C's folder would land at the queue ROOT under this same name,
    exactly where A's withdrawal ALSO wants to go, confounding the one interaction this test
    isolates.
    """
    with engine.begin() as conn:
        _, job_a = _deliver(conn, apps, "a", company="Acme Corp", title="Backend Engineer")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        app_a = create_application(conn, job_id=job_a, status="applied", source="test")
    with engine.connect() as conn:
        reconcile_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root / APPLIED_DIR) == ["Acme_Corp_Backend_Engineer"], "premise: A drained"

    with engine.begin() as conn:
        _, job_b = _deliver(conn, apps, "b", company="Acme Corp", title="Backend Engineer")
    with engine.connect() as conn:
        planned = sync_queue(conn, root=root, owner_name=OWNER)
    assert planned.failed == 0, planned.failures
    assert _folders(root) == ["Acme_Corp_Backend_Engineer"], "premise: B's plain name is free"
    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=job_b, at=NOW)
    with engine.connect() as conn:
        reconcile_queue(conn, root=root, owner_name=OWNER)
    assert _folders(root / SKIPPED_DIR) == ["Acme_Corp_Backend_Engineer"], "premise: B skipped"
    assert _folders(root) == [], "premise: the root is free again"

    with engine.begin() as conn:
        posting_c, _job_c = _deliver(
            conn, apps, "c", company="Acme Corp", title="Backend Engineer"
        )
    _plant_folder(
        root, LANE_COPY_DIR, "Acme_Corp_Backend_Engineer",
        posting_id=posting_c, job_id=999999, identity_hash="c0ffeec0",
    )

    with engine.begin() as conn:
        # The three transitions this ONE pass must resolve together, in posting-id order A, B, C.
        set_application_status(conn, application_id=app_a, to_status="withdrawn", source="test")
        create_application(conn, job_id=job_b, status="applied", source="test")
        conn.execute(update(postings).where(postings.c.id == posting_c).values(job_id=job_b))

    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root, owner_name=OWNER)

    assert (report.to_queue, report.to_applied) == (1, 1), report  # A out, B in; not C too
    assert report.failed == 1, report.failures
    assert "already exists" in report.failures[0].detail, report.failures[0].detail
    assert _folders(root) == ["Acme_Corp_Backend_Engineer"], "A landed at the root"
    applied_names = _folders(root / APPLIED_DIR)
    assert applied_names == ["Acme_Corp_Backend_Engineer"], "exactly one folder for job B"
    assert (
        int(str(_details(root / APPLIED_DIR / applied_names[0])["posting_id"])) != posting_c
    ), "the surviving folder must be B's, not a second one for C"


def test_a_non_colliding_applied_lead_still_moves_under_its_plain_name(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Control. With no name collision at all, the plain destination never exists, so widening
    must never engage -- the ordinary drain still moves a lead under the name it already has."""
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one", company="Acme Corp", title="Backend Engineer")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name
    with engine.begin() as conn:
        create_application(conn, job_id=job_id, status="applied", source="test")

    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root, owner_name=OWNER)

    assert (report.to_applied, report.failed) == (1, 0), report.failures
    assert _folders(root) == []
    assert _folders(root / APPLIED_DIR) == [folder]


def test_both_the_plain_and_widened_names_taken_still_refuses(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Control. The plain destination AND the name it would widen to are both already occupied by
    OTHER jobs. Reconcile tries exactly one widened name and never loops looking for a further
    one, so this must raise exactly as an ordinary occupied destination always has."""
    identity_hash = "deadbeef"
    widened_name = plan_lead_names(
        root=root.resolve(),
        owner_name=OWNER,
        company="Acme Corp",
        title=f"Backend Engineer {identity_hash[:8]}",
        identity_hash=identity_hash,
    ).folder

    with engine.begin() as conn:
        job_move = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        job_plain = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        job_widened = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        create_application(conn, job_id=job_move, status="applied", source="test")
        create_application(conn, job_id=job_plain, status="applied", source="test")
        create_application(conn, job_id=job_widened, status="applied", source="test")
    _plant_folder(
        root, APPLIED_DIR, "Acme_Corp_Backend_Engineer",
        posting_id=801, job_id=job_plain, identity_hash="c0ffee01",
    )
    _plant_folder(
        root, APPLIED_DIR, widened_name,
        posting_id=802, job_id=job_widened, identity_hash="c0ffee02",
    )
    _plant_folder(
        root, "", "Acme_Corp_Backend_Engineer",
        posting_id=803, job_id=job_move, identity_hash=identity_hash,
    )

    with engine.connect() as conn:
        report = reconcile_queue(conn, root=root, owner_name=OWNER)

    assert report.failed == 1, report.failures
    assert "already exists" in report.failures[0].detail, report.failures[0].detail
    assert _folders(root) == ["Acme_Corp_Backend_Engineer"], "the moving folder is left in place"
    assert sorted(_folders(root / APPLIED_DIR)) == sorted(
        ["Acme_Corp_Backend_Engineer", widened_name]
    )
    assert int(str(_details(root / APPLIED_DIR / "Acme_Corp_Backend_Engineer")["posting_id"])) == 801
    assert int(str(_details(root / APPLIED_DIR / widened_name)["posting_id"])) == 802


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
        _judge_version(conn, version_id, JD)
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
        [
            APPLIED_DIR, SKIPPED_DIR, INELIGIBLE_DIR, REVIEW_DIR, CLOSED_DIR, REPORTED_DIR,
            LANE_COPY_DIR,
        ]
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


# --------------------------------------------------------------------- D-498 rule (a)'s drain


def _cross_host(
    conn: Connection,
    posting_id: int,
    key: str,
    *,
    version: str = IDENTITY_ALGORITHM_VERSION,
) -> None:
    """One `cross_host` identity row. Written by hand because `_deliver` writes none, and this
    drain is defined entirely by that grouping.

    `version` defaults to the CURRENT generation and must: the readers behind this drain select
    it, so a fixture at any other value describes a group no correct reader sees and every
    assertion below it becomes vacuous. `RETIRED` is passed explicitly where a test is about a
    generation the identity subsystem has withdrawn.
    """
    conn.execute(
        insert(posting_identities).values(
            posting_id=posting_id,
            kind="cross_host",
            identity_key=key,
            algorithm_version=version,
            created_at=NOW,
        )
    )


def test_a_lane_copy_drains_when_the_employer_board_twin_is_standing(
    engine: Engine, root: Path, apps: Path
) -> None:
    """D-498 rule (a) runs in the RANKER, so it stops a redundant copy being delivered and does
    nothing about the ones already delivered. Measured 2026-09-14: 17 such leads standing.
    """
    with engine.begin() as conn:
        board_id, _ = _deliver(conn, apps, "board", provider="greenhouse")
        lane_id, _ = _deliver(conn, apps, "lane", provider="jobapps")
    # Grouped AFTER the first sync, which is how the standing population got its folders: a lane
    # copy grouped before it is ever synced gets no folder at all (the test below this one).
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        _cross_host(conn, board_id, "same-job")
        _cross_host(conn, lane_id, "same-job")
    assert len(_folders(root)) == 2

    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert (drained.to_lane_copy, drained.moved, drained.failed) == (1, 1, 0)
    assert len(_folders(root / LANE_COPY_DIR)) == 1
    # The EMPLOYER's copy is the one left in front of the owner.
    assert len(_folders(root)) == 1


def test_two_employer_board_copies_of_one_job_BOTH_stay(
    engine: Engine, root: Path, apps: Path
) -> None:
    """§3.1's counterexample, and the case this drain must never touch.

    `cross_host` groups and never suppresses precisely because Microsoft's four same-title
    Redmond postings are four real requisitions under one key. They are all EMPLOYER-BOARD rows,
    so the provider test excludes every one of them. Without that test this drain would delete
    three of the four, which is the failure §3.1 refuses — so this is the discriminating case,
    not a redundant one.
    """
    with engine.begin() as conn:
        first_id, _ = _deliver(conn, apps, "reqA", provider="greenhouse")
        second_id, _ = _deliver(conn, apps, "reqB", provider="workday")
        _cross_host(conn, first_id, "same-title")
        _cross_host(conn, second_id, "same-title")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert drained.to_lane_copy == 0
    assert _folders(root / LANE_COPY_DIR) == []
    assert len(_folders(root)) == 2


def test_the_lane_copy_returns_when_the_board_twin_stops_holding(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The re-entry path, designed in the same change as the quarantine and running on both
    sides of the gate. A drain without one is a trapdoor: the lane copy would be filed forever
    behind a board lead the owner has already dealt with.
    """
    with engine.begin() as conn:
        board_id, board_job = _deliver(conn, apps, "board", provider="greenhouse")
        lane_id, _ = _deliver(conn, apps, "lane", provider="jobapps")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        _cross_host(conn, board_id, "same-job")
        _cross_host(conn, lane_id, "same-job")
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert drained.to_lane_copy == 1

    # The owner skips the board copy: it stops holding, so the lane copy is work again.
    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=board_job, at=NOW)
    with engine.connect() as conn:
        restored = reconcile_queue(conn, root=root)
    assert restored.to_queue == 1
    assert _folders(root / LANE_COPY_DIR) == []
    assert len(_folders(root)) == 1


def test_a_lane_copy_stays_drained_across_refresh_queue(
    engine: Engine, root: Path, apps: Path
) -> None:
    """T189 F1, through `refresh_queue` -- the run's and the server start's path -- rather than
    `reconcile_queue` alone, which is what let the drain ship dead. The sync half used to pull the
    folder straight back out of `_lane_copy/`: the tell is `moved`, not `created`, and a second
    refresh must change nothing at all. The re-entry path is pinned through the same entry point.
    """
    with engine.begin() as conn:
        board_id, board_job = _deliver(conn, apps, "board", provider="greenhouse")
        lane_id, _ = _deliver(conn, apps, "lane", provider="jobapps")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        _cross_host(conn, board_id, "same-job")
        _cross_host(conn, lane_id, "same-job")

    (lane_folder,) = [
        name for name in _folders(root)
        if _details(root / name)["posting_id"] == lane_id
    ]
    drained, synced = queue.refresh_queue(engine, root=root, owner_name=OWNER)
    assert (drained.to_lane_copy, drained.failed, synced.failures) == (1, 0, ())
    assert _folders(root / LANE_COPY_DIR) == [lane_folder]
    # The ONE move is the board twin's, and it is `_plan`'s ordinary rule rather than the drain's:
    # its lane-copy sibling left the plan, so its disambiguating suffix is no longer needed.
    assert synced.moved == 1
    assert _folders(root) == ["Acme_Corp_Software_Engineer"]

    before = _snapshot(root)
    drained, synced = queue.refresh_queue(engine, root=root, owner_name=OWNER)
    assert (drained.moved, synced.moved, synced.created, synced.updated) == (0, 0, 0, 0)
    assert _snapshot(root) == before

    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=board_job, at=NOW)
    drained, synced = queue.refresh_queue(engine, root=root, owner_name=OWNER)
    assert (drained.to_queue, synced.failures) == (1, ())
    assert _folders(root / LANE_COPY_DIR) == []
    assert len(_folders(root)) == 1


def test_a_lane_copy_grouped_before_its_first_sync_gets_no_folder_until_the_twin_stops_holding(
    engine: Engine, root: Path, apps: Path
) -> None:
    """T189 F1's other side: `standing_queue_rows` leaves a lane copy out, so `sync_queue` never
    creates one -- exactly as it never creates an `ineligible` lead's -- and creates it once the
    board twin stops holding, which is the drain's re-entry path for a lead that never had a
    folder."""
    with engine.begin() as conn:
        board_id, board_job = _deliver(conn, apps, "board", provider="greenhouse")
        lane_id, _ = _deliver(conn, apps, "lane", provider="jobapps")
        _cross_host(conn, board_id, "same-job")
        _cross_host(conn, lane_id, "same-job")
    drained, synced = queue.refresh_queue(engine, root=root, owner_name=OWNER)
    assert (drained.moved, synced.created, synced.failures) == (0, 1, ())
    assert len(_folders(root)) == 1
    assert _folders(root / LANE_COPY_DIR) == []

    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=board_job, at=NOW)
    drained, synced = queue.refresh_queue(engine, root=root, owner_name=OWNER)
    assert (synced.created, synced.failures) == (1, ())
    assert len(_folders(root)) == 1
    assert len(_folders(root / SKIPPED_DIR)) == 1


def test_an_ineligible_lane_copy_files_under_ineligible_not_lane_copy(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Precedence. An ineligible verdict is a statement about the LEAD; a lane copy is only a
    statement about REDUNDANCY, so filing the rejected lead under `_lane_copy` would hide the
    stronger fact behind the weaker one.
    """
    with engine.begin() as conn:
        board_id, _ = _deliver(conn, apps, "board", provider="greenhouse")
        lane_id, _ = _deliver(conn, apps, "lane", provider="jobapps", body=INELIGIBLE_JD)
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        _cross_host(conn, board_id, "same-job")
        _cross_host(conn, lane_id, "same-job")
    with engine.begin() as conn:
        _make_ineligible(conn, lane_id)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    # Both facts hold at once: the lead IS a lane copy, and it files under the stronger claim.
    assert drained.to_lane_copy == 0
    assert drained.to_ineligible == 1
    assert len(_folders(root / INELIGIBLE_DIR)) == 1
    assert _folders(root / LANE_COPY_DIR) == []


# ------------------------------- the drain reads the CURRENT identity generation only (T114)

#: A generation the identity subsystem has retired. `write_identities` writes BESIDE history — the
#: UNIQUE key is (posting_id, kind, algorithm_version) — and `identities reap` is manual,
#: so retired rows stay on disk. Filing a standing lead under `_lane_copy` on a withdrawn key is
#: a quarantine with no evidence behind it, so the two readers this drain sits on
#: (`standing_board_cross_host_keys` and `lane_copy_job_ids`) select the current one.
RETIRED = "p6.1"
assert RETIRED != IDENTITY_ALGORITHM_VERSION  # the fixtures below must actually be stale


@pytest.mark.parametrize("board_first", [True, False])
def test_a_group_held_only_at_a_RETIRED_generation_drains_nothing(
    engine: Engine, root: Path, apps: Path, board_first: bool
) -> None:
    """Both standing leads carry a `cross_host` key at a retired generation and nothing current,
    so no current evidence says one covers the other -- and the lane copy stays in front of the
    owner. Missing evidence means no quarantine, which is the fail-open direction.

    Both seeding orders are run because neither production read carries an `ORDER BY`.
    """
    with engine.begin() as conn:
        board_id, _ = _deliver(conn, apps, "board", provider="greenhouse")
        lane_id, _ = _deliver(conn, apps, "lane", provider="jobapps")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        for posting_id in ((board_id, lane_id) if board_first else (lane_id, board_id)):
            _cross_host(conn, posting_id, "same-job", version=RETIRED)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert drained.to_lane_copy == 0
    assert _folders(root / LANE_COPY_DIR) == []
    assert len(_folders(root)) == 2


def test_a_board_twin_at_a_RETIRED_generation_holds_nothing(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`standing_board_cross_host_keys` in isolation: the LANE copy's key is current, so only the
    holder set can move. The board copy's only row is retired, so it elects nothing and the lane
    copy is not a redundant rendering of anything the owner can see."""
    with engine.begin() as conn:
        board_id, _ = _deliver(conn, apps, "board", provider="greenhouse")
        lane_id, _ = _deliver(conn, apps, "lane", provider="jobapps")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        _cross_host(conn, board_id, "same-job", version=RETIRED)
        _cross_host(conn, lane_id, "same-job")
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert drained.to_lane_copy == 0
    assert _folders(root / LANE_COPY_DIR) == []


def test_a_lane_twin_at_a_RETIRED_generation_is_not_matched_to_a_CURRENT_holder(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The mirror image, isolating `lane_copy_job_ids`: the holder set is current and correct, and
    it is the LANE row whose only key is retired. The two rows are in no current group together,
    so the lane lead is work rather than a copy."""
    with engine.begin() as conn:
        board_id, _ = _deliver(conn, apps, "board", provider="greenhouse")
        lane_id, _ = _deliver(conn, apps, "lane", provider="jobapps")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        _cross_host(conn, board_id, "same-job")
        _cross_host(conn, lane_id, "same-job", version=RETIRED)
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert drained.to_lane_copy == 0
    assert _folders(root / LANE_COPY_DIR) == []


@pytest.mark.parametrize("board_first", [True, False])
def test_the_control_a_group_held_at_the_CURRENT_generation_still_drains(
    engine: Engine, root: Path, apps: Path, board_first: bool
) -> None:
    """The control the three tests above are worthless without, run under both seeding orders: at
    the current generation the lane copy still files under `_lane_copy` and the employer's own
    copy is the one left in front of the owner."""
    with engine.begin() as conn:
        board_id, _ = _deliver(conn, apps, "board", provider="greenhouse")
        lane_id, _ = _deliver(conn, apps, "lane", provider="jobapps")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        for posting_id in ((board_id, lane_id) if board_first else (lane_id, board_id)):
            _cross_host(conn, posting_id, "same-job")
    with engine.connect() as conn:
        drained = reconcile_queue(conn, root=root)
    assert drained.to_lane_copy == 1
    assert len(_folders(root / LANE_COPY_DIR)) == 1
    assert len(_folders(root)) == 1


# ---------------------------------------------- the Greenhouse application form's hard stops (T91)


#: A real Greenhouse posting URL, which is what `parse_posting_target` needs to resolve
#: `(provider, slug, posting_ref)`. `APPLY_URL` above is deliberately NOT one — it is an opaque
#: `boards.test` link — so every other fixture in this module reads as "not a Greenhouse lead".
GREENHOUSE_URL = "https://job-boards.greenhouse.io/tenet3/jobs/8810809002"

#: The tenet3 citizenship question, verbatim from the live payload (see `test_form_questions.py`).
CITIZENSHIP_QUESTION = (
    "This position requires current U. S. citizenship in order to achieve and maintain a "
    "security clearance. Are you currently a U. S. citizen?"
)


def _questions_payload(*labels: str) -> bytes:
    return json.dumps(
        {
            "id": 8810809002,
            "questions": [
                {"label": label, "description": None, "required": True, "fields": []}
                for label in labels
            ],
            # Present so the exclusion has something to exclude on the integrated path too.
            "compliance": [{"type": "eeoc", "description": "&lt;p&gt;CC-305&lt;/p&gt;", "questions": []}],
        }
    ).encode()


class _FormFetcher:
    """Counts GETs and answers each with a queued response. Not the real `Fetcher`: the point of
    every test below is what the sweep ASKS FOR and how often, and a real client would put this
    suite on the network."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def get(self, url: str) -> object:
        self.urls.append(url)
        answer = self.responses.pop(0) if self.responses else self.responses
        if isinstance(answer, Exception):
            raise answer
        return answer


class _FormResult:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.not_modified = False


def test_a_greenhouse_lead_whose_form_states_a_hard_stop_lands_in_review(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The whole path, end to end: fetch, cache, match, lane, folder, sidecar.

    This is the class the change exists for. The lead's BODY is the ordinary `JD` fixture — no
    citizenship, no clearance, no ITAR, nothing the eligibility engine could read — so before the
    sweep it is a confirmed-US, confirmed-software, `eligible` lead sitting in the blind-apply
    queue, which is exactly where the three live leads of 2026-09-17 were. The only new evidence
    is the application form, and it is enough to hold it.
    """
    with engine.begin() as conn:
        held_id, _ = _deliver(conn, apps, "held", company="Tenet Co", url=GREENHOUSE_URL)
        _deliver(conn, apps, "clear", company="Clear Co")

    fetcher = _FormFetcher(_FormResult(_questions_payload(CITIZENSHIP_QUESTION)))
    with engine.connect() as conn:
        # Before: nothing is held, so the hold below is the form's doing and not the fixture's.
        assert delivered_unapplied(conn, skipped=set())[0].form_question_hit is None
        sweep = sweep_form_questions(conn, fetcher=fetcher, budget=100)  # type: ignore[arg-type]
        sync_queue(conn, root=root, owner_name=OWNER)

    assert sweep == FormQuestionSweep(candidates=1, cached=0, fetched=1)
    assert fetcher.urls == [
        "https://boards-api.greenhouse.io/v1/boards/tenet3/jobs/8810809002?questions=true"
    ]
    # The non-Greenhouse lead is untouched and still blindly appliable: the gate reaches one
    # provider by construction and must not disturb the rest of the queue.
    assert _folders(root) == ["Clear_Co_Software_Engineer"]
    assert _folders(root / REVIEW_DIR) == ["Tenet_Co_Software_Engineer"]

    details = _details(root / REVIEW_DIR / "Tenet_Co_Software_Engineer")
    assert details["review_reason"] == "form_question_hard_stop"
    # The EVIDENCE travels with the reason, and it has to: this reason names a requirement the
    # `job-description.txt` in the same folder does not state, so a reader who cannot see the
    # question concludes the gate misfired.
    assert details["form_question"] == CITIZENSHIP_QUESTION
    jd = (root / REVIEW_DIR / "Tenet_Co_Software_Engineer" / JD_FILE).read_text(encoding="utf-8")
    assert "citizen" not in jd.lower() and "clearance" not in jd.lower()
    # And it writes NO verdict: the form is not the frozen JD, so `INELIGIBLE` is unreachable
    # here however clear the question is.
    with engine.connect() as conn:
        assert {r.posting_id: r.verdict for r in delivered_unapplied(conn, skipped=set())}[
            held_id
        ] == "eligible"


def test_a_form_with_no_hard_stop_leaves_the_lead_in_the_apply_queue(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The control that must stay GREEN, and the arm a hold-every-Greenhouse-lead mutant fails.
    A fetched form is not a hold — 22 of 400 apply-lane leads are Greenhouse rows, and holding
    them all would cost the owner 21 real applications to catch one."""
    with engine.begin() as conn:
        _deliver(conn, apps, "ordinary", company="Ordinary Co", url=GREENHOUSE_URL)

    fetcher = _FormFetcher(_FormResult(_questions_payload("First Name", "LinkedIn Profile")))
    with engine.connect() as conn:
        sweep = sweep_form_questions(conn, fetcher=fetcher, budget=100)  # type: ignore[arg-type]
        sync_queue(conn, root=root, owner_name=OWNER)

    assert sweep.fetched == 1
    assert _folders(root) == ["Ordinary_Co_Software_Engineer"]
    assert _details(_sole_folder(root))["form_question"] is None


def test_the_form_is_asked_for_once_per_posting_version_and_never_again(
    engine: Engine, root: Path, apps: Path
) -> None:
    """THE CACHE, and it is priced in requests rather than in rows: `sync_queue` runs at the end of
    every run, at web-server start-up and after every mark-applied, so a per-run GET per lead would
    be hundreds of requests a day against a host we promise 1 req/s.

    The second sweep reads the same 1 candidate and issues NO request. The match is still made —
    the catalog is applied on READ, over the stored payload — so the lead stays held.
    """
    with engine.begin() as conn:
        _deliver(conn, apps, "cached", company="Cached Co", url=GREENHOUSE_URL)

    fetcher = _FormFetcher(_FormResult(_questions_payload(CITIZENSHIP_QUESTION)))
    with engine.connect() as conn:
        first = sweep_form_questions(conn, fetcher=fetcher, budget=100)  # type: ignore[arg-type]
        second = sweep_form_questions(conn, fetcher=fetcher, budget=100)  # type: ignore[arg-type]
        sync_queue(conn, root=root, owner_name=OWNER)

    assert first == FormQuestionSweep(candidates=1, fetched=1)
    assert second == FormQuestionSweep(candidates=1, cached=1)
    assert len(fetcher.urls) == 1
    assert _folders(root / REVIEW_DIR) == ["Cached_Co_Software_Engineer"]


@pytest.mark.parametrize(
    "failure",
    [FetchFailure("HTTP 500 after 3 attempts", status_code=500), TimeoutError("read timeout")],
    ids=["http-500", "timeout"],
)
def test_a_board_that_will_not_answer_never_holds_the_lead(
    engine: Engine, root: Path, apps: Path, failure: Exception
) -> None:
    """FAIL-OPEN, counted. This is the safety argument for putting a network read on the delivery
    path at all: an error is "no questions known", reported as `unfetched`, and the lead rides on
    into the apply queue exactly as it did before this gate existed. The opposite direction would
    cost the owner a real application every time a board 500s."""
    with engine.begin() as conn:
        _deliver(conn, apps, "unreachable", company="Silent Board Co", url=GREENHOUSE_URL)

    fetcher = _FormFetcher(failure)
    with engine.connect() as conn:
        sweep = sweep_form_questions(conn, fetcher=fetcher, budget=100)  # type: ignore[arg-type]
        sync_queue(conn, root=root, owner_name=OWNER)

    assert sweep == FormQuestionSweep(candidates=1, unfetched=1)
    assert _folders(root) == ["Silent_Board_Co_Software_Engineer"]
    assert _folders(root / REVIEW_DIR) == []
    # And it is RETRYABLE: a failure is not cached, so the next run asks again rather than
    # treating one bad minute as a permanent answer about this requisition.
    with engine.connect() as conn:
        assert sweep_form_questions(
            conn, fetcher=_FormFetcher(failure), budget=100  # type: ignore[arg-type]
        ) == FormQuestionSweep(candidates=1, unfetched=1)


def test_the_budget_bounds_the_requests_and_reports_what_it_refused(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A budget that silently dropped the remainder would make a throttled run indistinguishable
    from a queue with no hard stops in it. `0` is a real setting and disarms the sweep, reporting
    the whole candidate population as refused."""
    with engine.begin() as conn:
        for key in ("one", "two", "three"):
            _deliver(conn, apps, key, company=f"Co {key}", url=GREENHOUSE_URL)

    payloads = [_FormResult(_questions_payload("First Name")) for _ in range(3)]
    with engine.connect() as conn:
        assert sweep_form_questions(
            conn, fetcher=_FormFetcher(*payloads), budget=0  # type: ignore[arg-type]
        ) == FormQuestionSweep(candidates=3, budget_refused=3)
        bounded = _FormFetcher(*payloads)
        assert sweep_form_questions(conn, fetcher=bounded, budget=2) == FormQuestionSweep(  # type: ignore[arg-type]
            candidates=3, fetched=2, budget_refused=1
        )
        assert len(bounded.urls) == 2
        # The third lead is picked up by the NEXT run, and the two already stored cost nothing.
        assert sweep_form_questions(
            conn, fetcher=_FormFetcher(*payloads), budget=2  # type: ignore[arg-type]
        ) == FormQuestionSweep(candidates=3, cached=2, fetched=1)


def test_a_closed_greenhouse_lead_is_never_asked_about(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A dead requisition gets no GET. `classify` drains it above the form branch (D-383), so no
    answer could move it, and asking would spend the budget on work that cannot exist."""
    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "gone", company="Gone Co", url=GREENHOUSE_URL)
        conn.execute(
            postings.update().where(postings.c.id == posting_id).values(status="closed")
        )

    fetcher = _FormFetcher()
    with engine.connect() as conn:
        assert sweep_form_questions(
            conn, fetcher=fetcher, budget=100  # type: ignore[arg-type]
        ) == FormQuestionSweep(candidates=0)
    assert fetcher.urls == []


def test_the_pipeline_makes_no_form_request_unless_a_caller_supplies_a_fetcher(
    engine: Engine, apps: Path
) -> None:
    """The sweep is INJECTED, never built inside the pipeline — and this is a property of the
    GATE, not only of the API.

    `make check` runs on three operating systems and must make no request of its own, while
    fixtures across this suite carry real `boards.greenhouse.io` posting URLs (this module's own
    `GREENHOUSE_URL` among them, on a lead this very test delivers). A `Fetcher` constructed
    inside `_sync_queue` would put the gate on the network the first time one of them reached a
    delivered lead — silently, and only on whichever machine happened to have connectivity.
    `run_cmd` supplies the one fetcher that exists, exactly as it supplies the liveness prober and
    for the same recorded reason.

    Run against a REAL connection holding a real Greenhouse candidate, so the two arms cannot
    pass by failing earlier: the no-fetcher arm has something it could have asked about, and the
    absence of a cached row is the evidence it did not.
    """
    from rich.console import Console  # noqa: PLC0415

    from boardwatch.pipeline import runner as runner_mod  # noqa: PLC0415
    from boardwatch.store.form_question_queries import cached_form_questions  # noqa: PLC0415

    class _Explode:
        def get(self, url: str) -> object:
            raise AssertionError(f"the gate must not fetch: {url}")

    with engine.begin() as conn:
        posting_id, _ = _deliver(conn, apps, "offline", company="Offline Co", url=GREENHOUSE_URL)

    settings = load_settings()
    # Controls: neither arm below can pass through the budget guard by accident, and the lead
    # really is a candidate the sweep would otherwise ask about.
    assert settings.form_question_fetch_budget > 0
    console = Console(quiet=True)
    with engine.connect() as conn:
        version = current_posting_versions(conn, [posting_id])[posting_id]
        assert sweep_form_questions(
            conn, fetcher=_FormFetcher(_FormResult(_questions_payload(CITIZENSHIP_QUESTION))),
            budget=0,
        ) == FormQuestionSweep(candidates=1, budget_refused=1)  # type: ignore[arg-type]

        # No fetcher -> UNMEASURED, and nothing is asked. `None` rather than a zeroed report,
        # because "nobody asked" and "asked and found nothing" are different facts.
        assert (
            runner_mod._sweep_form_questions(
                conn, settings, console, None, runner_mod.PipelineSummary(run_id=1)
            )
            is None
        )
        # The budget disarms it even when a caller DOES supply one, without the exploding fetcher
        # being reached.
        disarmed = settings.model_copy(update={"form_question_fetch_budget": 0})
        assert (
            runner_mod._sweep_form_questions(
                conn, disarmed, console, _Explode(), runner_mod.PipelineSummary(run_id=1)  # type: ignore[arg-type]
            )
            is None
        )
        # And neither call stored anything, which is what says no request was made.
        assert cached_form_questions(conn, [version.posting_version_id]) == {}


def test_a_form_sweep_that_raises_is_recorded_on_the_run_and_not_only_printed(
    engine: Engine, apps: Path
) -> None:
    """A swept-nothing run must not read as a found-nothing run (T134).

    `_sweep_form_questions` fail-opens — that direction is right, the queue holds COPIES of work
    the run already delivered — but fail-open and silent are different things. A console line in
    a log nobody opens is the only trace a failed sweep used to leave, so a run that asked no
    board anything was byte-identical, everywhere a gate reads, to a run whose whole queue was
    clean. The note is NON-FATAL: the run still succeeds.
    """
    from rich.console import Console  # noqa: PLC0415

    from boardwatch.pipeline import runner as runner_mod  # noqa: PLC0415

    def _boom(conn: Connection, *, fetcher: object, budget: int) -> None:
        raise RuntimeError("the store refused the sweep")

    settings = load_settings()
    assert settings.form_question_fetch_budget > 0  # control: the budget cannot disarm this
    summary = runner_mod.PipelineSummary(run_id=1)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(runner_mod, "sweep_form_questions", _boom)
    try:
        with engine.connect() as conn:
            result = runner_mod._sweep_form_questions(
                conn, settings, Console(quiet=True), _FormFetcher(), summary  # type: ignore[arg-type]
            )
    finally:
        monkeypatch.undo()

    assert result is None
    assert summary.errors == [
        "application forms: sweep failed (RuntimeError: the store refused the sweep)"
    ]
    # Non-fatal: `run_pipeline` stamps `failed` only on `summary.fatal`, so the run stays `ok`.
    assert summary.fatal is None


# --- T134: the sweep holds no read transaction across the network -------------------------


#: A second Greenhouse posting, so a sweep can have two responses to file separately.
GREENHOUSE_URL_TWO = "https://job-boards.greenhouse.io/tenet3/jobs/8810809003"


class _InterposingFetcher(_FormFetcher):
    """A fetcher that records whether the sweep's connection is mid-transaction, and commits an
    unrelated write before answering.

    Both halves matter and they check different things. `in_transaction` is the STRUCTURAL
    assertion — a sweep holding a DEFERRED read snapshot across a GET has a transaction open
    here. The unrelated commit is what turns that into the observable fault: SQLite cannot
    upgrade an obsolete snapshot, so the sweep's own next write would raise
    `SQLITE_BUSY_SNAPSHOT`, which `busy_timeout` does not retry.
    """

    def __init__(self, conn: Connection, engine: Engine, *responses: object) -> None:
        super().__init__(*responses)
        self._conn = conn
        self._engine = engine
        self.in_transaction: list[bool] = []

    def get(self, url: str) -> object:
        self.in_transaction.append(self._conn.in_transaction())
        insert_run(self._engine)  # an unrelated writer, committed mid-fetch
        return super().get(url)


def test_the_form_sweep_opens_no_transaction_across_the_fetch(
    engine: Engine, root: Path, apps: Path
) -> None:
    """A single unrelated commit during a GET must not cost the whole sweep (T134).

    An aborted sweep leaves every uncached form unfetched, and an unasked hard stop is
    fail-open — the lead rides into the blind-apply queue, which is the T91 class this module
    exists to catch. So the read transaction ends when the reads do, before any HTTP.
    """
    with engine.begin() as conn:
        _deliver(conn, apps, "one", company="One Co", url=GREENHOUSE_URL)
        _deliver(conn, apps, "two", company="Two Co", url=GREENHOUSE_URL_TWO)

    payloads = [_FormResult(_questions_payload("First Name")) for _ in range(2)]
    with engine.connect() as conn:
        fetcher = _InterposingFetcher(conn, engine, *payloads)
        sweep = sweep_form_questions(conn, fetcher=fetcher, budget=100)  # type: ignore[arg-type]

    assert sweep == FormQuestionSweep(candidates=2, fetched=2)
    # Structural: no transaction is open at either call, so there is no snapshot to go obsolete.
    assert fetcher.in_transaction == [False, False]
    # And both responses actually landed, which is what says the interposed writer cost nothing.
    with engine.connect() as conn:
        version_ids = [
            v.posting_version_id
            for v in current_posting_versions(
                conn, [row.posting_id for row in delivered_unapplied(conn, skipped=set())]
            ).values()
        ]
        assert sorted(cached_form_questions(conn, version_ids)) == sorted(version_ids)


def test_a_form_response_that_lands_stays_committed_when_the_next_one_raises(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Per-response transactions, stated as the property that needs them (T134).

    The first response is durable the moment it is written; a fault on the second cannot take it
    back. Without that, a sweep is all-or-nothing across a network pass and one bad write throws
    away every GET the run already spent.
    """
    with engine.begin() as conn:
        _deliver(conn, apps, "one", company="One Co", url=GREENHOUSE_URL)
        _deliver(conn, apps, "two", company="Two Co", url=GREENHOUSE_URL_TWO)
    with engine.connect() as conn:
        by_posting = current_posting_versions(
            conn, [row.posting_id for row in delivered_unapplied(conn, skipped=set())]
        )
    version_ids = [v.posting_version_id for v in by_posting.values()]

    from boardwatch.store import form_question_queries  # noqa: PLC0415

    real = form_question_queries.record_form_questions
    recorded: list[int] = []

    def _second_write_fails(
        conn: Connection, posting_version_id: int, questions_json: list[dict[str, object]]
    ) -> None:
        if recorded:
            raise RuntimeError("the store refused the second response")
        recorded.append(posting_version_id)
        real(conn, posting_version_id, questions_json)

    payloads = [_FormResult(_questions_payload("First Name")) for _ in range(2)]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(form_question_queries, "record_form_questions", _second_write_fails)
    try:
        with engine.connect() as conn:
            fetcher = _InterposingFetcher(conn, engine, *payloads)
            with pytest.raises(RuntimeError, match="refused the second response"):
                sweep_form_questions(conn, fetcher=fetcher, budget=100)  # type: ignore[arg-type]
    finally:
        monkeypatch.undo()

    with engine.connect() as conn:
        cached = cached_form_questions(conn, version_ids)
    assert list(cached) == recorded, "the response that landed must survive the one that did not"
    assert len(cached) == 1

# ------------------------------------ T109: the standing lane's title band and the judge's NO


#: A body the judge's `ineligible` is quoted from. It is NOT the posting body the deterministic
#: engine reads (`JD`), and it does not need to be: `record_gate_verdict` uses `jd_text` only as
#: the keystone span source, while `current_gate_verdicts` keys purely on the frozen version and
#: the judge's inputs. Keeping them apart is what lets the fixture hold a DETERMINISTIC `eligible`
#: and a JUDGE `ineligible` on one lead, which is the whole population this ticket is about.
JUDGE_JD = "This position requires an active Top Secret security clearance."
JUDGE_EVIDENCE = "requires an active Top Secret security clearance"


@dataclass(frozen=True)
class _Standing:
    """What each of the four standing readers says about ONE delivered lead.

    Read through four independent paths on purpose. They are the four call sites that must agree,
    and each has its own fixtures elsewhere in the suite — so a hold that reaches one of them and
    not the others is exactly the D-332 failure nothing else in the suite would catch.
    """

    #: The COMPUTED title-band bit on the row itself, read before any lane call — so the four
    #: routings below cannot all be wrong together with the input they are derived from.
    band_bit: bool
    folder: str
    review_reason: str | None
    detail_reason: str | None
    in_review_ids: bool
    in_apply_lane: bool


def _read_standing(engine: Engine, root: Path, apps: Path, posting_id: int, job_id: int) -> _Standing:
    from boardwatch.delivery.api import ApiContext, detail_payload, queue_payload  # noqa: PLC0415
    from boardwatch.store.delivery_queries import (  # noqa: PLC0415
        apply_lane_placements,
        review_job_ids,
    )

    with engine.begin() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    ctx = ApiContext(
        settings=load_settings(),
        out_root=apps.resolve(),
        queue_root=root.resolve(),
        owner_name=OWNER,
        platform="darwin",
    )
    with engine.connect() as conn:
        page = queue_payload(conn, ctx)
        detail = detail_payload(conn, ctx, posting_id)
        held = review_job_ids(conn)
        standing = {row.posting_id: row for row in delivered_unapplied(conn, skipped=set())}
        run_ids = {
            row.delivered_run_id for row in standing.values() if row.delivered_run_id is not None
        }
        placements = apply_lane_placements(conn, run_ids=run_ids)
    assert detail is not None
    rows = {int(row["posting_id"]): row for row in page["rows"] + page["review"]}
    return _Standing(
        band_bit=standing[posting_id].seniority_above_band,
        folder=_folder_of(root, posting_id),
        review_reason=rows[posting_id]["review_reason"],
        detail_reason=detail["row"]["review_reason"],
        in_review_ids=job_id in held,
        in_apply_lane=any(in_apply for _placeable, in_apply in placements.values()),
    )


def _folder_of(root: Path, posting_id: int) -> str:
    """Which lane directory `sync_queue` filed this lead's folder under (`""` is the apply queue).

    Identified by the `posting_id` inside `details.json`, never by the folder NAME, exactly as
    `queue.py:_index` does — the name is a projection of the title and says nothing about lanes.
    """
    for details in root.rglob(DETAILS_FILE):
        if json.loads(details.read_text(encoding="utf-8"))["posting_id"] == posting_id:
            parent = details.parent.parent
            return "" if parent == root else parent.name
    raise AssertionError(f"no queue folder holds posting {posting_id}")


def _narrow_the_target_band(engine: Engine) -> None:
    """Move the operator's target band from `any` to `entry`, as `boardwatch profile` would.

    `target_seniority_band` is NOT part of `profile_hash` — that hashes the eligibility facts,
    the policy, the rules catalog and the declared fields — so every stored evaluation survives
    this and the lead keeps the verdict it was delivered with. Without that the lead would route
    to review under `unevaluated` and the assertion below would pass for the wrong reason.
    """
    from boardwatch.store.tables import profile  # noqa: PLC0415

    with engine.begin() as conn:
        conn.execute(update(profile).values(target_seniority_band="entry"))


def _judge(
    engine: Engine,
    posting_id: int,
    *,
    decision: str,
    reason: str = "work_auth",
    jd: str = JUDGE_JD,
    evidence: str = JUDGE_EVIDENCE,
) -> None:
    """Persist one FINAL-GATE verdict against this lead's current version, as the daily stage
    writes it: the stored facts, the configured judge, the live identity."""
    from boardwatch.eligibility import final_gate  # noqa: PLC0415
    from boardwatch.eligibility.oracle import OracleVerdict  # noqa: PLC0415

    with engine.begin() as conn:
        version = current_posting_versions(conn, [posting_id])[posting_id]
        final_gate.record_gate_verdict(
            conn,
            posting_version_id=version.posting_version_id,
            jd_text=jd,
            facts=FACTS,
            policy=POLICY,
            catalog=load_rules(load_settings().config_dir),
            verdict=OracleVerdict(
                label=str(posting_id), decision=decision, reason=reason,
                evidence=evidence, confidence="high",
            ),
            model=load_settings().gate.model,
        )


def test_a_narrowed_target_band_holds_a_STANDING_lead_in_every_reader(
    engine: Engine, root: Path, apps: Path
) -> None:
    """T109 part 1. The title-seniority hold must reach the standing queue, not only the run.

    `pipeline/runner._lead_lanes` computes the band and passes it; the four standing readers did
    not, so `classify`'s `seniority_above_band` defaulted False for every lead already delivered.
    The case that matters is exactly this one and it is unreachable from the run path — the
    ranker hides an above-band posting BEFORE delivery (see
    `tests/pipeline/test_lane_split_before_tailor.py`), so the only way a senior title is standing
    in the apply lane is that it was delivered while the band was `any` and the band narrowed
    afterwards. The band is COMPUTED on every read for that reason; persisting it at delivery
    would freeze the answer the day the operator's target moved.
    """
    with engine.begin() as conn:
        senior, senior_job = _deliver(conn, apps, "senior", title="Principal Software Engineer")

    # The control: while the band is `any` the gate is inert and the lead is blindly appliable.
    before = _read_standing(engine, root, apps, senior, senior_job)
    assert before == _Standing(
        band_bit=False, folder="", review_reason=None, detail_reason=None,
        in_review_ids=False, in_apply_lane=True,
    )

    _narrow_the_target_band(engine)

    after = _read_standing(engine, root, apps, senior, senior_job)
    assert after == _Standing(
        band_bit=True, folder=REVIEW_DIR, review_reason="seniority_above_band",
        detail_reason="seniority_above_band", in_review_ids=True, in_apply_lane=False,
    )


def test_a_current_judge_ineligible_HOLDS_a_standing_lead_in_every_reader(
    engine: Engine, root: Path, apps: Path
) -> None:
    """T109 part 2, and the owner's ruling of 2026-09-19.

    A CURRENT judge `ineligible` holds a standing lead in REVIEW under its own reason. It is never
    equated with a deterministic deletion and it is never dropped: review is the fail-open
    direction D-380 requires for a reading no deterministic rule produced, so the lead stays
    visible and keeps its folder.

    Measured live before it shipped: 45 delivered posting-versions carried a current judge
    `ineligible`, 17 of them ALSO carried a deterministic `eligible` and therefore sat in the
    apply lane on `classify`'s `eligible` short-circuit alone, and 12 of those 17 were open and
    unapplied. The deterministic `eligible` is asserted below rather than assumed, so the fixture
    cannot drift into a verdict that would reach the hold through some other branch.
    """
    with engine.begin() as conn:
        judged, judged_job = _deliver(conn, apps, "judged")

    with engine.connect() as conn:
        (row,) = delivered_unapplied(conn, skipped=set())
    assert row.verdict == "eligible", (
        "the fixture must carry a DETERMINISTIC eligible, or the hold below could be reached by "
        f"a branch under the short-circuit rather than above it; got {row.verdict!r}"
    )

    # The control: with no gate row the lead is blindly appliable, so the move is attributable.
    before = _read_standing(engine, root, apps, judged, judged_job)
    assert before.folder == "" and before.review_reason is None

    _judge(engine, judged, decision="ineligible")

    after = _read_standing(engine, root, apps, judged, judged_job)
    assert after == _Standing(
        band_bit=False, folder=REVIEW_DIR, review_reason="judged_ineligible_verdict",
        detail_reason="judged_ineligible_verdict", in_review_ids=True, in_apply_lane=False,
    )


@pytest.mark.parametrize(
    ("decision", "reason"),
    [("eligible", None), ("uncertain", None)],
    ids=["eligible-releases-nothing-here", "uncertain-is-an-absent-row"],
)
def test_the_other_two_judge_states_leave_a_standing_lead_where_it_was(
    engine: Engine, root: Path, apps: Path, decision: str, reason: str | None
) -> None:
    """The controls, one per remaining judge state. These stop the hold over-reaching.

    A judge `eligible` releases the two requirement holds and nothing else, and an `uncertain`
    behaves exactly as an absent row does — neither may move a lead that nothing else holds.
    """
    with engine.begin() as conn:
        lead, lead_job = _deliver(conn, apps, "control")
    _judge(engine, lead, decision=decision)

    after = _read_standing(engine, root, apps, lead, lead_job)
    assert after == _Standing(
        band_bit=False, folder="", review_reason=reason, detail_reason=reason,
        in_review_ids=False, in_apply_lane=True,
    )


def test_a_closed_lead_reports_no_review_reason_in_the_detail_pane(
    engine: Engine, root: Path, apps: Path
) -> None:
    """`_row_json` omitted `posting_closed`, so the pane answered as though the lead were live.

    A closed lead drains to `_closed`, which carries NO review reason — it is not held for a
    reason drawn from the review catalog, it is simply gone (`LaneDecision`'s own contract). The
    pane was computing the reason the lead WOULD have had were it open and publishing that
    instead, so the one surface where the reader decides whether to apply named a hold the folder
    tree does not agree with. The posting's closure still reaches the page as `status`, which is
    what the closed chip renders.
    """
    from boardwatch.delivery.api import ApiContext, detail_payload  # noqa: PLC0415

    with engine.begin() as conn:
        # `Front Office Agent` carries no software signal, so an OPEN lead here is held for
        # `role_unconfirmed` — that is the reason the pane must stop reporting once it is closed.
        dead, _ = _deliver(conn, apps, "dead", title="Front Office Agent")
        conn.execute(update(postings).where(postings.c.id == dead).values(
            status="closed", closed_at=NOW
        ))
    ctx = ApiContext(
        settings=load_settings(), out_root=apps.resolve(), queue_root=root.resolve(),
        owner_name=OWNER, platform="darwin",
    )
    with engine.connect() as conn:
        detail = detail_payload(conn, ctx, dead)
    assert detail is not None
    assert detail["row"]["status"] == "closed"
    assert detail["row"]["review_reason"] is None


# ---------------------------------------- T161: a gate verdict is keyed on the judge's inputs
#
# The judge is sent the body and the facts, never the catalog or the policy severities, so a
# re-key that moves neither must not darken a verdict — in ANY of the readers that must agree about
# one lead: the folder `sync_queue` files, the web list, the detail pane, `review_job_ids`,
# `apply_lane_placements`, and the RUN's own pre-tailor split. Each re-key is real (the identity
# or the engine digest is asserted to move) and each re-evaluates the deterministic lane under it,
# as the next run's preflight would, so the requirement flags are the CURRENT reading.

#: A body no catalog family reads anything in: the engine's zero-row branch returns `uncertain` and
#: the lane holds the lead `no_requirements_found`, unless a judge `eligible` releases it (0-B).
#: That release is exactly what a rules-only re-key used to strand.
SILENT_JD = "We are hiring a software engineer to build Python services for our platform team."

#: An `internship` hard stop a judge can quote: the evidence is a raw substring of the body.
INTERN_JD = "This is a twelve week summer internship program for current university students."
INTERN_EVIDENCE = "twelve week summer internship program for current university students"


@contextmanager
def _rekeyed(engine: Engine, kind: str) -> Iterator[None]:
    """`rekeyed`, proven to have moved what it claims, with every delivered lead re-evaluated
    under it as the next run's preflight would — so the requirement flags are the CURRENT reading.

    `engine_version` is not part of a gate row's identity at all, so that arm was never dark: it
    is the control, and the claim it pins is T163's (a detector edit must not darken a verdict).
    """
    from boardwatch.eligibility.preflight import current_identity  # noqa: PLC0415
    from tests.pipeline.test_llm_cache_identity import rekeyed  # noqa: PLC0415

    settings = load_settings()
    with engine.connect() as conn:
        before = current_identity(conn, settings)
    with rekeyed(settings.config_dir, kind):
        with engine.connect() as conn:
            after = current_identity(conn, settings)
        assert before is not None and after is not None
        assert after[0] == before[0]
        assert (after[1] != before[1]) == (kind == "rules_hash")
        with engine.begin() as conn:
            for version in current_posting_versions(conn, None).values():
                _judge_version(conn, version.posting_version_id, version.body_text)
        yield


def _row_of(engine: Engine, posting_id: int) -> QueueRow:
    with engine.connect() as conn:
        return next(
            row for row in delivered_unapplied(conn, skipped=set()) if row.posting_id == posting_id
        )


def _run_lane(engine: Engine, row: QueueRow) -> tuple[str, int]:
    """(the lane the RUN's pre-tailor split gives this lead, its count of leads with NO readable
    gate reading — the funnel's `gate.readings_absent`), from `runner._lead_lanes` fed the
    deterministic verdict the ranker would carry for the lead, which is the row's own."""
    lanes, absent, _tenant = runner_mod._lead_lanes(
        engine, load_settings(),
        [
            SimpleNamespace(  # type: ignore[list-item]
                posting_id=row.posting_id, verdict=row.verdict, title=row.title, role=row.role
            )
        ],
    )
    return lanes[row.posting_id][0], absent


@pytest.mark.parametrize("kind", ["rules_hash", "engine_version"])
def test_a_judge_eligible_keeps_its_lead_in_the_apply_lane_through_a_rekey(
    engine: Engine, root: Path, apps: Path, kind: str
) -> None:
    """T161 tests 1 and 3. A judge `eligible` releases a `no_requirements_found` hold (0-B); a
    re-key that leaves the judge's inputs alone must leave the lead released in every reader —
    and the run's own split must put it in the same lane as the queue, or the run would tailor
    (or skip) a lead `sync_queue` then files the other way (the T127 property, third caller).
    The split also counts the reading PRESENT, so the funnel's `gate.readings_absent` reads 0
    dark verdicts after the re-key rather than one per standing lead.
    """
    with engine.begin() as conn:
        lead, lead_job = _deliver(conn, apps, "silent", body=SILENT_JD)
    held = _read_standing(engine, root, apps, lead, lead_job)
    assert held.review_reason == "no_requirements_found", "the judge must be what releases it"
    _judge(engine, lead, decision="eligible")
    released = _read_standing(engine, root, apps, lead, lead_job)
    assert released == _Standing(
        band_bit=False, folder="", review_reason=None, detail_reason=None,
        in_review_ids=False, in_apply_lane=True,
    )

    with _rekeyed(engine, kind):
        assert _read_standing(engine, root, apps, lead, lead_job) == released
        row = _row_of(engine, lead)
        assert (row.verdict, row.judge_verdict) == ("uncertain", "eligible")
        assert _run_lane(engine, row) == (lane_decision(row).lane, 0) == ("", 0)


@pytest.mark.parametrize("kind", ["rules_hash", "engine_version"])
def test_a_judge_ineligible_keeps_holding_its_lead_through_a_rekey(
    engine: Engine, root: Path, apps: Path, kind: str
) -> None:
    """T161 tests 2 and 3, and the owner's ruling (2026-09-23): the judge's holds are KEPT through
    a re-key, not released as D-537 measured them releasing. The lead carries a DETERMINISTIC
    `eligible`, so if the judge's reading went dark it would ride the short-circuit straight
    into the blind-apply queue in every reader."""
    with engine.begin() as conn:
        judged, judged_job = _deliver(conn, apps, "judged")
    _judge(engine, judged, decision="ineligible")
    holding = _Standing(
        band_bit=False, folder=REVIEW_DIR, review_reason="judged_ineligible_verdict",
        detail_reason="judged_ineligible_verdict", in_review_ids=True, in_apply_lane=False,
    )
    assert _read_standing(engine, root, apps, judged, judged_job) == holding

    with _rekeyed(engine, kind):
        assert _read_standing(engine, root, apps, judged, judged_job) == holding
        row = _row_of(engine, judged)
        assert (row.verdict, row.judge_verdict) == ("eligible", "ineligible")
        assert _run_lane(engine, row) == (lane_decision(row).lane, 0) == (REVIEW_DIR, 0)


def test_a_judge_ineligible_whose_family_left_the_catalog_releases_its_hold(
    engine: Engine, root: Path, apps: Path
) -> None:
    """T161 test 6 through the lane (design §3). The catalog drops `internship`, so an `ineligible`
    citing it is a verdict no current family supports: every reader sees `uncertain`, which holds
    nothing, and the lead's deterministic `eligible` puts it in the apply lane. CONTROL, in the
    same store under the same catalog: an `ineligible` citing `work_auth` still holds."""
    import yaml  # noqa: PLC0415

    from boardwatch.eligibility.catalog import bundled_rules_text  # noqa: PLC0415

    with engine.begin() as conn:
        intern, intern_job = _deliver(conn, apps, "intern")
        control, control_job = _deliver(conn, apps, "control")
    _judge(engine, intern, decision="ineligible", reason="internship", jd=INTERN_JD,
           evidence=INTERN_EVIDENCE)
    _judge(engine, control, decision="ineligible")
    assert _row_of(engine, intern).judge_verdict == "ineligible"

    document = yaml.safe_load(bundled_rules_text())
    document["families"] = [f for f in document["families"] if f["id"] != "internship"]
    config_dir = load_settings().config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "rules.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    assert "internship" not in {f.id for f in load_rules(config_dir).families}
    with engine.begin() as conn:
        for version in current_posting_versions(conn, None).values():
            _judge_version(conn, version.posting_version_id, version.body_text)

    assert _row_of(engine, intern).judge_verdict == "uncertain"
    assert _read_standing(engine, root, apps, intern, intern_job) == _Standing(
        band_bit=False, folder="", review_reason=None, detail_reason=None,
        in_review_ids=False, in_apply_lane=True,
    )
    assert _row_of(engine, control).judge_verdict == "ineligible"
    assert _read_standing(engine, root, apps, control, control_job).review_reason == (
        "judged_ineligible_verdict"
    )


def test_with_no_profile_no_reader_finds_a_gate_verdict(engine: Engine, apps: Path) -> None:
    """T161 test 9, and a CONTROL on both sides of the change (the identity-scoped read returned
    `{}` for a missing profile too): with no profile there are no facts, so no reader finds the
    verdict — the list, the pane and the run's split alike — and the split counts it absent."""
    from boardwatch.store.delivery_queries import queue_detail  # noqa: PLC0415
    from boardwatch.store.tables import profile  # noqa: PLC0415

    with engine.begin() as conn:
        judged, _ = _deliver(conn, apps, "judged")
    _judge(engine, judged, decision="ineligible")
    assert _row_of(engine, judged).judge_verdict == "ineligible"

    with engine.begin() as conn:
        conn.execute(profile.delete())
    row = _row_of(engine, judged)
    with engine.connect() as conn:
        detail = queue_detail(conn, judged)
    assert detail is not None
    assert (row.judge_verdict, detail.row.judge_verdict) == (None, None)
    lanes, absent, _tenant = runner_mod._lead_lanes(
        engine, load_settings(),
        [SimpleNamespace(posting_id=judged, verdict=None, title=row.title, role=row.role)],  # type: ignore[list-item]
    )
    assert absent == 1
    assert lanes[judged][0] == REVIEW_DIR


# ------------------------------------------------------ one lock hold, one snapshot (T135, F3)
#
# The runner's queue pass and `prime_queue` reconcile and then sync. Before T135 each half took and
# released the lock on its own, on ONE connection whose read snapshot was pinned at its first
# SELECT, so a web action committed in between was invisible to the sync half — which then pulled
# the folder the web had just drained straight back out. Every test below drives the real entry
# point; the only thing patched is a barrier, and each barrier asserts it fired.


def _web_action(data_dir: Path, action: str, *, posting_id: int, job_id: int) -> None:
    """What `server._write` commits for each route, on its own read-write engine."""
    eng = get_engine(data_dir)
    try:
        with eng.begin() as conn:
            if action == "skip":
                mark_job_skipped(conn, job_id=job_id, at=NOW)
            elif action == "unskip":
                unmark_job_skipped(conn, job_id=job_id)
            else:
                mark_job_applied(conn, posting_id=posting_id, source="test")
    finally:
        eng.dispose()


def _web_reconcile(data_dir: Path, root: Path) -> ReconcileReport:
    """`server._reconcile`: one `reconcile_queue` on a fresh read-only connection."""
    eng = get_readonly_engine(data_dir)
    try:
        with eng.connect() as conn:
            return reconcile_queue(conn, root=root)
    finally:
        eng.dispose()


#: Where each web action says the folder belongs once it has committed.
_LANE_AFTER = {"skip": SKIPPED_DIR, "unskip": "", "applied": APPLIED_DIR}


def _persisted(engine: Engine, action: str, job_id: int) -> bool:
    with engine.connect() as conn:
        if action == "applied":
            return job_id in set(applied_job_ids(conn))
        return (job_id in set(skipped_job_ids(conn))) == (action == "skip")


def _drive(driver: str, engine: Engine, root: Path, apps: Path) -> None:
    if driver == "runner":
        runner_mod._sync_queue(
            engine, load_settings(), Console(file=io.StringIO()), queue_root=root
        )
    else:
        prime_queue(
            ApiContext(
                settings=load_settings(), out_root=apps.resolve(), queue_root=root.resolve(),
                owner_name=OWNER, platform="darwin",
            )
        )


def _between_passes(mp: pytest.MonkeyPatch, hook: Callable[[], None]) -> dict[str, bool]:
    """Run `hook` once, after the reconcile pass and before the sync pass does anything.

    "Before sync" is whichever comes first: sync asking for the lock (the two-hold shape) or
    `_sync_locked` being entered (a single hold). The barrier does not presume which shape the
    code has, so the same test reads both.
    """
    state = {"reconciled": False, "fired": False}
    real_reconcile, real_sync, real_lock = (
        queue._reconcile_locked, queue._sync_locked, queue._queue_lock,
    )

    def fire() -> None:
        if state["reconciled"] and not state["fired"]:
            state["fired"] = True
            hook()

    def reconcile_locked(conn: Connection, *, root: Path, owner_name: str = "") -> ReconcileReport:
        report = real_reconcile(conn, root=root, owner_name=owner_name)
        state["reconciled"] = True
        return report

    @contextmanager
    def lock(root: Path) -> Iterator[Path]:
        fire()
        with real_lock(root) as path:
            yield path

    def sync_locked(conn: Connection, *, root: Path, owner_name: str) -> queue.SyncReport:
        fire()
        return real_sync(conn, root=root, owner_name=owner_name)

    mp.setattr(queue, "_reconcile_locked", reconcile_locked)
    mp.setattr(queue, "_queue_lock", lock)
    mp.setattr(queue, "_sync_locked", sync_locked)
    return state


@pytest.mark.parametrize("action", ["skip", "applied"])
@pytest.mark.parametrize("driver", ["runner", "prime_queue"])
def test_a_web_action_between_the_two_passes_is_never_silently_reversed(
    engine: Engine, root: Path, apps: Path, tmp_path: Path, driver: str, action: str
) -> None:
    """F3's three steps. The web commits and reconciles between the runner's two passes.

    Whatever the web reconcile reports is allowed, EXCEPT a move that the runner then undoes: that
    is the owner's completed action reverting on disk while every report reads healthy. Unskip is
    not here because the sync half never moves a folder for a withheld job, so this shape cannot
    reverse it; the snapshot test below is the one that exposes unskip.
    """
    data_dir = tmp_path / "data"
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name
    lane = _LANE_AFTER[action]
    web: list[ReconcileReport] = []

    def hook() -> None:
        _web_action(data_dir, action, posting_id=posting_id, job_id=job_id)
        web.append(_web_reconcile(data_dir, root))

    with pytest.MonkeyPatch.context() as mp:
        state = _between_passes(mp, hook)
        _drive(driver, engine, root, apps)

    assert state["fired"] and len(web) == 1, "the barrier never ran, so nothing was tested"
    assert _persisted(engine, action, job_id)
    if web[0].moved:
        assert _folders(root / lane) == [folder], (
            f"the web reported the folder moved into {lane!r} and the {driver} pulled it back out"
        )
    assert web[0].contended, "the web pass ran between the two halves of one plan"

    followup = _web_reconcile(data_dir, root)
    assert (followup.moved, followup.failed) == (1, 0)
    assert _folders(root / lane) == [folder]
    assert _folders(root) == []
    assert _persisted(engine, action, job_id)


@pytest.mark.parametrize("action", ["skip", "unskip", "applied"])
def test_an_action_committed_before_the_lock_is_filed_by_the_same_pass(
    engine: Engine, root: Path, apps: Path, tmp_path: Path, action: str
) -> None:
    """The snapshot must be taken AFTER the lock. A commit that lands after the runner's first
    read (`resolve_owner_name`) but before it holds the lock is visible to this pass."""
    data_dir = tmp_path / "data"
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name
    if action == "unskip":
        _web_action(data_dir, "skip", posting_id=posting_id, job_id=job_id)
        _web_reconcile(data_dir, root)
        assert _folders(root / SKIPPED_DIR) == [folder]
    lane = _LANE_AFTER[action]
    real = runner_mod.resolve_owner_name
    fired: list[bool] = []

    def owner_then_commit(conn: Connection | None, config_dir: Path) -> str:
        name = real(conn, config_dir)
        _web_action(data_dir, action, posting_id=posting_id, job_id=job_id)
        fired.append(True)
        return name

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runner_mod, "resolve_owner_name", owner_then_commit)
        _drive("runner", engine, root, apps)

    assert fired, "the commit never landed, so nothing was tested"
    assert _persisted(engine, action, job_id)
    assert _folders(root / lane) == [folder], (
        f"a {action} committed before the lock was taken was not filed by this pass"
    )


def test_a_commit_while_the_runner_holds_the_lock_is_contended_and_repaired_next_time(
    engine: Engine, root: Path, apps: Path, tmp_path: Path
) -> None:
    """CONTROL, green before and after T135: the residual T135 does not close.

    A web action that commits while the runner holds the lock, after its snapshot, cannot be seen
    by that plan, and its own reconcile is refused. It is not lost: the next reconcile from any
    path files it. A durable queue generation would close this; it is out of scope.
    """
    data_dir = tmp_path / "data"
    with engine.begin() as conn:
        posting_id, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    folder = _sole_folder(root).name
    web: list[ReconcileReport] = []
    real_index = queue._index

    def index_then_commit(base: Path) -> tuple[dict[int, queue._Entry], tuple[str, ...]]:
        # `_index` runs inside the lock, after the reconcile pass has read the store.
        if not web:
            _web_action(data_dir, "skip", posting_id=posting_id, job_id=job_id)
            web.append(_web_reconcile(data_dir, root))
        return real_index(base)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(queue, "_index", index_then_commit)
        _drive("runner", engine, root, apps)

    assert len(web) == 1, "the commit never landed, so nothing was tested"
    assert (web[0].contended, web[0].moved) == (True, 0)
    assert _persisted(engine, "skip", job_id)
    assert _folders(root) == [folder], "the plan read a snapshot from before the commit"

    repair = _web_reconcile(data_dir, root)
    assert (repair.to_skipped, repair.failed) == (1, 0)
    assert _folders(root / SKIPPED_DIR) == [folder]


def test_a_contended_refresh_reports_both_halves_and_changes_nothing(
    engine: Engine, root: Path, apps: Path
) -> None:
    """Contention is a normal outcome: both reports say so, nothing moves, nothing raises. A
    pending drain is set up so a pass that ran anyway would show."""
    with engine.begin() as conn:
        _, job_id = _deliver(conn, apps, "one")
    with engine.connect() as conn:
        sync_queue(conn, root=root, owner_name=OWNER)
    with engine.begin() as conn:
        mark_job_skipped(conn, job_id=job_id, at=NOW)
    before = _snapshot(root)
    holder = FileLock(str(root / LOCK_FILE))
    holder.acquire()
    try:
        drained, synced = queue.refresh_queue(engine, root=root, owner_name=OWNER)
    finally:
        holder.release()

    assert drained == ReconcileReport(contended=True)
    assert synced == queue.SyncReport(contended=True)
    assert _snapshot(root) == before


def test_refresh_reads_the_store_only_after_the_lock_is_held(
    engine: Engine, root: Path, apps: Path
) -> None:
    """The invariant, pinned structurally: no statement reaches the store before the lock."""
    with engine.begin() as conn:
        _deliver(conn, apps, "one")
    order: list[str] = []
    real_lock = queue._queue_lock

    @contextmanager
    def lock(base: Path) -> Iterator[Path]:
        with real_lock(base) as path:
            order.append("lock")
            yield path

    def statement(*args: object) -> None:
        order.append("sql")

    event.listen(engine, "before_cursor_execute", statement)
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(queue, "_queue_lock", lock)
            queue.refresh_queue(engine, root=root, owner_name=OWNER)
    finally:
        event.remove(engine, "before_cursor_execute", statement)

    assert order.count("lock") == 1, "reconcile and sync must share ONE lock hold"
    assert order[0] == "lock" and "sql" in order
    assert _folders(root) != []
