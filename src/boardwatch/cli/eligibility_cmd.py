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

from typing import NoReturn, get_args

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.eligibility.catalog import FamilySpec, FieldSpec, RulesCatalog, load_rules
from boardwatch.eligibility.facts import (
    Facts,
    Policy,
    PolicyChoice,
    facts_payload,
    parse_facts,
    parse_policy,
)
from boardwatch.store.queries import get_profile, save_eligibility

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
        if not value.isdigit():
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
    valid_families = [spec.id for spec in catalog.families]
    severities = get_args(PolicyChoice)
    with app_ctx.engine.begin() as conn:
        row = get_profile(conn)
        if row is None:
            _no_profile()
        facts = parse_facts(row.eligibility_facts_json)
        policy = parse_policy(row.eligibility_policy_json)
        if family not in valid_families:
            typer.echo(
                f"unknown policy family {family!r}. Valid families: {', '.join(valid_families)}"
            )
            raise typer.Exit(code=1)
        if choice not in severities:
            typer.echo(f"unknown severity {choice!r}. Valid: {', '.join(severities)}")
            raise typer.Exit(code=1)
        new_policy = Policy(families={**policy.families, family: choice})
        save_eligibility(
            conn,
            facts_json=facts_payload(facts),
            policy_json=new_policy.model_dump(mode="json"),
        )
    console.print(f"set policy {family} = {choice}")
