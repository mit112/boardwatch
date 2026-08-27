"""boardwatch profile show|edit (§2.3, §3.6).

Profile skills are extracted by THE SAME taxonomy engine as postings, on every
save, and stored with the taxonomy_version used; a stale version is repaired
by the D21 preflight (Task 12)."""

from __future__ import annotations

from typing import Literal, get_args

import typer
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from sqlalchemy import Engine

from boardwatch.cli.context import build_context
from boardwatch.cli.eligibility_cmd import (
    set_career_field,
    set_fact,
    set_field_of_study,
    set_policy,
)
from boardwatch.core.settings import Settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.facts import facts_payload, parse_facts, parse_policy
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.store.queries import get_profile, save_eligibility, save_profile

console = Console()
profile_app = typer.Typer(no_args_is_help=True, help="Profile management.")

# D-246. The closed target vocabulary. Enforced here at the write boundary rather than by a
# SQLite CHECK, which would cost a full table rebuild to retrofit.
SeniorityBandChoice = Literal["entry", "mid", "senior", "any"]
# DERIVED from the Literal, never restated: a second hand-written list would drift from
# the one pydantic actually validates against.
SENIORITY_BAND_CHOICES: frozenset[str] = frozenset(get_args(SeniorityBandChoice))

ZERO_SKILL_WARNING = (
    "warning: no recognized skills in your profile — "
    "ranking will use title/recency/location only"
)


class ProfileInput(BaseModel):
    """Pydantic boundary validation for profile saves (issue #11, §6.1)."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    target_titles: list[str]
    exclude_titles: list[str]
    locations: list[str]
    remote_only: bool
    resume_max_pages: int = 1
    target_seniority_band: SeniorityBandChoice = "any"


def persist_profile(
    engine: Engine,
    settings: Settings,
    *,
    text: str,
    target_titles: list[str],
    exclude_titles: list[str],
    locations: list[str],
    remote_only: bool,
    resume_max_pages: int = 1,
    target_seniority_band: str = "any",
) -> list[str]:
    """Save the singleton profile, re-deriving skills via the taxonomy engine.

    Inputs pass through ProfileInput first — Pydantic at the boundary; a
    whitespace-only profile text is rejected before anything is persisted.
    """
    data = ProfileInput(
        text=text.strip(),
        target_titles=target_titles,
        exclude_titles=exclude_titles,
        locations=locations,
        remote_only=remote_only,
        resume_max_pages=resume_max_pages,
        target_seniority_band=target_seniority_band,
    )
    taxonomy = load_taxonomy(settings.config_dir)
    skills = sorted(taxonomy.extract(data.text))
    with engine.begin() as conn:
        save_profile(
            conn,
            text=data.text,
            target_titles=data.target_titles,
            exclude_titles=data.exclude_titles,
            locations=data.locations,
            remote_only=data.remote_only,
            skills=skills,
            taxonomy_version=taxonomy.version,
            resume_max_pages=data.resume_max_pages,
            # Explicit, never defaulted: a caller that forgot it would silently reset the
            # band on every `profile edit`.
            target_seniority_band=data.target_seniority_band,
        )
    if not skills:
        console.print(ZERO_SKILL_WARNING)
    else:
        console.print(f"Recognized {len(skills)} skills from your profile.")
    return skills


def split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]


@profile_app.command("show")
def show(ctx: typer.Context) -> None:
    """Render profile, recognized skills, and the taxonomy version used."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        row = get_profile(conn)
    if row is None:
        console.print("no profile yet — run `boardwatch init` first")
        raise typer.Exit(code=1)
    console.print(f"Profile text: {row.text[:120]}{'…' if len(row.text) > 120 else ''}")
    skills = row.skills_json or []
    console.print(f"Skills ({len(skills)}): {', '.join(skills) if skills else '—'}")
    console.print(f"Taxonomy version: {row.taxonomy_version}")
    console.print(f"Target titles: {', '.join(row.target_titles_json or []) or '—'}")
    console.print(f"Exclude titles: {', '.join(row.exclude_titles_json or []) or '—'}")
    console.print(f"Target seniority band: {row.target_seniority_band}")
    console.print(
        f"Locations: {', '.join(row.locations_json or []) or '—'} · "
        f"Remote only: {'yes' if row.remote_only else 'no'}"
    )


@profile_app.command("edit")
def edit(ctx: typer.Context) -> None:
    """Edit the profile; skills are re-derived on save (§3.6)."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        row = get_profile(conn)
    if row is None:
        console.print("no profile yet — run `boardwatch init` first")
        raise typer.Exit(code=1)
    text = typer.prompt("Profile text", default=row.text)
    targets = typer.prompt(
        "Target titles (comma separated)", default=", ".join(row.target_titles_json or [])
    )
    excludes = typer.prompt(
        "Exclude titles (comma separated)", default=", ".join(row.exclude_titles_json or [])
    )
    locations = typer.prompt(
        "Locations (comma separated)", default=", ".join(row.locations_json or [])
    )
    remote_only = typer.confirm("Remote only?", default=bool(row.remote_only))
    resume_max_pages = typer.prompt(
        "Résumé max pages", default=row.resume_max_pages, type=int
    )
    # Re-prompt on a bad answer rather than aborting the edit and discarding the answers
    # already entered this run — the same reason the eligibility prompts below loop. A bare
    # prompt would let a typo like "Entry" raise inside persist_profile and lose everything.
    while True:
        target_seniority_band = typer.prompt(
            "Target seniority band (entry/mid/senior/any)",
            default=getattr(row, "target_seniority_band", None) or "any",
        ).strip()
        if target_seniority_band in SENIORITY_BAND_CHOICES:
            break
        console.print(
            f"{target_seniority_band!r} is not a seniority band; "
            f"choose one of {', '.join(sorted(SENIORITY_BAND_CHOICES))}"
        )
    persist_profile(
        app_ctx.engine,
        app_ctx.settings,
        text=text,
        target_titles=split_csv(targets),
        exclude_titles=split_csv(excludes),
        locations=split_csv(locations),
        remote_only=remote_only,
        resume_max_pages=resume_max_pages,
        target_seniority_band=target_seniority_band,
    )

    # The same four eligibility prompts as init, so the feature is reachable on an existing
    # install. Seeded from the stored facts and policy, so a skipped answer keeps the current
    # value rather than clearing it. persist_profile never touches the eligibility columns.
    catalog = load_rules(app_ctx.settings.config_dir)
    facts = parse_facts(row.eligibility_facts_json)
    policy = parse_policy(row.eligibility_policy_json)
    if typer.confirm("Update eligibility checks?", default=False):
        if catalog.career_fields:
            field_hint = ", ".join(sorted(catalog.career_fields))
            while True:
                answer = typer.prompt(f"Your career field [{field_hint}]", default="")
                if not answer.strip():
                    break
                try:
                    facts = set_career_field(facts, catalog, answer.strip())
                    break
                except typer.BadParameter as exc:
                    console.print(exc.message)
        if catalog.fields_of_study:
            study_hint = ", ".join(sorted(s.id for s in catalog.fields_of_study))
            while True:
                answer = typer.prompt(f"Your field of study [{study_hint}]", default="")
                if not answer.strip():
                    break
                try:
                    facts = set_field_of_study(facts, catalog, answer.strip())
                    break
                except typer.BadParameter as exc:
                    console.print(exc.message)
        for family in catalog.families:
            for field_spec in family.fields:
                # Re-prompt on a bad answer rather than aborting the edit and discarding the
                # answers already entered this run.
                while True:
                    answer = typer.prompt(
                        f"{family.question} [{field_spec.name}: "
                        f"{', '.join(field_spec.choices) or field_spec.type}]",
                        default="",
                    )
                    if not answer.strip():
                        break
                    try:
                        facts = set_fact(
                            facts, catalog,
                            f"{family.fact}.{field_spec.name}"
                            if len(family.fields) > 1
                            else family.fact,
                            answer.strip(),
                        )
                        break
                    except typer.BadParameter as exc:
                        console.print(exc.message)
            while True:
                choice = typer.prompt(
                    f"How should {family.label} affect your results?",
                    default=policy.families.get(family.id, family.default_policy),
                )
                try:
                    policy = set_policy(policy, catalog, family.id, choice)
                    break
                except typer.BadParameter as exc:
                    console.print(exc.message)
        with app_ctx.engine.begin() as conn:
            save_eligibility(
                conn,
                facts_json=facts_payload(facts),
                policy_json=policy.model_dump(mode="json"),
            )
