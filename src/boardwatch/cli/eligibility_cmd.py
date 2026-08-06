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

from collections import Counter
from typing import NoReturn, get_args

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from boardwatch.cli.context import build_context
from boardwatch.eligibility.catalog import FamilySpec, FieldSpec, RulesCatalog, load_rules
from boardwatch.eligibility.engine import current_evaluations
from boardwatch.eligibility.extract_llm import extract_and_record
from boardwatch.eligibility.facts import (
    Facts,
    Policy,
    PolicyChoice,
    facts_payload,
    parse_facts,
    parse_policy,
)
from boardwatch.eligibility.preflight import current_identity, run_eligibility
from boardwatch.llm.cache import ResponseCache
from boardwatch.llm.factory import build_client
from boardwatch.llm.payload import preview_text
from boardwatch.reports.abstain import build_abstain_report
from boardwatch.store.abstain_queries import count_requirement_dispositions
from boardwatch.store.queries import (
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
eligibility_app.add_typer(facts_app, name="facts")
eligibility_app.add_typer(policy_app, name="policy")


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
    evaluated = 0
    # This lane is invoked standalone, so it owns its run: a degenerate pipeline run whose
    # only stage is the LLM extraction. Minting rather than writing NULL is what keeps
    # `run_id IS NULL` meaning "predates attribution" and nothing else — but it is minted
    # LAZILY, on the first posting actually reached, matching run_eligibility. A provider
    # outage makes every call return None, and a run row attributing zero rows would turn
    # `runs` into a command log.
    run_id: int | None = None
    for current in ordered:
        if evaluated >= settings.llm.max_calls_per_run:
            break
        if run_id is None:
            run_id = ensure_run(app_ctx.engine, None)
        with app_ctx.engine.begin() as conn:
            extract_and_record(
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
        evaluated += 1
    if run_id is not None:
        finish_run(app_ctx.engine, run_id)
    console.print(f"extracted {evaluated} postings")


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
    report = build_abstain_report(catalog, counts)

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
        if rule.never_fired:
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
        f"{len(report.fully_abstaining)} fire but never decide · "
        f"{report.total_rows} rows across {len(evals)} evaluations"
    )
    if report.unattributed:
        console.print(f"[yellow]{report.unattributed} rows carry no rule_id[/yellow]")
    if report.out_of_catalog:
        # Closed catalog: an undeclared rule_id is a failure, never a new bucket.
        console.print(
            f"[red]FAILURE: {report.out_of_catalog_rows} rows carry rule_ids the catalog does "
            f"not declare: {', '.join(report.out_of_catalog)}[/red]"
        )
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
