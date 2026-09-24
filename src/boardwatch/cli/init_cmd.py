"""boardwatch init — §2.2 first-run (P1): companies via starter-set / registry
search / paste, then the P0 profile + filter flow (unchanged)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.cli.eligibility_cmd import (
    set_career_field,
    set_fact,
    set_field_of_study,
    set_policy,
)
from boardwatch.cli.profile_cmd import persist_profile, split_csv
from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.core.settings import load_settings
from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.facts import Facts, Policy, facts_payload
from boardwatch.rank.role_taxonomy import (
    BUNDLED_FIELDS,
    MISSING_ROLE_TAXONOMY,
    ROLE_TAXONOMY_FILE,
    ROLE_TAXONOMY_VERSION,
    RoleTaxonomyError,
    role_token,
    write_role_taxonomy,
)
from boardwatch.registry.loader import load_catalog, starter_entries
from boardwatch.registry.validate import CompanyEntry
from boardwatch.store.queries import get_profile, save_eligibility, upsert_watch
from boardwatch.tailor.render.latex import resolve_template

console = Console()


def _paste_target(token: str) -> tuple[str, str]:
    token = token.strip()
    if ":" not in token and "/" not in token:  # deviation 9: bare token is a Greenhouse slug
        return "greenhouse", token.lower()
    return parse_board_target(token)


def _seed_resume_template(config_dir: Path) -> bool:
    """Write the bundled LaTeX template into the config dir when it is not already there.

    T2 made a run refuse rather than fall back to the bundled default, because that default's
    header and education are placeholder identity and a silent fallback delivers a résumé
    addressed to nobody. That refusal stands; what it left behind was a fresh install with
    nothing to edit. Seeding the file changes only that: the same bundled text is now on disk
    where the user can edit it, and `_validate_template`'s placeholder-phrase catalog goes on
    refusing it verbatim until they do.

    NEVER overwrites: the edited file is the deliverable, and `init` is re-runnable.
    """
    candidate = config_dir / "resume_template.tex"
    if candidate.exists():
        return False
    config_dir.mkdir(parents=True, exist_ok=True)
    candidate.write_text(resolve_template(None), encoding="utf-8")
    return True


def gather_role_taxonomy(config_dir: Path) -> None:
    """Ask for the user's role taxonomy and write it, validated (P2 item 8, D-054).

    The prompts are field-neutral and suggest no content: the only vocabulary shown is the set of
    fields boardwatch ships role knowledge for, the way the career-field prompt shows its catalog.
    Naming one of those fields IS the answer (the bundled taxonomy); any other field's families
    and words are the user's own. A bad answer re-prompts; blank skips, and the role gate then
    abstains rather than guessing.
    """
    path = config_dir / ROLE_TAXONOMY_FILE
    bundled_hint = ", ".join(sorted(BUNDLED_FIELDS))
    while True:
        field = typer.prompt(
            f"Your field, for the role filter [{bundled_hint}, or your own id; blank to skip]",
            default="",
        ).strip()
        if not field:
            if path.exists():
                console.print(f"Role taxonomy unchanged at {path}.")
            else:
                console.print(
                    f"No role taxonomy set, so the role filter abstains ({MISSING_ROLE_TAXONOMY})"
                    " — set one with `boardwatch profile role-taxonomy`."
                )
            return
        try:
            role_token(field, "field")
        except RoleTaxonomyError as exc:
            console.print(str(exc), markup=False)
            continue
        document: dict[str, Any] = {"version": ROLE_TAXONOMY_VERSION, "field": field}
        if field in BUNDLED_FIELDS:
            document["bundled"] = True
        else:
            family_ids = split_csv(
                typer.prompt("Role families in your field (comma separated ids)")
            )
            document["role_families"] = [
                {
                    "id": family_id,
                    "title_words": split_csv(
                        typer.prompt(f"Title words for {family_id} (comma separated)")
                    ),
                }
                for family_id in family_ids
            ]
            excludes = split_csv(
                typer.prompt(
                    "Title words that rule a posting out (comma separated, blank for none)",
                    default="",
                )
            )
            if excludes:
                document["exclude_words"] = excludes
        try:
            taxonomy = write_role_taxonomy(config_dir, document)
        except RoleTaxonomyError as exc:
            console.print(str(exc), markup=False)
            continue
        console.print(f"Role taxonomy for {taxonomy.field!r} written to {path}.", markup=False)
        return


def role_taxonomy(ctx: typer.Context) -> None:
    """Set the role taxonomy the ranker's role filter reads, replacing the current one."""
    # load_settings, not build_context: this writes one config file and never opens the store.
    gather_role_taxonomy(load_settings(data_dir=ctx.obj).config_dir)


def init(ctx: typer.Context) -> None:
    """Interactive first-run: companies (3 paths), profile, filters."""
    app_ctx = build_context(ctx.obj)
    template_path = app_ctx.settings.config_dir / "resume_template.tex"
    if _seed_resume_template(app_ctx.settings.config_dir):
        console.print(
            f"Wrote a starter résumé template to {template_path}. "
            "Edit its header and education before your first run — a run refuses the "
            "unedited placeholder identity."
        )
    catalog = load_catalog()
    catalog_index: dict[tuple[str, str], CompanyEntry] = {
        (str(e.provider), e.slug): e for e in catalog
    }
    choice = typer.prompt(
        "Companies: [1] Starter set  [2] Search registry  [3] Paste slugs/URLs", default="1"
    )
    targets: list[tuple[str, str]] = []
    if choice == "1":
        targets = [(e.provider, e.slug) for e in starter_entries(catalog)]
    elif choice == "2":
        query = typer.prompt("Search registry").casefold()
        hits = [e for e in catalog if query in e.name.casefold() or query in e.slug.casefold()]
        for e in hits:
            if typer.confirm(f"Watch {e.name} ({e.provider}:{e.slug})?", default=True):
                targets.append((e.provider, e.slug))
    else:
        raw = typer.prompt("Paste slugs or board URLs (comma/newline separated)")
        for token in split_csv(raw):
            try:
                targets.append(_paste_target(token))
            except UnknownBoardURL as exc:
                console.print(f"[yellow]skipping {token!r}: {exc}[/yellow]")

    with app_ctx.engine.begin() as conn:
        for provider, slug in targets:
            entry = catalog_index.get((provider, slug))
            upsert_watch(
                conn, provider=provider, slug=slug,
                name=entry.name if entry else slug,
                source="registry" if entry else "user",
            )

    # ---- profile + filters: unchanged from P0 #11 (moved verbatim) ----
    text = typer.prompt("Profile text (paste resume text or a short profile)")
    targets_t = typer.prompt("Target titles (comma separated, blank for none)", default="")
    excludes = typer.prompt("Exclude titles (comma separated, blank for none)", default="")
    locations = typer.prompt("Locations (comma separated, blank for none)", default="")
    remote_only = typer.confirm("Remote only?", default=False)
    # T186. `init` on an EXISTING install must not silently reset the target countries to
    # undeclared: under B3 an undeclared target makes both location gates inert, which over the
    # live store lifts every non-US drop and review hold at once. `profile edit` is where the
    # value changes; `init` keeps what the row already says.
    with app_ctx.engine.connect() as conn:
        existing = get_profile(conn)
    persist_profile(
        app_ctx.engine, app_ctx.settings, text=text,
        target_titles=split_csv(targets_t), exclude_titles=split_csv(excludes),
        locations=split_csv(locations), remote_only=remote_only,
        target_countries=(
            () if existing is None else tuple(existing.target_countries_json or ())
        ),
    )

    # Eligibility is optional and comes AFTER persist_profile: profile.text is NOT NULL, so
    # facts cannot be written before the row exists (§4.6). Exactly TWO prompt call sites plus
    # one confirm drive every family, so R11's pin stays constant as the catalog grows (D-P2-8).
    # A third prompt sets `career_field` and a fourth `field_of_study`. Both are single
    # catalog-scalars, not per-family — one prompt each whatever the size of their
    # vocabularies, so the pin stays constant there too.
    if typer.confirm("Set up eligibility checks now?", default=False):
        rules_catalog = load_rules(app_ctx.settings.config_dir)
        facts, policy = Facts(), Policy()
        if rules_catalog.career_fields:
            field_hint = ", ".join(sorted(rules_catalog.career_fields))
            while True:
                answer = typer.prompt(f"Your career field [{field_hint}]", default="")
                if not answer.strip():
                    break
                try:
                    facts = set_career_field(facts, rules_catalog, answer.strip())
                    break
                except typer.BadParameter as exc:
                    console.print(exc.message)
        if rules_catalog.fields_of_study:
            study_hint = ", ".join(sorted(s.id for s in rules_catalog.fields_of_study))
            while True:
                answer = typer.prompt(f"Your field of study [{study_hint}]", default="")
                if not answer.strip():
                    break
                try:
                    facts = set_field_of_study(facts, rules_catalog, answer.strip())
                    break
                except typer.BadParameter as exc:
                    console.print(exc.message)
        for family in rules_catalog.families:
            for field_spec in family.fields:
                # Compose the choice hint outside the f-string: a nested-quote f-string
                # unparses differently across CPython 3.12 patch releases, which would make
                # the R11 EXPECTED_INIT_PROMPTS snapshot pass on one patch and fail on another.
                choice_hint = ", ".join(field_spec.choices) or field_spec.type
                # Re-prompt on a bad answer instead of aborting the whole wizard and losing
                # every eligibility answer entered so far (the profile row is already saved).
                while True:
                    answer = typer.prompt(
                        f"{family.question} [{field_spec.name}: {choice_hint}]",
                        default="",
                    )
                    if not answer.strip():
                        break
                    try:
                        facts = set_fact(
                            facts, rules_catalog,
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
                    default=family.default_policy,
                )
                try:
                    policy = set_policy(policy, rules_catalog, family.id, choice)
                    break
                except typer.BadParameter as exc:
                    console.print(exc.message)
        with app_ctx.engine.begin() as conn:
            save_eligibility(
                conn,
                facts_json=facts_payload(facts),
                policy_json=policy.model_dump(mode="json"),
            )

    # Asked whatever the eligibility answer: the role taxonomy is a RANKER input. Never
    # overwritten here, because `init` is re-runnable and the file is the user's answer.
    role_taxonomy_path = app_ctx.settings.config_dir / ROLE_TAXONOMY_FILE
    if role_taxonomy_path.exists():
        console.print(
            f"Keeping your role taxonomy at {role_taxonomy_path}; change it with "
            "`boardwatch profile role-taxonomy`.",
            markup=False,
        )
    else:
        gather_role_taxonomy(app_ctx.settings.config_dir)

    console.print(f"Watching {len(targets)} companies. Run `boardwatch scan` next.")
