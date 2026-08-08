"""Orchestration for `boardwatch tailor` — the P7 Tier A pipeline (spec §5), plus the
opt-in Tier B LLM rewording lane (P7b).

Mirrors reports/notify.py's transaction discipline: never hold a DB write lock across
render/PDF I/O. Read JD skills + resolve the current OPEN posting version under a short
read connection, do all pure planning/rendering/safety with no lock held, then write the
master + tailored artifacts and the lineage edge in one closing engine.begin().

Fail closed: a posting with no current version, or one that is not open, raises before any
render or write. Tier A safety (enforce_tier_a) raises before ANY artifact is recorded, so
a rejected résumé leaves no trace on disk or in the DB.

Tier B runs only when the caller supplies a `ModelClient` OR a precomputed `tb_override`
(the subscription agent lane, P7b task 6); passing neither leaves Tier A's output,
hashes, and artifacts exactly as if Tier B did not exist. When a client is given,
`run_tier_b`'s filter + judge are its own gate; `tb_override` carries a `TierBResult`
already produced by `apply_agent_rewrites` replaying `run_tier_b_core` over agent JSON
files — either way `enforce_tier_a` never runs against the reworded model, since
`Rewrite` is not a Tier A op. Tier B emits a second `resume_tailored_llm` artifact with a
`rewritten_from` edge back to the Tier A artifact, recorded in the same closing
transaction as Tier A's write.
"""

from __future__ import annotations

import hashlib
import re
import shutil
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
from boardwatch.reports.resume_gate import (
    GateReason,
    GateResult,
    LayoutViolation,
    LeadArtifactError,
    RenderToolMissingError,
    ResumeValidationError,
    evaluate_compile,
    validate_layout,
    validate_slots,
)
from boardwatch.store.artifacts import (
    add_derivation,
    get_or_create_master_artifact,
    record_artifact,
)
from boardwatch.store.queries import (
    CurrentVersion,
    current_posting_versions,
    ensure_run,
    finish_run,
    get_profile,
)
from boardwatch.store.tables import extractions, postings
from boardwatch.tailor.apply import apply_plan
from boardwatch.tailor.coverage import (
    CoverageReport,
    coverage_report,
    coverage_to_dict,
    requirement_terms,
    resume_fact_skills,
)
from boardwatch.tailor.equivalences import EquivalenceTable, load_equivalences
from boardwatch.tailor.load import load_resume
from boardwatch.tailor.model import Resume
from boardwatch.tailor.persona import apply_persona, load_personas, select_persona
from boardwatch.tailor.plan import Delete, EquivalenceSwap, TailorPlan, build_plan
from boardwatch.tailor.render.latex import LatexRenderer
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason, CompileRunner
from boardwatch.tailor.rewrite.lane import TierBResult, run_tier_b
from boardwatch.tailor.rewrite.prompt import JUDGE_PROMPT_VERSION, REWRITE_PROMPT_VERSION
from boardwatch.tailor.rewrite.provenance import PROVENANCE_VERSION
from boardwatch.tailor.safety import enforce_tier_a
from boardwatch.tailor.title import resolve_title

VALIDATOR_VERSION = "tier-a-1"
# Bumped for P1b (D-033): the lane now vetoes un-provenanced rewords before the judge,
# so a cached pre-gate Tier-B reply must not be replayed as if it had passed the gate.
LLM_LANE_VERSION = "tier-b-2"
SUPPORTED_FORMATS = ("latex",)
_RENDER_TOOL_MISSING_MSG = (
    "tectonic binary not found on PATH; install it (e.g. `brew install tectonic` or "
    "https://tectonic-typesetting.github.io/en-US/install.html) to render résumé PDFs"
)


class NoCurrentVersionError(RuntimeError):
    """The posting has no current version, or is not open — nothing safe to tailor against."""


class UnsupportedFormatError(ValueError):
    """Asked for a render format this build has no adapter for (LaTeX is the sole 1.0 adapter)."""


@dataclass(frozen=True)
class _TierAPlan:
    """Full Tier A planning result — the private, complete sibling of `plan_tier_a`'s
    public 3-tuple. `run_tailor` needs `master`/`table`/`plan`/`cv` below this point for
    hashing, the audit trail, and the artifact write; `plan_tier_a` exposes only what the
    subscription Tier B agent-lane CLI needs (P7b task 4)."""

    master: Resume
    tailored: Resume
    jd_skills: set[str]
    taxonomy: Taxonomy
    table: EquivalenceTable
    plan: TailorPlan
    cv: CurrentVersion
    # P4 item 7: the persona lens chosen for this JD and the headline title it resolved to.
    # `master` stays the ORIGINAL authored résumé (its hash, coverage, and the untailored
    # safety-net render must not be shaped by a presentation lens); `tailored` is built from
    # the persona-shaped résumé, so `tailored.title` carries `resolved_title` into the render.
    persona_id: str
    resolved_title: str


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
    # False/None on a dry run (the compile gate never runs) and on a shippable non-degraded
    # PDF; True + the tailored gate's failure reason when the untailored-master fallback is
    # what actually shipped (P1a task 4 — the CLI needs this to print the degraded marker).
    degraded: bool = False
    degrade_reason: str | None = None
    # P4 item 6: how many of the JD's requirement terms the MASTER résumé genuinely has. A
    # REPORT, never a veto — it never changes `kept`/`dropped`/`degraded`. None when a coverage
    # measurement error was swallowed (fail-safe: a metric bug must not delete a real résumé).
    coverage: CoverageReport | None = None
    # P4 item 7: the persona lens applied for this JD (also recorded in the artifact meta_json).
    persona_id: str | None = None


def _pdf_page_count(pdf: Path) -> int | None:
    """Shell `pdfinfo` and parse its `Pages:` line. Real `pdfinfo` output lists `Pages:`
    well after Creator/Producer/CreationDate/etc (around line 11), never on line 1 — the
    `re.MULTILINE` flag is load-bearing so `^` anchors to each line, not just position 0.
    Missing binary, non-zero exit, or unparseable output all fall through to `None`."""
    if shutil.which("pdfinfo") is None:
        return None
    result = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


def _default_runner(tex: Path, pdf: Path) -> CompileOutcome:
    if shutil.which("tectonic") is None:
        return CompileOutcome(CompileReason.BINARY_MISSING, None, None, "")
    compiled = subprocess.run(
        ["tectonic", "-X", "compile", "--outfmt", "pdf", "--outdir", str(pdf.parent), str(tex)],
        capture_output=True, text=True,
    )
    log = compiled.stdout + compiled.stderr
    # tectonic names its output PDF by the .tex stem, not the requested `pdf` path.
    produced = pdf.parent / f"{tex.stem}.pdf"
    if compiled.returncode != 0 or not produced.exists():
        return CompileOutcome(CompileReason.COMPILE_FAILED, None, None, log)
    if produced != pdf:
        shutil.move(str(produced), str(pdf))
    page_count = _pdf_page_count(pdf)
    if page_count is None:
        # Mirrors the old typst fallback: an unmeasured PDF is treated as a compile
        # failure so the lead falls back rather than shipping without a page count.
        return CompileOutcome(CompileReason.COMPILE_FAILED, None, None, log)
    return CompileOutcome(CompileReason.OK, pdf, page_count, log)


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
    coverage: CoverageReport | None,
    persona_id: str,
    resolved_title: str,
) -> dict[str, Any]:
    return {
        "validator_version": VALIDATOR_VERSION,
        "equivalences_version": table.version,
        "master_content_hash": master_hash,
        "posting_id": cv.posting_id,
        "posting_version_id": cv.posting_version_id,
        "jd_skills": sorted(jd_skills),
        "format": fmt,
        # P4 item 7 audit: the persona lens and the headline it resolved to for this JD.
        "persona_id": persona_id,
        "resolved_title": resolved_title,
        # legacy meta key name (D-058); renaming ripples into funnel/reconcile — out of scope
        "typst_pdf_built": pdf_built,
        "pdf_uri": pdf_uri,
        "dropped": [op.bullet_id for op in plan.ops if isinstance(op, Delete)],
        "bullets": rows,
        "coverage": coverage_to_dict(coverage),
    }


def _plan_tier_a(
    engine: Engine, settings: Settings, posting_id: int, *, resume_path: Path
) -> _TierAPlan:
    """Tier A planning prefix shared by `run_tailor` and `plan_tier_a`: preflight,
    taxonomy, the posting's current OPEN version + jd_skills extraction lookup, the
    authored résumé, equivalences, plan build/apply, and the no-fabrication check —
    raises before any render or write.
    """
    run_preflight(engine, settings)
    taxonomy = load_taxonomy(settings.config_dir)
    # A malformed registry (bundled OR override) raises PersonaError here, before any render or
    # write — the pipeline runner treats it as a run-level fatal, never a per-lead degrade.
    registry = load_personas(settings.config_dir)

    with engine.connect() as conn:
        cv = current_posting_versions(conn, [posting_id]).get(posting_id)
        if cv is None:
            raise NoCurrentVersionError(f"posting {posting_id} has no current version")
        # current_posting_versions ignores status for an explicit list; enforce open here, and
        # read the posting title in the same round-trip — it is the persona-selection input.
        prow = conn.execute(
            select(postings.c.status, postings.c.title).where(postings.c.id == posting_id)
        ).one()
        if prow.status != "open":
            raise NoCurrentVersionError(
                f"posting {posting_id} is not open (status={prow.status!r})"
            )
        jd_title = str(prow.title)
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
    # Shape the résumé through the persona lens BEFORE planning: the JD title selects the
    # persona, the persona resolves the headline title, and the shaped résumé (reordered skill
    # groups, entry subset, headline) is what all of Tier A operates on. `apply_persona` never
    # fabricates — it only selects and reorders EXISTING master facts — so the Tier A firewall
    # compares `tailored` against `shaped`, which is itself entailed by `master`.
    persona = select_persona(jd_title, registry)
    resolved_title = resolve_title(jd_title, persona)
    shaped = apply_persona(master, persona, resolved_title)
    table = load_equivalences()
    plan = build_plan(shaped, jd_skills, table, taxonomy)
    tailored = apply_plan(shaped, plan, table)
    enforce_tier_a(shaped, tailored, plan, table)  # raises before any render or write

    return _TierAPlan(
        master=master,
        tailored=tailored,
        jd_skills=jd_skills,
        taxonomy=taxonomy,
        table=table,
        plan=plan,
        cv=cv,
        persona_id=persona.id,
        resolved_title=resolved_title,
    )


def plan_tier_a(
    engine: Engine, settings: Settings, posting_id: int, *, resume_path: Path
) -> tuple[Resume, set[str], Taxonomy, str]:
    """Tier A prefix for callers that only need the tailored résumé + JD skills +
    taxonomy + JD body text — the subscription Tier B agent lane (P7b task 4). Reuses
    `run_tailor`'s exact Tier A selection logic rather than re-deriving it.

    The JD body text (P4 item 1, D-048) is the current OPEN posting version's body,
    exactly what the API lane's `run_tailor` passes to `run_tier_b` -- callers that do not
    need it for their own step (e.g. the request/screen steps) discard it.
    """
    r = _plan_tier_a(engine, settings, posting_id, resume_path=resume_path)
    return r.tailored, r.jd_skills, r.taxonomy, r.cv.body_text


def run_tailor(
    engine: Engine,
    settings: Settings,
    posting_id: int,
    *,
    resume_path: Path,
    out_dir: Path,
    fmt: str = "latex",
    dry_run: bool = False,
    typst_runner: CompileRunner | None = None,
    client: ModelClient | None = None,
    cache: ResponseCache | None = None,
    tb_override: TierBResult | None = None,
    llm_provider_override: str | None = None,
    llm_model_override: str | None = None,
    llm_budget_override: int | None = None,
    run_id: int | None = None,
) -> TailorResult:
    if fmt not in SUPPORTED_FORMATS:
        supported = ", ".join(SUPPORTED_FORMATS)
        raise UnsupportedFormatError(f"unsupported format {fmt!r}; supported: {supported}")
    if client is not None and tb_override is not None:
        raise ValueError("pass either client or tb_override, not both")
    r = _plan_tier_a(engine, settings, posting_id, resume_path=resume_path)
    master, tailored, jd_skills, taxonomy = r.master, r.tailored, r.jd_skills, r.taxonomy
    table, plan, cv = r.table, r.plan, r.cv
    persona_id, resolved_title = r.persona_id, r.resolved_title

    renderer = LatexRenderer(config_dir=settings.config_dir)
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

    # P4 item 6: keyword coverage of the JD's requirement terms against the MASTER résumé (the
    # anti-echo denominator — never the tailored output). Wrapped fail-safe: a bug here records
    # coverage=None and never aborts, so a measurement error can never delete a real résumé.
    coverage: CoverageReport | None
    try:
        jd_requirement_skills, denominator_source = requirement_terms(cv.body_text, taxonomy)
        coverage = coverage_report(
            jd_requirement_skills, resume_fact_skills(master, taxonomy), denominator_source
        )
    except Exception:  # noqa: BLE001 - a coverage-measurement bug must not drop the lead
        coverage = None

    # Tier B: opt-in LLM rewording, gated on an explicit client. Runs whether or not this
    # is a dry run — the preview must reflect what a real run would produce — but it never
    # touches Tier A's own `tailored`/`source`/`tailored_hash` above it.
    llm_source: str | None = None
    llm_rows: list[dict[str, Any]] | None = None
    llm_hash: str | None = None
    # Non-Optional sentinel (rather than `TierBResult | None`) so `tb.calls_made` below
    # needs no null-check: it is only ever read from the `client is not None` or
    # `tb_override is not None` write path, where `tb` has always been replaced by a
    # real (or precomputed, agent-lane) `TierBResult`.
    tb = TierBResult(accepted=[], rows=[], calls_made=0)
    if client is not None or tb_override is not None:
        if client is not None:
            if cache is None:
                raise ValueError("cache is required when client is provided")
            tb = run_tier_b(
                tailored,
                client,
                cache,
                jd_skills=jd_skills,
                taxonomy=taxonomy,
                table=table,
                model=settings.llm.model or "unknown",
                budget=settings.llm.max_calls_per_run,
                provider=settings.llm.provider,
                base_url=settings.llm.base_url,
                jd_text=cv.body_text,
            )
        else:
            # Subscription agent lane (P7b task 6): the filter/verdict/row path already
            # ran in `apply_agent_rewrites`, no live client to call here. `tb_override`
            # is guaranteed non-None here — the enclosing `if` requires client or
            # tb_override, and this `else` is only reached when client is None.
            assert tb_override is not None
            tb = tb_override
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
                "op": (
                    "reworded"
                    if r.kept
                    else "unchanged" if r.drop_reason == "unchanged" else "fallback"
                ),
            }
            for r in tb.rows
        ]

    pdf_path: Path | None = None
    art_id: int | None = None
    llm_pdf_path: Path | None = None
    llm_art_id: int | None = None
    # Declared here, not inside `if not dry_run:` below, so the final TailorResult can report
    # them unconditionally — a dry run never touches the compile gate, so both stay at their
    # honest "nothing to report" default.
    degraded = False
    degrade_reason: str | None = None
    if not dry_run:
        with engine.connect() as conn:
            profile_row = get_profile(conn)
        # The stored column has no floor (Task 2 review note): a missing profile or a
        # non-positive value both fall back to 1 rather than being trusted verbatim — a 0
        # would make every lead exceed the limit.
        max_pages = max(1, profile_row.resume_max_pages) if profile_row is not None else 1
        chosen_runner = typst_runner or _default_runner

        name = f"tailored-{posting_id}"
        typ_path = Path(out_dir) / f"{name}.tex"  # deterministic reference (§5)
        pdf_path_candidate = Path(out_dir) / f"{name}.pdf"
        untailored_name = f"untailored-{posting_id}"
        untailored_typ_path = Path(out_dir) / f"{untailored_name}.tex"
        untailored_pdf_path = Path(out_dir) / f"{untailored_name}.pdf"

        try:
            validate_slots(tailored)
            validate_layout(tailored, source)
        except LayoutViolation as exc:
            # A structural layout violation (P4 item 5a): never sent to tectonic, straight to
            # the untailored-master fallback below — same posture as a slot failure.
            tailored_gate = GateResult(exc.reason, False, None, None, str(exc))
        except ResumeValidationError as exc:
            # Treated exactly like a failed compile: never sent to tectonic, straight to the
            # untailored-master fallback below.
            tailored_outcome = CompileOutcome(
                CompileReason.COMPILE_FAILED, None, None, f"slot validation failed: {exc}"
            )
            tailored_gate = evaluate_compile(tailored_outcome, max_pages=max_pages)
        else:
            # No lock held here: to_pdf shells out / touches the filesystem freely.
            tailored_outcome = renderer.to_pdf(source, Path(out_dir), name, chosen_runner)
            tailored_gate = evaluate_compile(tailored_outcome, max_pages=max_pages)
        if tailored_gate.reason is GateReason.BINARY_MISSING:
            raise RenderToolMissingError(_RENDER_TOOL_MISSING_MSG)

        if tailored_gate.shippable:
            chosen_gate = tailored_gate
            chosen_typ_uri = str(typ_path)
            chosen_hash = tailored_hash
        else:
            # No layout gate here (P4 checkpoint fix): the untailored master is the
            # unconditionally-shippable safety net (P1a — never silently delete a real
            # job). It is Mit's authored, already page-valid résumé; `validate_layout`'s
            # TOO_MANY_BULLETS reuses MAX_BULLETS_PER_ENTRY, which is a *selection* cap
            # `build_plan` trims TO, so the authored master can legitimately have entries
            # that exceed it before trimming. Gating this fallback on the same check the
            # tailored side just failed dropped leads a zero-/low-skill JD should still
            # ship. Master-authoring defects belong in a future run-once, load-time check
            # (item 5b), not this per-lead path.
            untailored_source = renderer.emit(master)
            untailored_outcome = renderer.to_pdf(
                untailored_source, Path(out_dir), untailored_name, chosen_runner
            )
            untailored_gate = evaluate_compile(untailored_outcome, max_pages=max_pages)
            if untailored_gate.reason is GateReason.BINARY_MISSING:
                raise RenderToolMissingError(_RENDER_TOOL_MISSING_MSG)
            if untailored_gate.shippable:
                degraded = True
                degrade_reason = tailored_gate.reason.value
                chosen_gate = untailored_gate
                chosen_typ_uri = str(untailored_typ_path)
                chosen_hash = _sha(untailored_source)
            else:
                # Both attempts failed: no artifact, no folder — only the failure log.
                combined_log = (
                    f"tailored ({tailored_gate.reason.value}):\n{tailored_gate.log}\n\n"
                    f"untailored ({untailored_gate.reason.value}):\n{untailored_gate.log}"
                )
                day_dir = Path(out_dir).parent
                failed_dir = day_dir / "_failed"
                failed_dir.mkdir(parents=True, exist_ok=True)
                failed_log_path = failed_dir / f"{Path(out_dir).name}.log"
                failed_log_path.write_text(combined_log, encoding="utf-8")
                # Leave no partial output behind: delete only what this call itself may
                # have written, then the now-empty lead folder.
                for p in (typ_path, pdf_path_candidate, untailored_typ_path, untailored_pdf_path):
                    p.unlink(missing_ok=True)
                try:
                    Path(out_dir).rmdir()
                except OSError:
                    pass  # not empty (unrelated files present) or already gone
                raise LeadArtifactError(
                    f"posting {posting_id}: no shippable résumé PDF "
                    f"(tailored={tailored_gate.reason.value}, "
                    f"untailored={untailored_gate.reason.value}); log: {failed_log_path}"
                )

        assert chosen_gate.pdf_path is not None  # shippable => evaluate_compile's OK branch
        pdf_path = chosen_gate.pdf_path
        log_path = Path(out_dir) / "tectonic-compile.log"
        log_path.write_text(chosen_gate.log, encoding="utf-8")

        llm_uri: str | None = None
        if (client is not None or tb_override is not None) and llm_source is not None:
            llm_name = f"tailored-{posting_id}-llm"
            try:
                validate_layout(tailored_b, llm_source)
            except LayoutViolation:
                # Fail-soft, not fail-drop: Tier B is the path most likely to produce an
                # off-band bullet or leaked boilerplate (LLM-rewritten, unaudited for
                # layout), but Tier A's own PDF above is already gated and remains the
                # lead's deliverable. Treated as if Tier B were never attempted -- never
                # sent to tectonic, and llm_uri stays None so the resume_tailored_llm insert
                # below is skipped too, rather than recording an artifact for a résumé
                # that was never shippable.
                pass
            else:
                llm_uri = str(Path(out_dir) / f"{llm_name}.tex")
                llm_outcome = renderer.to_pdf(llm_source, Path(out_dir), llm_name, chosen_runner)
                llm_gate = evaluate_compile(llm_outcome, max_pages=max_pages)
                if llm_gate.reason is GateReason.BINARY_MISSING:
                    raise RenderToolMissingError(_RENDER_TOOL_MISSING_MSG)
                if llm_gate.shippable:
                    llm_pdf_path = llm_gate.pdf_path
                # else: skip the Tier B PDF; Tier A's PDF above remains the lead's deliverable.

        meta = _trace(
            plan, jd_skills, table, master_hash, cv, fmt, True, str(pdf_path), rows, coverage,
            persona_id, resolved_title,
        )
        meta["degraded"] = degraded
        if degraded:
            meta["degrade_reason"] = degrade_reason
        meta["compile_log_uri"] = str(log_path)

        # Standalone `boardwatch tailor run` owns its run: a degenerate pipeline run whose
        # only stage is this one posting. Minting rather than writing NULL keeps
        # `run_id IS NULL` meaning "predates attribution" and nothing else. Under
        # `boardwatch run` the pipeline supplies the id and all leads share it.
        owns_run = run_id is None
        run_id = ensure_run(engine, run_id)
        with engine.begin() as conn:
            master_id = get_or_create_master_artifact(
                conn,
                content_hash=master_hash,
                uri=str(resume_path),
                generator_version=VALIDATOR_VERSION,
                meta={"kind": "master", "version": VALIDATOR_VERSION},
                run_id=run_id,
            )
            meta["master_artifact_id"] = master_id
            art_id = record_artifact(
                conn,
                kind="resume_tailored",
                uri=chosen_typ_uri,
                posting_version_id=cv.posting_version_id,
                content_hash=chosen_hash,
                generator="boardwatch.tailor",
                generator_version=VALIDATOR_VERSION,
                media_type="text/x-tex",
                meta=meta,
                run_id=run_id,
            )
            add_derivation(
                conn, artifact_id=art_id, parent_artifact_id=master_id, relation="tailored_from"
            )
            if llm_uri is not None:
                llm_meta = {
                    "tier": "B",
                    "llm_lane_version": LLM_LANE_VERSION,
                    "rewrite_prompt_version": REWRITE_PROMPT_VERSION,
                    "judge_prompt_version": JUDGE_PROMPT_VERSION,
                    "provenance_version": PROVENANCE_VERSION,
                    "provider": llm_provider_override or settings.llm.provider,
                    "model": llm_model_override or settings.llm.model,
                    "tier_a_artifact_id": art_id,
                    # The hash of what actually shipped as the Tier-A artifact above
                    # (`chosen_hash`), not the rejected tailored render's `tailored_hash`
                    # — when Tier A degraded to the untailored master, those two differ,
                    # and this lineage must match `tier_a_artifact_id`'s own content_hash.
                    "tier_a_content_hash": chosen_hash,
                    "posting_id": cv.posting_id,
                    "posting_version_id": cv.posting_version_id,
                    "calls_made": tb.calls_made,
                    # The agent lane enforces its own budget (2x bullet count, not the
                    # API lane's llm.max_calls_per_run — see apply_agent_rewrites), so
                    # the override must be recorded here or the audit trail would show
                    # calls_made exceeding a budget that was never actually the cap.
                    "budget": (
                        llm_budget_override
                        if llm_budget_override is not None
                        else settings.llm.max_calls_per_run
                    ),
                    "typst_pdf_built": llm_pdf_path is not None,
                    "pdf_uri": str(llm_pdf_path) if llm_pdf_path is not None else None,
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
                    media_type="text/x-tex",
                    meta=llm_meta,
                    run_id=run_id,
                )
                add_derivation(
                    conn, artifact_id=llm_art_id, parent_artifact_id=art_id,
                    relation="rewritten_from",
                )

        if owns_run:
            finish_run(engine, run_id)

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
        degraded=degraded,
        degrade_reason=degrade_reason,
        coverage=coverage,
        persona_id=persona_id,
    )
