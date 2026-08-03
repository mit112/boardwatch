"""Orchestration for `boardwatch tailor` — the P7 Tier A pipeline (spec §5), plus the
opt-in Tier B LLM rewording lane (P7b).

Mirrors reports/notify.py's transaction discipline: never hold a DB write lock across
render/PDF I/O. Read JD skills + resolve the current OPEN posting version under a short
read connection, do all pure planning/rendering/safety with no lock held, then write the
master + tailored artifacts and the lineage edge in one closing engine.begin().

Fail closed: a posting with no current version, or one that is not open, raises before any
render or write. Tier A safety (enforce_tier_a) raises before ANY artifact is recorded, so
a rejected résumé leaves no trace on disk or in the DB.

Tier B runs only when the caller supplies a `ModelClient`; passing none leaves Tier A's
output, hashes, and artifacts exactly as if Tier B did not exist. When a client is given,
`run_tier_b`'s filter + judge are its own gate — `enforce_tier_a` never runs against the
reworded model, since `Rewrite` is not a Tier A op. Tier B emits a second
`resume_tailored_llm` artifact with a `rewritten_from` edge back to the Tier A artifact,
recorded in the same closing transaction as Tier A's write.
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
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.client import ModelClient
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
from boardwatch.tailor.rewrite.lane import TierBResult, run_tier_b
from boardwatch.tailor.rewrite.prompt import JUDGE_PROMPT_VERSION, REWRITE_PROMPT_VERSION
from boardwatch.tailor.safety import enforce_tier_a

VALIDATOR_VERSION = "tier-a-1"
LLM_LANE_VERSION = "tier-b-1"
SUPPORTED_FORMATS = ("typst",)


class NoCurrentVersionError(RuntimeError):
    """The posting has no current version, or is not open — nothing safe to tailor against."""


class UnsupportedFormatError(ValueError):
    """Asked for a render format this build has no adapter for (Typst is the sole 1.0 adapter)."""


@dataclass(frozen=True)
class TailorResult:
    posting_id: int
    source: str
    pdf_path: Path | None
    kept: list[str]
    dropped: list[str]
    swaps: list[tuple[str, str, str]]
    jd_skills: list[str]
    bullets: list[dict[str, Any]]
    tailored_artifact_id: int | None
    dry_run: bool
    llm_source: str | None = None
    llm_pdf_path: Path | None = None
    rewrites: list[dict[str, Any]] | None = None
    llm_artifact_id: int | None = None


def _default_runner(typ: Path, pdf: Path) -> bool:
    try:
        r = subprocess.run(["typst", "compile", str(typ), str(pdf)], capture_output=True)
        return r.returncode == 0 and pdf.exists()
    except FileNotFoundError:
        return False


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _moved_bullet_ids(master: Resume, tailored: Resume) -> set[str]:
    """Bullets whose position changed relative to the author's order among the survivors.

    Deleting a bullet shifts everything below it; that is not a reorder. Comparing against
    the author's order *filtered to the surviving ids* isolates genuine emphasis changes.
    """
    master_entries = {e.entry_id: e for e in master.entries}
    moved: set[str] = set()
    for e in tailored.entries:
        out_order = [b.bullet_id for b in e.bullets]
        survivors = set(out_order)
        author_order = [
            b.bullet_id for b in master_entries[e.entry_id].bullets if b.bullet_id in survivors
        ]
        moved.update(a for a, o in zip(author_order, out_order, strict=True) if a != o)
    return moved


def _audit_rows(
    master: Resume,
    tailored: Resume,
    plan: TailorPlan,
    jd_skills: set[str],
    taxonomy: Taxonomy,
) -> list[dict[str, Any]]:
    """One row per bullet: what happened to it and why (spec L9 `bullets[]` schema).

    Persisted verbatim in the artifact's meta_json AND printed by the CLI, so the audit a
    user reads is byte-for-byte the audit that was recorded.
    """
    m_by = {b.bullet_id: b for e in master.entries for b in e.bullets}
    entry_of = {b.bullet_id: e.entry_id for e in master.entries for b in e.bullets}
    swaps_by: dict[str, list[tuple[str, str]]] = {}
    for op in plan.ops:
        if isinstance(op, EquivalenceSwap):
            swaps_by.setdefault(op.bullet_id, []).append((op.from_phrase, op.to_phrase))
    moved = _moved_bullet_ids(master, tailored)

    rows: list[dict[str, Any]] = []
    for e in tailored.entries:
        for b in e.bullets:
            swaps = swaps_by.get(b.bullet_id, [])
            reordered = b.bullet_id in moved
            row: dict[str, Any] = {
                "bullet_id": b.bullet_id,
                "entry_id": e.entry_id,
                # A swap rewrites the text, so it is the headline op; `reordered` keeps the
                # position fact from being lost when a bullet both moved and was swapped.
                "op": "swapped" if swaps else "reordered" if reordered else "kept",
                "reordered": reordered,
                "jd_skills_covered": sorted(taxonomy.extract(b.text) & jd_skills),
                "source_text_sha256": _sha(m_by[b.bullet_id].text),
                "output_text_sha256": _sha(b.text),
            }
            if swaps:
                row["from"], row["to"] = swaps[0]
                row["swaps"] = [{"from": f, "to": t} for f, t in swaps]
            rows.append(row)
    for op in plan.ops:
        if isinstance(op, Delete):
            src = m_by[op.bullet_id].text
            rows.append(
                {
                    "bullet_id": op.bullet_id,
                    "entry_id": entry_of[op.bullet_id],
                    "op": "dropped",
                    "jd_skills_covered": sorted(taxonomy.extract(src) & jd_skills),
                    "source_text_sha256": _sha(src),
                    "output_text_sha256": None,
                }
            )
    return rows


def _trace(
    plan: TailorPlan,
    jd_skills: set[str],
    table: EquivalenceTable,
    master_hash: str,
    cv: CurrentVersion,
    fmt: str,
    pdf_built: bool,
    pdf_uri: str | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
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
        "bullets": rows,
    }


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
    client: ModelClient | None = None,
    cache: ResponseCache | None = None,
) -> TailorResult:
    if fmt not in SUPPORTED_FORMATS:
        supported = ", ".join(SUPPORTED_FORMATS)
        raise UnsupportedFormatError(f"unsupported format {fmt!r}; supported: {supported}")
    run_preflight(engine, settings)
    taxonomy = load_taxonomy(settings.config_dir)

    with engine.connect() as conn:
        cv = current_posting_versions(conn, [posting_id]).get(posting_id)
        if cv is None:
            raise NoCurrentVersionError(f"posting {posting_id} has no current version")
        # current_posting_versions ignores status for an explicit list; enforce open here.
        status = conn.execute(select(postings.c.status).where(postings.c.id == posting_id)).scalar()
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
    # Hash the authored model, not its render: the render drops bullet_id/entry_id/tech_tags,
    # so two different masters that merely *look* the same would content-address to one
    # artifact and hand the second run the first one's uri as its lineage parent.
    master_hash = _sha(master.model_dump_json())
    tailored_hash = _sha(source)

    kept = [b.bullet_id for e in tailored.entries for b in e.bullets]
    dropped = [op.bullet_id for op in plan.ops if isinstance(op, Delete)]
    swaps = [
        (op.bullet_id, op.from_phrase, op.to_phrase)
        for op in plan.ops
        if isinstance(op, EquivalenceSwap)
    ]
    rows = _audit_rows(master, tailored, plan, jd_skills, taxonomy)

    # Tier B: opt-in LLM rewording, gated on an explicit client. Runs whether or not this
    # is a dry run — the preview must reflect what a real run would produce — but it never
    # touches Tier A's own `tailored`/`source`/`tailored_hash` above it.
    llm_source: str | None = None
    llm_rows: list[dict[str, Any]] | None = None
    llm_hash: str | None = None
    # Non-Optional sentinel (rather than `TierBResult | None`) so `tb.calls_made` below
    # needs no null-check: it is only ever read from the `client is not None` write path,
    # where `tb` has always been replaced by a real `run_tier_b` result.
    tb = TierBResult(accepted=[], rows=[], calls_made=0)
    if client is not None:
        if cache is None:
            raise ValueError("cache is required when client is provided")
        tb = run_tier_b(
            tailored,
            client,
            cache,
            jd_skills=jd_skills,
            taxonomy=taxonomy,
            model=settings.llm.model or "unknown",
            budget=settings.llm.max_calls_per_run,
        )
        tailored_b = apply_plan(tailored, TailorPlan(ops=tuple(tb.accepted)), table)
        reworded = frozenset(r.bullet_id for r in tb.accepted)
        llm_source = renderer.emit(tailored_b, reworded=reworded)
        # Content-address Tier B by the model, not the render (unlike Tier A's
        # `tailored_hash` above, which hashes the render for historical reasons predating
        # this lane). This asymmetry is deliberate and documented — not something to
        # "fix" by changing Tier A's addressing.
        llm_hash = _sha(tailored_b.model_dump_json())
        llm_rows = [
            {
                "bullet_id": r.bullet_id,
                "entry_id": r.entry_id,
                "a_text_sha256": _sha(r.a_text),
                "b_text_sha256": _sha(r.b_text),
                "filter_pass": r.filter_pass,
                "judge_verdict": r.judge_verdict,
                "kept": r.kept,
                "drop_reason": r.drop_reason,
                "op": "reworded" if r.kept else "fallback",
            }
            for r in tb.rows
        ]

    pdf_path: Path | None = None
    art_id: int | None = None
    llm_pdf_path: Path | None = None
    llm_art_id: int | None = None
    if not dry_run:
        name = f"tailored-{posting_id}"
        typ_uri = str(Path(out_dir) / f"{name}.typ")  # deterministic reference (§5)
        # No lock held here: to_pdf shells out / touches the filesystem freely.
        pdf_path = renderer.to_pdf(source, Path(out_dir), name, typst_runner or _default_runner)
        llm_uri: str | None = None
        if client is not None and llm_source is not None:
            llm_name = f"tailored-{posting_id}-llm"
            llm_uri = str(Path(out_dir) / f"{llm_name}.typ")
            llm_pdf_path = renderer.to_pdf(
                llm_source, Path(out_dir), llm_name, typst_runner or _default_runner
            )
        meta = _trace(
            plan,
            jd_skills,
            table,
            master_hash,
            cv,
            fmt,
            pdf_path is not None,
            str(pdf_path) if pdf_path is not None else None,
            rows,
        )
        with engine.begin() as conn:
            master_id = get_or_create_master_artifact(
                conn,
                content_hash=master_hash,
                uri=str(resume_path),
                generator_version=VALIDATOR_VERSION,
                meta={"kind": "master", "version": VALIDATOR_VERSION},
            )
            meta["master_artifact_id"] = master_id
            art_id = record_artifact(
                conn,
                kind="resume_tailored",
                uri=typ_uri,
                posting_version_id=cv.posting_version_id,
                content_hash=tailored_hash,
                generator="boardwatch.tailor",
                generator_version=VALIDATOR_VERSION,
                media_type="text/x-typst",
                meta=meta,
            )
            add_derivation(
                conn, artifact_id=art_id, parent_artifact_id=master_id, relation="tailored_from"
            )
            if client is not None and llm_source is not None and llm_uri is not None:
                llm_meta = {
                    "tier": "B",
                    "llm_lane_version": LLM_LANE_VERSION,
                    "rewrite_prompt_version": REWRITE_PROMPT_VERSION,
                    "judge_prompt_version": JUDGE_PROMPT_VERSION,
                    "provider": settings.llm.provider,
                    "model": settings.llm.model,
                    "tier_a_artifact_id": art_id,
                    "tier_a_content_hash": tailored_hash,
                    "posting_id": cv.posting_id,
                    "posting_version_id": cv.posting_version_id,
                    "calls_made": tb.calls_made,
                    "budget": settings.llm.max_calls_per_run,
                    "rewrites": llm_rows,
                }
                llm_art_id = record_artifact(
                    conn,
                    kind="resume_tailored_llm",
                    uri=llm_uri,
                    posting_version_id=cv.posting_version_id,
                    content_hash=llm_hash,
                    generator="boardwatch.tailor",
                    generator_version=LLM_LANE_VERSION,
                    media_type="text/x-typst",
                    meta=llm_meta,
                )
                add_derivation(
                    conn, artifact_id=llm_art_id, parent_artifact_id=art_id,
                    relation="rewritten_from",
                )

    return TailorResult(
        posting_id=posting_id,
        source=source,
        pdf_path=pdf_path,
        kept=kept,
        dropped=dropped,
        swaps=swaps,
        jd_skills=sorted(jd_skills),
        bullets=rows,
        tailored_artifact_id=art_id,
        dry_run=dry_run,
        llm_source=llm_source,
        llm_pdf_path=llm_pdf_path,
        rewrites=llm_rows,
        llm_artifact_id=llm_art_id,
    )
