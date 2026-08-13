"""boardwatch eligibility facts|policy (§4.6, D-P2-1, D-P2-4).

User controls land BEFORE any automatic evaluation, so this CLI is the only writer of the
eligibility facts and severity policy. Every value is validated against the CATALOG's
declared choices, never against a literal spelled here: the vocabulary in an error message
comes from the catalog, so it stays correct as the catalog grows (D-P2-4).

No module-level string collection lives here. This module is scoped under R9, which flags a
non-empty string collection at a declaration position with no allowlist, so the severity set
is read from the Policy type and any small word lists stay inside function bodies.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, NoReturn, get_args

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from boardwatch.cli.context import build_context
from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import FamilySpec, FieldSpec, RulesCatalog, load_rules
from boardwatch.eligibility.engine import current_evaluations, not_applicable_field_families
from boardwatch.eligibility.extract_llm import extract_and_record
from boardwatch.eligibility.facts import (
    Facts,
    Policy,
    PolicyChoice,
    facts_payload,
    parse_facts,
    parse_policy,
)
from boardwatch.eligibility.gate_handshake import apply_gate_verdicts, build_gate_request
from boardwatch.eligibility.oracle import (
    OracleVerdict,
    apply_oracle_verdicts,
    build_label_request,
    read_worksheet,
)
from boardwatch.eligibility.preflight import current_identity, run_eligibility
from boardwatch.eligibility.scoring import SHIP_AUDIT_COVERAGE_BAR, load_labeled_set, score
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.client import LaneDeathReason, LLMLaneDeadError
from boardwatch.llm.factory import build_client
from boardwatch.llm.payload import preview_text
from boardwatch.pipeline.runner import DEFAULT_TOP_N
from boardwatch.reports.abstain import build_abstain_report
from boardwatch.store.abstain_queries import count_requirement_dispositions
from boardwatch.store.queries import (
    RUN_FAILED,
    RUN_OK,
    current_posting_versions,
    ensure_run,
    finish_run,
    get_profile,
    save_eligibility,
)
from boardwatch.store.tables import eligibility_requirements

console = Console()

eligibility_app = typer.Typer(no_args_is_help=True, help="Eligibility facts and severity policy.")
facts_app = typer.Typer(invoke_without_command=True, help="Show or set your eligibility facts.")
policy_app = typer.Typer(invoke_without_command=True, help="Show or set severity per family.")
label_app = typer.Typer(
    no_args_is_help=True, help="Oracle-judge labeling handshake: request/apply."
)
gate_app = typer.Typer(
    no_args_is_help=True,
    help="Final eligibility gate handshake over the ranked shortlist: request/apply.",
)
eligibility_app.add_typer(facts_app, name="facts")
eligibility_app.add_typer(policy_app, name="policy")
eligibility_app.add_typer(label_app, name="label")
eligibility_app.add_typer(gate_app, name="gate")

# Worksheet default: the labeled-set *.jsonl directory the label/score commands read and
# write. Rooted under the user's own data_dir (not a repo-relative path) so multi-tenancy
# holds — Mit's own worksheet lives in his gitignored working dir and is passed via
# --worksheet, never hardcoded here.
_DEFAULT_WORKSHEET_DIRNAME = "eligibility-labels"


def _no_profile() -> NoReturn:
    console.print("no profile yet, run `boardwatch init` first")
    raise typer.Exit(code=1)


def _coerce(field: FieldSpec, value: str) -> object:
    """A source-form value validated against one catalog field's declared type and choices.

    Every rejection raises typer.BadParameter carrying the declared choices, so the message
    vocabulary comes from the catalog and never from a literal here.
    """
    if field.type == "choice":
        if value not in field.choices:
            raise typer.BadParameter(
                f"{value!r} is not a valid {field.name}. Choices: {', '.join(field.choices)}"
            )
        return value
    if field.type == "choice_set":
        items = [item.strip() for item in value.split(",") if item.strip()]
        for item in items:
            if item not in field.choices:
                raise typer.BadParameter(
                    f"{item!r} is not a valid {field.name}. "
                    f"Choices: {', '.join(field.choices)}"
                )
        return tuple(sorted(set(items)))
    if field.type == "int":
        # str.isdigit() is True for Unicode digits like "²" that int() cannot parse, so guard
        # with isascii() too: the point is a clean BadParameter, never a raw ValueError.
        if not (value.isascii() and value.isdigit()):
            raise typer.BadParameter(f"{field.name} must be a whole number, got {value!r}")
        return int(value)
    if field.type == "bool":
        truthy = {"true", "yes", "y", "1", "on"}
        falsy = {"false", "no", "n", "0", "off"}
        low = value.strip().lower()
        if low in truthy:
            return True
        if low in falsy:
            return False
        raise typer.BadParameter(f"{field.name} must be yes or no, got {value!r}")
    raise typer.BadParameter(f"unsupported field type {field.type!r}")


def _resolve_field(family: FamilySpec, fact_name: str, field_name: str) -> FieldSpec:
    if family.answer_type == "structured":
        field_names = ", ".join(spec.name for spec in family.fields)
        if not field_name:
            raise typer.BadParameter(
                f"{fact_name} is structured, so set it as {fact_name}.<field> "
                f"where <field> is one of: {field_names}"
            )
        field = next((spec for spec in family.fields if spec.name == field_name), None)
        if field is None:
            raise typer.BadParameter(
                f"unknown field {field_name!r} for {fact_name}. Fields: {field_names}"
            )
        return field
    if field_name:
        raise typer.BadParameter(f"{fact_name} is a scalar fact and takes no field")
    return family.fields[0]


def set_fact(facts: Facts, catalog: RulesCatalog, dotted: str, value: str) -> Facts:
    """Apply one dotted assignment to the facts, returning a new Facts.

    `dotted` is `<fact>` for a scalar family or `<fact>.<field>` for a structured one. The
    fact is looked up by iterating the catalog for a matching `family.fact`, and the value is
    validated against the matching field's declared type and choices. Pure and CLI-free.
    """
    fact_name, _, field_name = dotted.partition(".")
    family = next(
        (candidate for candidate in catalog.families if candidate.fact == fact_name), None
    )
    if family is None:
        valid = ", ".join(sorted(candidate.fact for candidate in catalog.families))
        raise typer.BadParameter(f"unknown fact {fact_name!r}. Valid facts: {valid}")
    field = _resolve_field(family, fact_name, field_name)
    parsed = _coerce(field, value)
    data = facts.model_dump()
    if family.answer_type == "structured":
        sub = dict(data.get(fact_name) or {})
        sub[field.name] = parsed
        data[fact_name] = sub
    else:
        data[fact_name] = parsed
    return Facts.model_validate(data)


def set_career_field(facts: Facts, catalog: RulesCatalog, value: str) -> Facts:
    """Set the profile's career_field, validated against the catalog's closed vocabulary.

    career_field is a non-family scalar, so set_fact (which resolves a family.fact) cannot
    reach it. Pure and CLI-free apart from the BadParameter it raises for a friendly message.
    """
    if value not in catalog.career_fields:
        valid = ", ".join(sorted(catalog.career_fields)) or "(none declared)"
        raise typer.BadParameter(f"unknown career_field {value!r}. Valid: {valid}")
    return facts.model_copy(update={"career_field": value})


def set_policy(policy: Policy, catalog: RulesCatalog, family_id: str, choice: str) -> Policy:
    """Apply one family severity to the policy, returning a new Policy. Pure and CLI-free.

    The family must be a catalog family id and the choice a declared severity; both rejections
    raise typer.BadParameter carrying the valid vocabulary, which comes from the catalog and the
    Policy type, never a literal spelled at a call site."""
    valid_families = [spec.id for spec in catalog.families]
    if family_id not in valid_families:
        raise typer.BadParameter(
            f"unknown policy family {family_id!r}. Valid families: {', '.join(valid_families)}"
        )
    severities = get_args(PolicyChoice)
    if choice not in severities:
        raise typer.BadParameter(f"unknown severity {choice!r}. Valid: {', '.join(severities)}")
    return Policy(families={**policy.families, family_id: choice})


def _render_value(value: object) -> str:
    if value is None:
        return "not set"
    if isinstance(value, tuple):
        return ", ".join(value) if value else "not set"
    return str(value)


@facts_app.callback(invoke_without_command=True)
def facts_root(ctx: typer.Context) -> None:
    """Show every declared fact and its current value."""
    if ctx.invoked_subcommand is not None:
        return
    app_ctx = build_context(ctx.obj)
    catalog = load_rules(app_ctx.settings.config_dir)
    with app_ctx.engine.connect() as conn:
        row = get_profile(conn)
    if row is None:
        _no_profile()
    facts = parse_facts(row.eligibility_facts_json)
    for family in catalog.families:
        if family.answer_type == "structured":
            sub = getattr(facts, family.fact)
            console.print(f"{family.label}:")
            for field in family.fields:
                value = getattr(sub, field.name) if sub is not None else None
                console.print(f"  {field.name}: {_render_value(value)}")
        else:
            console.print(f"{family.label}: {_render_value(getattr(facts, family.fact))}")
    console.print(f"Career field: {_render_value(facts.career_field)}")


@facts_app.command("set")
def facts_set(ctx: typer.Context, fact: str, value: str) -> None:
    """Set one fact, e.g. `highest_degree bachelor` or `work_authorization.status citizen`."""
    app_ctx = build_context(ctx.obj)
    catalog = load_rules(app_ctx.settings.config_dir)
    with app_ctx.engine.begin() as conn:
        row = get_profile(conn)
        if row is None:
            _no_profile()
        facts = parse_facts(row.eligibility_facts_json)
        policy = parse_policy(row.eligibility_policy_json)
        try:
            if fact == "career_field":
                new_facts = set_career_field(facts, catalog, value)
            else:
                new_facts = set_fact(facts, catalog, fact, value)
        except typer.BadParameter as exc:
            typer.echo(exc.message)
            raise typer.Exit(code=1) from exc
        save_eligibility(
            conn,
            facts_json=facts_payload(new_facts),
            policy_json=policy.model_dump(mode="json"),
        )
    console.print(f"set {fact} = {value}")


@eligibility_app.command("run")
def run_cmd(ctx: typer.Context) -> None:
    """Evaluate every open posting that has no current-version verdict yet."""
    app_ctx = build_context(ctx.obj)
    stats = run_eligibility(app_ctx.engine, app_ctx.settings, console)
    if stats.skipped_no_profile:
        console.print("no profile yet, run `boardwatch init` first")
        raise typer.Exit(code=1)
    console.print(f"evaluated {stats.evaluated} postings")


@eligibility_app.command("extract")
def extract_cmd(
    ctx: typer.Context,
    dry_run: bool = typer.Option(  # noqa: B008
        False,
        "--dry-run",
        help="Preview the LLM payload and destination for open postings; call no model.",
    ),
) -> None:
    """Opt-in LLM-assisted eligibility extraction (advisory, D-P3-13). Off by default.

    The deterministic `eligibility run` stays authoritative; this command only ever adds
    additional `engine_kind='llm'` rows that `show` renders as advisory. When the LLM
    tier is off or uncredentialed this degrades to a one-line message instead of an
    error, and never calls a model.
    """
    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    if not settings.llm.eligibility_extraction:
        console.print(
            "LLM eligibility extraction is off; set llm.eligibility_extraction = true "
            "in config to enable"
        )
        return
    client = build_client(settings)
    if client is None:
        console.print(
            "LLM tier is off; enable it in config and set BOARDWATCH_LLM_API_KEY"
        )
        return

    with app_ctx.engine.connect() as conn:
        versions = current_posting_versions(conn, None)
    ordered = sorted(versions.values(), key=lambda cv: cv.posting_version_id)
    provider = settings.llm.provider or "unknown"
    model = settings.llm.model or "unknown"
    # build_client() (llm/factory.py) never passes base_url to AnthropicClient, so the
    # anthropic provider always talks to its hardcoded default regardless of config. Mirror
    # that here so the preview names the destination a request will actually reach.
    preview_base_url = settings.llm.base_url if provider != "anthropic" else None

    if dry_run:
        if not ordered:
            console.print("no open postings to preview")
            return
        for current in ordered:
            console.print(
                preview_text(
                    current.body_text, provider=provider, model=model,
                    base_url=preview_base_url,
                )
            )
        return

    with app_ctx.engine.connect() as conn:
        profile_row = get_profile(conn)
    if profile_row is None:
        _no_profile()
    if not ordered:
        console.print("no open postings to extract")
        return

    facts = parse_facts(profile_row.eligibility_facts_json)
    policy = parse_policy(profile_row.eligibility_policy_json)
    catalog = load_rules(settings.config_dir)
    cache = ResponseCache(settings.data_dir / "llm-cache")

    console.print(
        preview_text(
            ordered[0].body_text, provider=provider, model=model,
            base_url=preview_base_url,
        )
    )
    # Two counters, deliberately. `attempted` is what bounds the loop; keying the
    # cap to successes instead would let unclassified failures run the ENTIRE
    # posting set, removing the only working call ceiling in the codebase.
    attempted = 0
    extracted = 0
    lane_death: LaneDeathReason | None = None
    # This lane is invoked standalone, so it owns its run: a degenerate pipeline run whose
    # only stage is the LLM extraction. Minting rather than writing NULL is what keeps
    # `run_id IS NULL` meaning "predates attribution" and nothing else.
    #
    # It is minted on the first posting reached, NOT conditioned on a row being written, and
    # that is deliberate rather than lazy: the id has to exist before extract_and_record can
    # write it, so there is no ordering in which a successful write precedes the mint. A
    # provider outage therefore records a finished run attributing zero rows — which is
    # correct HERE and would be wrong in run_eligibility. `extract` is an explicit user
    # action, so "I ran extract and it produced nothing" belongs in the ledger; the
    # eligibility preflight fires incidentally on every `top`, so minting there would turn
    # `runs` into a command log. The two rules differ because the invocations differ.
    run_id: int | None = None
    for current in ordered:
        if attempted >= settings.llm.max_calls_per_run:
            break
        if run_id is None:
            run_id = ensure_run(app_ctx.engine, None)
        attempted += 1
        try:
            with app_ctx.engine.begin() as conn:
                evaluation_id = extract_and_record(
                    conn,
                    posting_version_id=current.posting_version_id,
                    jd_text=current.body_text,
                    facts=facts,
                    policy=policy,
                    catalog=catalog,
                    client=client,
                    cache=cache,
                    provider=settings.llm.provider,
                    model=settings.llm.model,
                    run_id=run_id,
                )
        except LLMLaneDeadError as exc:
            lane_death = exc.reason
            break
        if evaluation_id is not None:
            extracted += 1
    # Fatal only when death was observed AND nothing landed: a partial run is a real partial
    # success, and zero-landed alone is a routine outcome. Computed once, above the ledger
    # write, because the same flag has to drive BOTH the durable status and the exit code —
    # a command that exits 1 while its own run row says `ok` makes the honest report the
    # ephemeral one. It is narrower than "the run wrote nothing": an unclassified provider
    # outage still finishes `ok` attributing zero rows, which the comment above deliberately
    # blesses. Only the case where the command itself declares failure is recorded as failure.
    lane_death_fatal = lane_death is not None and extracted == 0
    if run_id is not None:
        finish_run(
            app_ctx.engine,
            run_id,
            # The reason is read off the typed exception attribute, never parsed back out of
            # a message; this string is the ledger's rendering of it, not its classification.
            errors=(
                [f"eligibility extract: llm lane dead ({lane_death}); 0 of {attempted} extracted"]
                if lane_death_fatal
                else None
            ),
            status=RUN_FAILED if lane_death_fatal else RUN_OK,
        )
    console.print(f"extracted {extracted} of {attempted} attempted")
    if lane_death is not None:
        console.print(
            f"LLM lane stopped: the credential is unusable ({lane_death}). "
            "Remaining postings were not called."
        )
        if lane_death_fatal:
            raise typer.Exit(code=1)


@eligibility_app.command("summary")
def summary_cmd(ctx: typer.Context) -> None:
    """Counts per family and disposition across the funnel, plus how many open postings have
    no current-engine evaluation. This is how a user learns whether the catalog fires at all
    before trusting a hidden count."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        identity = current_identity(conn, app_ctx.settings)
        versions = current_posting_versions(conn, None)
        version_ids = [cv.posting_version_id for cv in versions.values()]
        evals = (
            current_evaluations(conn, version_ids, *identity) if identity is not None else {}
        )
        eval_ids = [eval_id for eval_id, _ in evals.values()]
        requirement_rows = (
            conn.execute(
                select(
                    eligibility_requirements.c.rule_id,
                    eligibility_requirements.c.disposition,
                ).where(eligibility_requirements.c.evaluation_id.in_(eval_ids))
            ).all()
            if eval_ids
            else []
        )
    evaluated = len(evals)
    unevaluated = len(version_ids) - evaluated
    verdicts: Counter[str] = Counter(verdict for _, verdict in evals.values())
    by_family: Counter[tuple[str, str]] = Counter()
    for row in requirement_rows:
        family = row.rule_id.split(":")[0] if row.rule_id else "(unknown)"
        by_family[(family, row.disposition)] += 1

    console.print(f"evaluated: {evaluated} · no current-engine evaluation: {unevaluated}")
    if verdicts:
        console.print(
            "verdicts: " + ", ".join(f"{name} {count}" for name, count in sorted(verdicts.items()))
        )
    for (family, disposition), count in sorted(by_family.items()):
        console.print(f"  {family} · {disposition}: {count}")


@eligibility_app.command("abstain")
def abstain_cmd(ctx: typer.Context) -> None:
    """Abstain rate for EVERY rule in the catalog, including rules that have never fired.

    `summary` groups the rows that exist; this enumerates the catalog and joins the rows onto
    it. The difference is the entire point: a rule that has never been detected produces no
    row to group, so it is invisible to `summary` and visible here as `never fired`. That is
    the keystone invariant's monitoring requirement — a rule that cannot fire must be a
    reported failure, not silence.

    Scoped, like `summary`, to the CURRENT deterministic evaluation of each OPEN posting. So
    `never fired` means "never fired in this scope": a rule that only ever fired on postings
    that have since closed reports as never-fired here. The footer prints how many evaluations
    were examined so a scope of zero cannot be mistaken for a catalog of dead rules.
    """
    app_ctx = build_context(ctx.obj)
    catalog = load_rules(app_ctx.settings.config_dir)
    with app_ctx.engine.connect() as conn:
        identity = current_identity(conn, app_ctx.settings)
        versions = current_posting_versions(conn, None)
        version_ids = [cv.posting_version_id for cv in versions.values()]
        evals = (
            current_evaluations(conn, version_ids, *identity) if identity is not None else {}
        )
        eval_ids = [eval_id for eval_id, _ in evals.values()]
        counts = count_requirement_dispositions(conn, eval_ids)
        profile_row = get_profile(conn)
    na = (
        not_applicable_field_families(parse_facts(profile_row.eligibility_facts_json), catalog)
        if profile_row is not None
        else frozenset()
    )
    report = build_abstain_report(catalog, counts, not_applicable_families=na)

    table = Table(title="per-rule abstain rate")
    # Fold rather than ellipsize: at 80 columns rich truncates rule_ids to a common prefix,
    # and `experience_years:total_years_minimum` / `..._preferred` then render identically.
    # The rule_id IS the report's key, so it can wrap but must never be abbreviated.
    table.add_column("rule", overflow="fold")
    table.add_column("observed", justify="right")
    table.add_column("met", justify="right")
    table.add_column("unmet", justify="right")
    table.add_column("abstained", justify="right")
    table.add_column("rate", justify="right")
    for rule in report.rules:
        if rule.not_applicable:
            rate, style = "not applicable", "dim"
        elif rule.never_fired:
            # Not "0%" — the rule produced no rows, so there is no rate to report.
            rate, style = "never fired", "yellow"
        elif rule.fully_abstaining:
            rate, style = "100%", "red"
        else:
            # Guard the rounding: 1051/1052 formats as "100%" and would then be
            # character-identical to a rule that genuinely never decides, collapsing the two
            # states this report exists to keep apart.
            rounded = f"{rule.abstain_rate:.0%}"
            rate, style = (">99%" if rounded == "100%" else rounded), ""
        table.add_row(
            rule.rule_id, str(rule.observed), str(rule.met), str(rule.unmet),
            str(rule.unknown), rate, style=style or None,
        )
    console.print(table)

    console.print(
        f"{len(report.rules)} rules · {len(report.never_fired)} never fired · "
        f"{len(report.not_applicable)} not applicable · "
        f"{len(report.fully_abstaining)} fire but never decide · "
        f"{report.total_rows} rows across {len(evals)} evaluations"
    )
    if report.unattributed:
        console.print(f"[yellow]{report.unattributed} rows carry no rule_id[/yellow]")
    # Closed catalog, three dimensions: an undeclared rule_id, a family the catalog does not
    # declare, or a disposition token outside {met, unmet, unknown}. Each is a FAILURE, never
    # a new bucket. Print every one that fired before exiting, so a run is not diagnosed one
    # anomaly at a time.
    failed = False
    if report.out_of_catalog:
        console.print(
            f"[red]FAILURE: {report.out_of_catalog_rows} rows carry rule_ids the catalog does "
            f"not declare: {', '.join(report.out_of_catalog)}[/red]"
        )
        failed = True
    if report.out_of_catalog_families:
        console.print(
            f"[red]FAILURE: dispositions observed under families the catalog does not "
            f"declare: {', '.join(report.out_of_catalog_families)}[/red]"
        )
        failed = True
    if report.bad_dispositions:
        console.print(
            f"[red]FAILURE: dispositions outside the closed set {{met, unmet, unknown}}: "
            f"{', '.join(report.bad_dispositions)}[/red]"
        )
        failed = True
    if failed:
        raise typer.Exit(1)


def _worksheet_dir(settings: Settings, worksheet: Path | None) -> Path:
    return worksheet if worksheet is not None else settings.data_dir / _DEFAULT_WORKSHEET_DIRNAME


def _require_worksheet_dir(settings: Settings, worksheet: Path | None) -> Path:
    """Resolve the worksheet dir and fail loud if it does not exist.

    `Path.glob` and `load_labeled_set` both treat a missing directory as "no rows" —
    correct for a legitimate empty worksheet, wrong for a typo'd or unmounted `--worksheet`
    path, which would otherwise print a quiet "0 unlabeled" / all-zero tallies / "total 0"
    and exit 0, indistinguishable from real emptiness. An EXISTING but empty directory (0
    `*.jsonl` files, or every row already labeled) is NOT an error and must not raise here.
    """
    worksheet_dir = _worksheet_dir(settings, worksheet)
    if not worksheet_dir.is_dir():
        console.print(f"[red]worksheet directory not found: {worksheet_dir}[/red]")
        raise typer.Exit(2)
    return worksheet_dir


@label_app.command("request")
def label_request_cmd(
    ctx: typer.Context,
    worksheet: Path | None = typer.Option(  # noqa: B008
        None,
        "--worksheet",
        help="Directory of labeled-set *.jsonl worksheets "
        "(default {data_dir}/eligibility-labels).",
    ),
    out: Path | None = typer.Option(  # noqa: B008
        None,
        "--out",
        help="Output path for the label request JSON (default {worksheet}/label_request.json).",
    ),
) -> None:
    """Build an oracle-judge label request from every unlabeled row in the worksheet.

    Reads every `*.jsonl` file in `--worksheet`, selects rows with no `expected_verdict`
    yet, and writes one JD-blind-of-prior-guess request (`hint` dropped, per
    `build_label_request`'s independence contract) for the judge to answer.
    """
    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    catalog = load_rules(settings.config_dir)
    worksheet_dir = _require_worksheet_dir(settings, worksheet)
    rows: list[dict[str, Any]] = []
    for path in sorted(worksheet_dir.glob("*.jsonl")):
        rows.extend(read_worksheet(path))
    request_id = uuid.uuid4().hex
    request = build_label_request(rows, catalog, request_id=request_id)
    out_path = out if out is not None else worksheet_dir / "label_request.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    console.print(f"wrote {out_path}")
    console.print(f"request_id={request_id} · {len(request['items'])} unlabeled")


@label_app.command("apply")
def label_apply_cmd(
    ctx: typer.Context,
    verdicts_path: Path = typer.Option(  # noqa: B008
        ..., "--verdicts", help="Path to the judge's verdicts JSON (a list of verdict objects)."
    ),
    worksheet: Path | None = typer.Option(  # noqa: B008
        None,
        "--worksheet",
        help="Directory of labeled-set *.jsonl worksheets "
        "(default {data_dir}/eligibility-labels).",
    ),
) -> None:
    """Apply oracle verdicts back into every worksheet file, preserving every other column.

    Runs each verdict through the ineligible-gate (`apply_oracle_verdicts`) and rewrites
    each `*.jsonl` worksheet file in place, one JSON object per line, same order and every
    pre-existing key preserved (M5). Hard-negative rows (H1, `applied/` prefix) accepted as
    `ineligible` are surfaced as a warning, not silently applied — Mit actually applied to
    those postings, so an ineligible verdict is a red flag worth a human look.
    """
    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    catalog = load_rules(settings.config_dir)
    worksheet_dir = _require_worksheet_dir(settings, worksheet)
    raw_verdicts: list[dict[str, Any]] = json.loads(verdicts_path.read_text(encoding="utf-8"))
    verdicts = [OracleVerdict(**item) for item in raw_verdicts]

    total_labeled = 0
    total_downgraded = 0
    total_overwritten = 0
    hard_negatives: list[str] = []
    by_verdict: dict[str, int] = {}
    for path in sorted(worksheet_dir.glob("*.jsonl")):
        rows = read_worksheet(path)
        merged_rows, result = apply_oracle_verdicts(rows, verdicts, catalog)
        path.write_text("".join(json.dumps(row) + "\n" for row in merged_rows), encoding="utf-8")
        total_labeled += result.labeled
        total_downgraded += result.downgraded
        total_overwritten += result.overwritten
        hard_negatives.extend(result.hard_negative_ineligible)
        for verdict_name, count in result.by_verdict.items():
            by_verdict[verdict_name] = by_verdict.get(verdict_name, 0) + count

    console.print(
        f"labeled {total_labeled} · downgraded {total_downgraded} · "
        f"overwritten {total_overwritten}"
    )
    if hard_negatives:
        console.print(
            f"[yellow]WARNING: hard-negative labels accepted as ineligible: "
            f"{', '.join(hard_negatives)}[/yellow]"
        )
    if by_verdict:
        console.print(
            "by_verdict: " + ", ".join(f"{k} {v}" for k, v in sorted(by_verdict.items()))
        )


@gate_app.command("request")
def gate_request_cmd(
    ctx: typer.Context,
    top: int = typer.Option(  # noqa: B008
        DEFAULT_TOP_N,
        "--top",
        help="Shortlist size to judge (default matches the pipeline's own shortlist, "
        "NOT `top`'s own default of 10 — the gate judges exactly what a run tailors).",
    ),
    out: Path | None = typer.Option(  # noqa: B008
        None,
        "--out",
        help="Output path for the gate request JSON (default {data_dir}/gate_request.json).",
    ),
) -> None:
    """Build a final-gate label request from the ranked shortlist's visible postings.

    Runs the same ranking `boardwatch top` shows, takes its visible postings, and builds
    one independence-preserving request row per posting (label = posting id, no `hint`,
    no prior engine verdict — `build_gate_request`/`build_label_request`'s contract).
    """
    # Imported here, not at module scope: cli.top_cmd's rank_open_postings is the shared
    # ranking path, but eligibility_cmd otherwise has no reason to depend on cli.top_cmd,
    # so the import stays local to the one command that needs it.
    from boardwatch.cli.top_cmd import NoProfileError, rank_open_postings

    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    catalog = load_rules(settings.config_dir)
    with app_ctx.engine.connect() as conn:
        profile_row = get_profile(conn)
    if profile_row is None:
        _no_profile()
    facts = parse_facts(profile_row.eligibility_facts_json)
    try:
        # `record_surfaced=False`: the request judges the shortlist and hands it straight back,
        # so it must not advance the queue. Consuming here suppressed every posting the gate had
        # just asked about, and the `boardwatch run` this handshake exists to feed then shortlisted
        # nothing for the whole `seen` TTL — the verdicts never reached an artifact.
        results = rank_open_postings(
            app_ctx.engine, settings, limit=top, record_surfaced=False
        )
    except NoProfileError:
        _no_profile()
    with app_ctx.engine.connect() as conn:
        versions = current_posting_versions(conn, None)
    request_id = uuid.uuid4().hex
    request = build_gate_request(results.visible, versions, facts, catalog, request_id=request_id)
    out_path = out if out is not None else settings.data_dir / "gate_request.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    console.print(f"wrote {out_path}")
    console.print(f"request_id={request_id} · {len(request['items'])} items")


@gate_app.command("apply")
def gate_apply_cmd(
    ctx: typer.Context,
    verdicts_path: Path = typer.Option(  # noqa: B008
        ...,
        "--verdicts",
        help="Path to the judge's gate verdicts JSON (a list of verdict objects).",
    ),
    top: int = typer.Option(  # noqa: B008
        DEFAULT_TOP_N,
        "--top",
        help="Shortlist size the verdicts were judged against (must match `gate request`'s "
        "--top); verdicts beyond this many are ignored, so a stale or tampered verdicts "
        "file cannot widen the gate past the shortlist it was built from.",
    ),
) -> None:
    """Apply final-gate verdicts to their postings' current OPEN versions.

    Runs each verdict through the same accept-then-keystone-span gate `record_gate_verdict`
    applies, and writes one `engine_kind='llm'` / `engine_version='final_gate:...'` row per
    posting under the user's STORED facts and policy (never the labeling pass's all-blocker
    reference policy — that would compute a different identity and the ranker's read would
    silently no-op). Demoted postings (written `ineligible`) are printed as a warning,
    mirroring `label apply`'s hard-negative warning.
    """
    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    catalog = load_rules(settings.config_dir)
    with app_ctx.engine.connect() as conn:
        profile_row = get_profile(conn)
    if profile_row is None:
        _no_profile()
    facts = parse_facts(profile_row.eligibility_facts_json)
    policy = parse_policy(profile_row.eligibility_policy_json)
    raw_verdicts: list[dict[str, Any]] = json.loads(verdicts_path.read_text(encoding="utf-8"))
    truncated = len(raw_verdicts) - top
    if truncated > 0:
        console.print(
            f"[yellow]{truncated} verdicts beyond --top {top} ignored[/yellow]"
        )
    verdicts = [OracleVerdict(**item) for item in raw_verdicts[:top]]

    with app_ctx.engine.connect() as conn:
        versions = current_posting_versions(conn, None)
    # D-019: a standalone stage (no pipeline above it) either receives a run_id or mints
    # one via ensure_run, so every attributable row is attributable and run_id IS NULL
    # keeps its one meaning ("predates attribution"). Mirrors `eligibility extract`'s own
    # standalone-LLM-lane pattern just above. Gated on there being at least one verdict to
    # apply — same guard `run_eligibility` uses (D-019) — so an empty/no-op invocation does
    # not log a run.
    run_id: int | None = ensure_run(app_ctx.engine, None) if verdicts else None
    with app_ctx.engine.begin() as conn:
        result = apply_gate_verdicts(
            conn, verdicts, versions=versions, facts=facts, policy=policy, catalog=catalog,
            run_id=run_id,
        )
    if run_id is not None:
        finish_run(app_ctx.engine, run_id)

    console.print(
        f"judged {result.judged} · ineligible {result.ineligible} · "
        f"downgraded {result.downgraded}"
    )
    if result.demoted_labels:
        console.print(
            f"[yellow]WARNING: demoted to ineligible: "
            f"{', '.join(result.demoted_labels)}[/yellow]"
        )


@eligibility_app.command("score")
def score_cmd(
    ctx: typer.Context,
    worksheet: Path | None = typer.Option(  # noqa: B008
        None,
        "--worksheet",
        help="Directory of labeled-set *.jsonl worksheets "
        "(default {data_dir}/eligibility-labels).",
    ),
) -> None:
    """Precision report against the human-verified labeled set (Gate P5, PROGRAM.md §3.P5).

    Exits non-zero when the labeled set contains at least one reference INELIGIBLE case
    and `meets_ship_gate()` fails — the mechanical audit drain (M1): an all-oracle,
    zero-audit labeled set cannot ship on precision alone.
    """
    app_ctx = build_context(ctx.obj)
    settings = app_ctx.settings
    catalog = load_rules(settings.config_dir)
    worksheet_dir = _require_worksheet_dir(settings, worksheet)
    cases = load_labeled_set(worksheet_dir)
    report = score(cases, catalog)

    precision_str = f"{report.precision:.0%}" if report.precision is not None else "undefined"
    console.print(
        f"total {report.total} · predicted_ineligible {report.predicted_ineligible} · "
        f"true_ineligible {report.true_ineligible}"
    )
    console.print(f"precision: {precision_str} · meets_gate: {report.meets_gate()}")
    if report.span_violations:
        console.print(f"[red]span violations: {', '.join(report.span_violations)}[/red]")
    if report.false_positives:
        console.print(
            "[red]false positives: "
            + ", ".join(f"{m.label} (expected {m.expected})" for m in report.false_positives)
            + "[/red]"
        )
    console.print(f"audited: {report.audited_coverage:.0%}")
    if report.audited_coverage < SHIP_AUDIT_COVERAGE_BAR:
        console.print(
            "[yellow]NOT integrity-anchored; run the audit before shipping B1-B4[/yellow]"
        )
    if report.is_measurable and not report.meets_ship_gate():
        raise typer.Exit(1)


@policy_app.callback(invoke_without_command=True)
def policy_root(ctx: typer.Context) -> None:
    """Show the materialised severity for every declared family."""
    if ctx.invoked_subcommand is not None:
        return
    app_ctx = build_context(ctx.obj)
    catalog = load_rules(app_ctx.settings.config_dir)
    with app_ctx.engine.connect() as conn:
        row = get_profile(conn)
    if row is None:
        _no_profile()
    policy = parse_policy(row.eligibility_policy_json)
    materialised = catalog.materialised_policy(policy)
    for family in catalog.families:
        console.print(f"{family.id}: {materialised[family.id]}")


@policy_app.command("set")
def policy_set(ctx: typer.Context, family: str, choice: str) -> None:
    """Set one family's severity to blocker, preference or ignore."""
    app_ctx = build_context(ctx.obj)
    catalog = load_rules(app_ctx.settings.config_dir)
    with app_ctx.engine.begin() as conn:
        row = get_profile(conn)
        if row is None:
            _no_profile()
        facts = parse_facts(row.eligibility_facts_json)
        policy = parse_policy(row.eligibility_policy_json)
        try:
            new_policy = set_policy(policy, catalog, family, choice)
        except typer.BadParameter as exc:
            typer.echo(exc.message)
            raise typer.Exit(code=1) from exc
        save_eligibility(
            conn,
            facts_json=facts_payload(facts),
            policy_json=new_policy.model_dump(mode="json"),
        )
    console.print(f"set policy {family} = {choice}")
