"""boardwatch tailor: init/validate/run for the Tier A résumé pipeline (P7, spec §5-6).

An authored, structured YAML résumé is the only input — boardwatch never parses a
résumé, it only renders one. `init` scaffolds that file, `validate` proves it loads and
shows what the taxonomy sees in each bullet, and `run` drives the deterministic,
no-fabrication tailoring pipeline (`reports.tailor.run_tailor`) against one posting.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.core.settings import Settings, load_settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.factory import build_client
from boardwatch.reports.resume_gate import LeadArtifactError, TypstUnavailableError
from boardwatch.reports.tailor import (
    NoCurrentVersionError,
    UnsupportedFormatError,
    plan_tier_a,
    run_tailor,
)
from boardwatch.tailor.load import ResumeLoadError, load_resume, scaffold_template
from boardwatch.tailor.rewrite.agent_io import CandidatesFile, VerdictsFile, dump_json, load_json
from boardwatch.tailor.rewrite.agent_lane import (
    apply_agent_rewrites,
    build_rewrite_request,
    screen_candidates,
)
from boardwatch.tailor.safety import TierASafetyError

console = Console()

tailor_app = typer.Typer(
    no_args_is_help=True,
    help="Tailor an authored résumé against a posting (local by default; opt-in LLM via --tier-b).",
)

rewrite_app = typer.Typer(
    no_args_is_help=True,
    help="Subscription Tier B agent lane: request/screen/apply skill-driven rewrites.",
)
tailor_app.add_typer(rewrite_app, name="rewrite")

RESUME_OPTION = typer.Option(None, "--resume", help="Path to the authored résumé YAML.")


def _resume_path(settings: Settings, override: Path | None = None) -> Path:
    return override if override is not None else settings.config_dir / "resume.yaml"


@tailor_app.command("init")
def init_cmd(
    ctx: typer.Context,
    force: bool = typer.Option(  # noqa: B008
        False, "--force", help="Overwrite an existing resume.yaml."
    ),
) -> None:
    """Scaffold an authored résumé YAML at {config_dir}/resume.yaml."""
    app_ctx = build_context(ctx.obj, ensure=False)
    path = _resume_path(app_ctx.settings)
    if path.exists() and not force:
        console.print(f"{path} already exists; pass --force to overwrite")
        raise typer.Exit(code=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scaffold_template(), encoding="utf-8")
    console.print(f"wrote {path}")


@tailor_app.command("validate")
def validate_cmd(ctx: typer.Context, resume_path: Path | None = RESUME_OPTION) -> None:
    """Load the authored résumé and report entry/bullet counts plus per-bullet skills."""
    app_ctx = build_context(ctx.obj, ensure=False)
    settings = app_ctx.settings
    try:
        resume = load_resume(_resume_path(settings, resume_path))
    except ResumeLoadError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc
    taxonomy = load_taxonomy(settings.config_dir)
    bullet_count = sum(len(entry.bullets) for entry in resume.entries)
    console.print(f"{len(resume.entries)} entries · {bullet_count} bullets")
    for entry in resume.entries:
        for bullet in entry.bullets:
            skills = ", ".join(sorted(taxonomy.extract(bullet.text))) or "none"
            # markup=False: rich reads the [entry_id] bracket as a style tag and swallows it.
            console.print(f"  [{entry.entry_id}] {bullet.bullet_id}: {skills}", markup=False)


@tailor_app.command("run")
def run_cmd(
    ctx: typer.Context,
    posting_id: int = typer.Argument(..., help="Posting id (the # column of top)."),  # noqa: B008
    resume_path: Path | None = RESUME_OPTION,
    out_dir: Path | None = typer.Option(  # noqa: B008
        None, "--out", help="Output directory (default {data_dir}/tailored)."
    ),
    fmt: str = typer.Option(  # noqa: B008
        "typst", "--format", help="Render format (typst is the only 1.0 adapter)."
    ),
    dry_run: bool = typer.Option(  # noqa: B008
        False, "--dry-run", help="Render and report without writing artifacts."
    ),
    tier_b: bool = typer.Option(  # noqa: B008
        False, "--tier-b", "--llm", help="Also emit an opt-in LLM-reworded variant (Tier B)."
    ),
) -> None:
    """Tailor the authored résumé against one posting's JD skills."""
    client = None
    cache = None
    if tier_b:
        # Evaluate the gate against settings ALONE, before build_context below creates
        # and migrates boardwatch.db — a gate failure against a pristine data dir must
        # leave no database behind. load_settings only reads config.toml, so loading it
        # again inside build_context is a cheap duplication, preferred here over
        # threading a pre-built AppContext through build_context's signature.
        gate_settings = load_settings(data_dir=ctx.obj)
        if not gate_settings.llm.resume_tailoring:
            console.print(
                "Tier B requires llm.resume_tailoring = true in config "
                "(opt-in for résumé rewording)"
            )
            raise typer.Exit(code=1)
        try:
            client = build_client(gate_settings)
        except ValueError as exc:
            console.print(str(exc))
            raise typer.Exit(code=1) from exc
        if client is None:
            console.print(
                "LLM tier is not enabled; set llm.enabled = true and BOARDWATCH_LLM_API_KEY"
            )
            raise typer.Exit(code=1)

    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    if tier_b:
        cache = ResponseCache(settings.data_dir / "llm-cache")

    try:
        result = run_tailor(
            app_ctx.engine,
            settings,
            posting_id,
            resume_path=_resume_path(settings, resume_path),
            out_dir=out_dir if out_dir is not None else settings.data_dir / "tailored",
            fmt=fmt,
            dry_run=dry_run,
            client=client,
            cache=cache,
        )
    except (
        ResumeLoadError,
        NoCurrentVersionError,
        TierASafetyError,
        UnsupportedFormatError,
        TypstUnavailableError,
        LeadArtifactError,
    ) as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    jd_skills = ", ".join(result.jd_skills) or "none"
    console.print(f"posting {result.posting_id} · jd skills: {jd_skills}")
    console.print(
        f"kept {len(result.kept)} · dropped {len(result.dropped)} · swaps {len(result.swaps)}"
    )
    for row in result.bullets:
        covered = ", ".join(row["jd_skills_covered"]) or "no jd skills"
        line = f"  {row['op']:<9} [{row['entry_id']}] {row['bullet_id']}: {covered}"
        if row["op"] == "swapped":
            swaps = ", ".join(f"{s['from']} -> {s['to']}" for s in row["swaps"])
            line += f" · {swaps}"
        console.print(line, markup=False)  # see validate_cmd: [entry_id] is not rich markup
    console.print("guarantee: PASS (Tier A no-fabrication check enforced before write)")
    if result.dry_run:
        if result.rewrites is not None:
            # Tier B ran even in a dry run (a preview must reflect what a real run
            # would produce) and its lane caches provider replies to disk as it goes,
            # so "nothing written" would be false here — only the résumé artifacts
            # were skipped, not the LLM response cache.
            console.print(
                "dry run — no résumé artifacts written (the LLM response cache was updated)"
            )
        else:
            console.print("dry run — source only, nothing written")
    elif result.pdf_path is not None and result.degraded:
        console.print(
            f"pdf: {result.pdf_path} "
            f"(degraded: untailored fallback, reason={result.degrade_reason})"
        )
    elif result.pdf_path is not None:
        console.print(f"pdf: {result.pdf_path}")
    else:
        # Outside a dry run, run_tailor raises TypstUnavailableError or LeadArtifactError
        # (caught above) before ever returning without a PDF — a PDF-less non-raising result
        # is exactly the silent false-success P1a exists to eliminate, so a regression that
        # reintroduces one must fail loudly here, not print a success-shaped message.
        raise AssertionError(
            "unreachable: run_tailor yields a PDF (shippable or degraded) or raises"
        )

    if result.rewrites is not None:
        reworded = sum(1 for r in result.rewrites if r["kept"])
        # "unchanged" (the provider echoed the bullet back verbatim) is not a fallback
        # failure — it is a no-op — so it is counted and tagged separately from a real
        # drop rather than folded into "fell back".
        unchanged = sum(1 for r in result.rewrites if r["drop_reason"] == "unchanged")
        fell_back = len(result.rewrites) - reworded - unchanged
        console.print(
            f"Tier B (LLM): reworded {reworded} · unchanged {unchanged} · fell back {fell_back}"
        )
        for r in result.rewrites:
            if r["kept"]:
                tag = "reworded"
            elif r["drop_reason"] == "unchanged":
                tag = "unchanged"
            else:
                tag = f"fallback:{r['drop_reason']}"
            console.print(f"  {tag:<16} [{r['entry_id']}] {r['bullet_id']}", markup=False)
        console.print(
            "Tier B is LLM-assisted: each reworded bullet passed a deterministic overmatch "
            "filter and a fail-closed entailment judge, but is NOT structurally proven — "
            "review the flagged variant before sending; the Tier A file above is the safe copy."
        )
        if any(r["drop_reason"] == "budget" for r in result.rewrites):
            console.print(
                "Tier B call budget exhausted before every bullet was reworded — raise "
                "llm.max_calls_per_run (Tier B spends 2 calls per bullet, shared with the "
                "eligibility LLM lane; a cache hit still spends budget, so re-running with "
                "no config change will not help)."
            )
        if not result.dry_run and result.llm_pdf_path is not None:
            console.print(f"tier B pdf: {result.llm_pdf_path}")


@rewrite_app.command("request")
def rewrite_request_cmd(
    ctx: typer.Context,
    posting_id: int = typer.Argument(..., help="Posting id (the # column of top)."),  # noqa: B008
    resume_path: Path | None = RESUME_OPTION,
    out: Path | None = typer.Option(  # noqa: B008
        None,
        "--out",
        help="Output path (default {data_dir}/tailored/rewrite_request-{posting_id}.json).",
    ),
) -> None:
    """Run Tier A internally, then write a JD-aware rewrite_request.json for the
    rewriter agent (subscription Tier B agent lane, step 1)."""
    # Evaluate the gate against settings ALONE, before build_context below creates and
    # migrates boardwatch.db — a gate failure against a pristine data dir must leave no
    # database behind (mirrors run_cmd's --tier-b gate above).
    gate_settings = load_settings(data_dir=ctx.obj)
    if not gate_settings.llm.resume_tailoring_via_agent:
        console.print("Tier B agent lane requires llm.resume_tailoring_via_agent = true in config")
        raise typer.Exit(code=1)

    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    try:
        tailored, jd_skills, _taxonomy = plan_tier_a(
            app_ctx.engine,
            settings,
            posting_id,
            resume_path=_resume_path(settings, resume_path),
        )
    except (ResumeLoadError, NoCurrentVersionError, TierASafetyError) as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    request_id = uuid.uuid4().hex
    request = build_rewrite_request(tailored, jd_skills, request_id=request_id)
    default_out = settings.data_dir / "tailored" / f"rewrite_request-{posting_id}.json"
    out_path = out if out is not None else default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(request, out_path)
    console.print(f"wrote {out_path}")
    console.print(
        f"request_id: {request_id} · jd skills: {len(request.jd_skills)} "
        f"· bullets: {len(request.bullets)}"
    )


@rewrite_app.command("screen")
def rewrite_screen_cmd(
    ctx: typer.Context,
    posting_id: int = typer.Argument(..., help="Posting id (the # column of top)."),  # noqa: B008
    candidates_path: Path = typer.Option(  # noqa: B008
        ..., "--candidates", help="Path to the rewriter agent's candidates.json."
    ),
    resume_path: Path | None = RESUME_OPTION,
    out: Path | None = typer.Option(  # noqa: B008
        None,
        "--out",
        help="Output path (default {data_dir}/tailored/judge_request-{posting_id}.json).",
    ),
) -> None:
    """Re-derive each bullet's a_text from a fresh Tier A run, filter the agent's
    candidates through the deterministic overmatch filter, and write a JD-free
    judge_request.json containing only filter-survivors (subscription Tier B agent
    lane, step 2)."""
    # Evaluate the gate against settings ALONE, before build_context below creates and
    # migrates boardwatch.db — mirrors rewrite_request_cmd's gate above.
    gate_settings = load_settings(data_dir=ctx.obj)
    if not gate_settings.llm.resume_tailoring_via_agent:
        console.print("Tier B agent lane requires llm.resume_tailoring_via_agent = true in config")
        raise typer.Exit(code=1)

    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    try:
        tailored, _jd_skills, taxonomy = plan_tier_a(
            app_ctx.engine,
            settings,
            posting_id,
            resume_path=_resume_path(settings, resume_path),
        )
    except (ResumeLoadError, NoCurrentVersionError, TierASafetyError) as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    candidates = load_json(CandidatesFile, candidates_path)
    judge_req, drops = screen_candidates(
        tailored, candidates, taxonomy, request_id=candidates.request_id
    )
    default_out = settings.data_dir / "tailored" / f"judge_request-{posting_id}.json"
    out_path = out if out is not None else default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(judge_req, out_path)

    console.print(f"wrote {out_path}")
    console.print(f"survived to judge: {len(judge_req.items)} · dropped: {len(drops)}")
    for drop in drops:
        console.print(f"  dropped [{drop.bullet_id}]: {drop.reason}", markup=False)


@rewrite_app.command("apply")
def rewrite_apply_cmd(
    ctx: typer.Context,
    posting_id: int = typer.Argument(..., help="Posting id (the # column of top)."),  # noqa: B008
    candidates_path: Path = typer.Option(  # noqa: B008
        ..., "--candidates", help="Path to the rewriter agent's candidates.json."
    ),
    verdicts_path: Path = typer.Option(  # noqa: B008
        ..., "--verdicts", help="Path to the judge agent's verdicts.json."
    ),
    resume_path: Path | None = RESUME_OPTION,
    out: Path | None = typer.Option(  # noqa: B008
        None, "--out", help="Output directory for artifacts (default {data_dir}/tailored)."
    ),
) -> None:
    """Parse each agent verdict via `parse_verdict`, keep filter-pass ∧ ENTAILED, and
    emit both the Tier A artifact and a `resume_tailored_llm` artifact — reusing
    `run_tailor`'s existing artifact writer with no live LLM client (subscription Tier B
    agent lane, step 3)."""
    # Evaluate the gate against settings ALONE, before build_context below creates and
    # migrates boardwatch.db — mirrors rewrite_request_cmd's / rewrite_screen_cmd's gate.
    gate_settings = load_settings(data_dir=ctx.obj)
    if not gate_settings.llm.resume_tailoring_via_agent:
        console.print("Tier B agent lane requires llm.resume_tailoring_via_agent = true in config")
        raise typer.Exit(code=1)

    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    resolved_resume_path = _resume_path(settings, resume_path)
    try:
        tailored, jd_skills, taxonomy = plan_tier_a(
            app_ctx.engine, settings, posting_id, resume_path=resolved_resume_path
        )
    except (ResumeLoadError, NoCurrentVersionError, TierASafetyError) as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    candidates = load_json(CandidatesFile, candidates_path)
    verdicts = load_json(VerdictsFile, verdicts_path)
    if candidates.request_id != verdicts.request_id:
        console.print(
            "candidates and verdicts are from different runs "
            f"(request_id {candidates.request_id} != {verdicts.request_id}); "
            "re-run screen + judge for this request, or pass the matching files"
        )
        raise typer.Exit(code=1)
    tb = apply_agent_rewrites(tailored, candidates, verdicts, taxonomy, jd_skills)
    # Recomputed identically to the budget apply_agent_rewrites enforced internally (2x
    # bullet count) so the artifact's recorded `budget` matches the cap that was actually
    # applied — these two computations must stay in sync.
    llm_budget = 2 * sum(len(e.bullets) for e in tailored.entries)

    out_dir = out if out is not None else settings.data_dir / "tailored"
    try:
        result = run_tailor(
            app_ctx.engine,
            settings,
            posting_id,
            resume_path=resolved_resume_path,
            out_dir=out_dir,
            tb_override=tb,
            llm_provider_override="claude-code-agent",
            llm_model_override="subscription",
            llm_budget_override=llm_budget,
        )
    except (TypstUnavailableError, LeadArtifactError) as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    jd_skills_str = ", ".join(result.jd_skills) or "none"
    console.print(f"posting {result.posting_id} · jd skills: {jd_skills_str}")
    console.print(
        f"kept {len(result.kept)} · dropped {len(result.dropped)} · swaps {len(result.swaps)}"
    )
    if result.pdf_path is not None and result.degraded:
        console.print(
            f"pdf: {result.pdf_path} "
            f"(degraded: untailored fallback, reason={result.degrade_reason})"
        )
    elif result.pdf_path is not None:
        console.print(f"pdf: {result.pdf_path}")
    else:
        # run_tailor raises TypstUnavailableError or LeadArtifactError (caught above) before
        # ever returning without a PDF — a PDF-less non-raising result is exactly the silent
        # false-success P1a exists to eliminate, so a regression that reintroduces one must
        # fail loudly here, not print a success-shaped message.
        raise AssertionError(
            "unreachable: run_tailor yields a PDF (shippable or degraded) or raises"
        )

    # tb_override always populates result.rewrites (run_tailor's Tier B guard fires
    # whenever client-or-tb_override is given); see reports/tailor.py.
    assert result.rewrites is not None
    reworded = sum(1 for r in result.rewrites if r["kept"])
    # "unchanged" (the agent echoed the bullet back verbatim) is not a fallback failure —
    # it is a no-op — so it is counted and tagged separately from a real drop, mirroring
    # run_cmd's Tier B summary.
    unchanged = sum(1 for r in result.rewrites if r["drop_reason"] == "unchanged")
    fell_back = len(result.rewrites) - reworded - unchanged
    console.print(
        f"Tier B (LLM): reworded {reworded} · unchanged {unchanged} · fell back {fell_back}"
    )
    for r in result.rewrites:
        if r["kept"]:
            tag = "reworded"
        elif r["drop_reason"] == "unchanged":
            tag = "unchanged"
        else:
            tag = f"fallback:{r['drop_reason']}"
        console.print(f"  {tag:<16} [{r['entry_id']}] {r['bullet_id']}", markup=False)
    console.print(
        "Tier B is LLM-assisted: each reworded bullet passed a deterministic overmatch "
        "filter and a fail-closed entailment judge, but is NOT structurally proven — "
        "review the flagged variant before sending; the Tier A file above is the safe copy."
    )
    if result.llm_pdf_path is not None:
        console.print(f"tier B pdf: {result.llm_pdf_path}")
