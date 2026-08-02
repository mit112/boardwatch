"""Orchestration for `boardwatch tailor` — the P7 Tier A pipeline (spec §5).

Mirrors reports/notify.py's transaction discipline: never hold a DB write lock across
render/PDF I/O. Read JD skills + resolve the current OPEN posting version under a short
read connection, do all pure planning/rendering/safety with no lock held, then write the
master + tailored artifacts and the lineage edge in one closing engine.begin().

Fail closed: a posting with no current version, or one that is not open, raises before any
render or write. Tier A safety (enforce_tier_a) raises before ANY artifact is recorded, so
a rejected résumé leaves no trace on disk or in the DB.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select

from boardwatch.core.settings import Settings
from boardwatch.extract.preflight import run_preflight
from boardwatch.extract.taxonomy import Taxonomy, load_taxonomy
from boardwatch.store.artifacts import (
    add_derivation,
    get_or_create_master_artifact,
    record_artifact,
)
from boardwatch.store.queries import CurrentVersion, current_posting_versions
from boardwatch.store.tables import extractions, postings
from boardwatch.tailor.apply import apply_plan
from boardwatch.tailor.equivalences import EquivalenceTable, load_equivalences
from boardwatch.tailor.load import load_resume
from boardwatch.tailor.model import Resume
from boardwatch.tailor.plan import Delete, EquivalenceSwap, TailorPlan, build_plan
from boardwatch.tailor.render import TypstRunner
from boardwatch.tailor.render.typst import TypstRenderer
from boardwatch.tailor.safety import enforce_tier_a

VALIDATOR_VERSION = "tier-a-1"


class NoCurrentVersionError(RuntimeError):
    """The posting has no current version, or is not open — nothing safe to tailor against."""


@dataclass(frozen=True)
class TailorResult:
    posting_id: int
    source: str
    pdf_path: Path | None
    kept: list[str]
    dropped: list[str]
    swaps: list[tuple[str, str, str]]
    jd_skills: list[str]
    bullets: list[dict[str, object]]
    tailored_artifact_id: int | None
    dry_run: bool


def _default_runner(typ: Path, pdf: Path) -> bool:
    try:
        r = subprocess.run(["typst", "compile", str(typ), str(pdf)], capture_output=True)
        return r.returncode == 0 and pdf.exists()
    except FileNotFoundError:
        return False


def _trace(
    master: Resume,
    tailored: Resume,
    plan: TailorPlan,
    jd_skills: set[str],
    table: EquivalenceTable,
    master_hash: str,
    cv: CurrentVersion,
    fmt: str,
    pdf_built: bool,
    pdf_uri: str | None,
) -> dict[str, Any]:
    m_by = {b.bullet_id: b for e in master.entries for b in e.bullets}
    bullets: list[dict[str, Any]] = []
    for e in tailored.entries:
        for b in e.bullets:
            src = m_by[b.bullet_id].text
            bullets.append(
                {
                    "bullet_id": b.bullet_id,
                    "entry_id": e.entry_id,
                    "source_text_sha256": hashlib.sha256(src.encode()).hexdigest(),
                    "output_text_sha256": hashlib.sha256(b.text.encode()).hexdigest(),
                }
            )
    return {
        "validator_version": VALIDATOR_VERSION,
        "equivalences_version": table.version,
        "master_content_hash": master_hash,
        "posting_id": cv.posting_id,
        "posting_version_id": cv.posting_version_id,
        "jd_skills": sorted(jd_skills),
        "format": fmt,
        "typst_pdf_built": pdf_built,
        "pdf_uri": pdf_uri,
        "dropped": [op.bullet_id for op in plan.ops if isinstance(op, Delete)],
        "bullets": bullets,
    }


def _coverage_rows(
    master: Resume, tailored: Resume, dropped: list[str], jd_skills: set[str], taxonomy: Taxonomy
) -> list[dict[str, object]]:
    """Per-bullet JD coverage for the CLI: which skills each kept/dropped bullet covers."""
    entry_of = {b.bullet_id: e.entry_id for e in master.entries for b in e.bullets}
    m_by = {b.bullet_id: b for e in master.entries for b in e.bullets}
    rows: list[dict[str, object]] = []
    for e in tailored.entries:
        for b in e.bullets:
            rows.append(
                {
                    "bullet_id": b.bullet_id,
                    "entry_id": e.entry_id,
                    "action": "kept",
                    "jd_skills_covered": sorted(taxonomy.extract(b.text) & jd_skills),
                }
            )
    for bid in dropped:
        rows.append(
            {
                "bullet_id": bid,
                "entry_id": entry_of[bid],
                "action": "dropped",
                "jd_skills_covered": sorted(taxonomy.extract(m_by[bid].text) & jd_skills),
            }
        )
    return rows


def run_tailor(
    engine: Engine,
    settings: Settings,
    posting_id: int,
    *,
    resume_path: Path,
    out_dir: Path,
    fmt: str = "typst",
    dry_run: bool = False,
    typst_runner: TypstRunner | None = None,
) -> TailorResult:
    run_preflight(engine, settings)
    taxonomy = load_taxonomy(settings.config_dir)

    with engine.connect() as conn:
        cv = current_posting_versions(conn, [posting_id]).get(posting_id)
        if cv is None:
            raise NoCurrentVersionError(f"posting {posting_id} has no current version")
        # current_posting_versions ignores status for an explicit list; enforce open here.
        status = conn.execute(
            select(postings.c.status).where(postings.c.id == posting_id)
        ).scalar()
        if status != "open":
            raise NoCurrentVersionError(f"posting {posting_id} is not open (status={status!r})")
        row = conn.execute(
            select(extractions.c.json)
            .select_from(
                extractions.join(
                    postings,
                    (extractions.c.posting_id == postings.c.id)
                    & (extractions.c.content_hash == postings.c.content_hash),
                )
            )
            .where(
                extractions.c.posting_id == posting_id,
                extractions.c.kind == "taxonomy",
                extractions.c.engine_version == taxonomy.version,
            )
        ).first()
    jd_skills: set[str] = set((row.json if row else {}).get("skills", []))

    master = load_resume(Path(resume_path))
    table = load_equivalences()
    plan = build_plan(master, jd_skills, table, taxonomy)
    tailored = apply_plan(master, plan, table)
    enforce_tier_a(master, tailored, plan, table)  # raises before any render or write

    renderer = TypstRenderer()
    source = renderer.emit(tailored)
    master_hash = hashlib.sha256(renderer.emit(master).encode()).hexdigest()
    tailored_hash = hashlib.sha256(source.encode()).hexdigest()

    kept = [b.bullet_id for e in tailored.entries for b in e.bullets]
    dropped = [op.bullet_id for op in plan.ops if isinstance(op, Delete)]
    swaps = [
        (op.bullet_id, op.from_phrase, op.to_phrase)
        for op in plan.ops
        if isinstance(op, EquivalenceSwap)
    ]
    coverage = _coverage_rows(master, tailored, dropped, jd_skills, taxonomy)

    pdf_path: Path | None = None
    art_id: int | None = None
    if not dry_run:
        name = f"tailored-{posting_id}"
        typ_uri = str(Path(out_dir) / f"{name}.typ")  # deterministic reference (§5)
        # No lock held here: to_pdf shells out / touches the filesystem freely.
        pdf_path = renderer.to_pdf(source, Path(out_dir), name, typst_runner or _default_runner)
        meta = _trace(
            master, tailored, plan, jd_skills, table, master_hash, cv, fmt,
            pdf_path is not None, str(pdf_path) if pdf_path is not None else None,
        )
        with engine.begin() as conn:
            master_id = get_or_create_master_artifact(
                conn, content_hash=master_hash, uri=str(resume_path),
                generator_version=VALIDATOR_VERSION,
                meta={"kind": "master", "version": VALIDATOR_VERSION},
            )
            meta["master_artifact_id"] = master_id
            art_id = record_artifact(
                conn, kind="resume_tailored", uri=typ_uri,
                posting_version_id=cv.posting_version_id, content_hash=tailored_hash,
                generator="boardwatch.tailor", generator_version=VALIDATOR_VERSION,
                media_type="text/x-typst", meta=meta,
            )
            add_derivation(
                conn, artifact_id=art_id, parent_artifact_id=master_id, relation="tailored_from"
            )

    return TailorResult(
        posting_id=posting_id, source=source, pdf_path=pdf_path, kept=kept, dropped=dropped,
        swaps=swaps, jd_skills=sorted(jd_skills), bullets=coverage,
        tailored_artifact_id=art_id, dry_run=dry_run,
    )
