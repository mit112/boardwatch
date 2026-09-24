"""boardwatch companies — search / add / remove / list / discover / import / export (§2.3).
`export` is the registry-format contribution funnel; data-portability export
(--format jsonl|csv) is P2 and intentionally absent."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Any, NamedTuple

import typer
import yaml
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from sqlalchemy import Row, inspect

from boardwatch.cli._json_out import emit_json, narrative
from boardwatch.cli.context import build_context
from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.core.clock import utcnow
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.core.settings import Settings, load_settings
from boardwatch.lanes.admission import CompanyBudget
from boardwatch.lanes.github_lists import (
    candidate_document,
    discover,
    fetch_listings,
    one_line,
    select,
)
from boardwatch.lanes.grnh_seeds import GRNH_HOSTS, MAX_ATTEMPTS_CONSIDERED, SeedCoverage
from boardwatch.lanes.grnh_seeds import candidate_document as grnh_candidate_document
from boardwatch.lanes.grnh_seeds import resolve as grnh_resolve
from boardwatch.lanes.grnh_seeds import without_known as grnh_without_known
from boardwatch.providers.base import BoardHealth, Provider
from boardwatch.providers.registry import PROVIDER_NAMES, derive_employer_name
from boardwatch.providers.workday import FacetBucket, FacetUnavailable, read_facet_catalog
from boardwatch.registry.loader import load_catalog
from boardwatch.registry.validate import CatalogError, CompanyEntry, validate_entries
from boardwatch.scan.coordinator import default_providers
from boardwatch.store.queries import (
    companies_named_by_slug,
    company_exists,
    list_watches,
    set_company_name,
    stored_slug,
    unwatch,
    unwatched_scannable_companies,
    upsert_watch,
)
from boardwatch.store.seed_queries import unresolved_seed_count, unresolved_seeds

companies_app = typer.Typer(no_args_is_help=True, help="Manage watched company boards.")
console = Console()

# D27 vocabulary: OK/EMPTY are positive evidence the board exists; DEAD means the slug is
# wrong; ERROR/UNREACHABLE are absence of evidence, which is not evidence of absence — so
# --verify skips them rather than writing a watch it could not substantiate.
_UNPROVEN = frozenset({BoardHealth.DEAD, BoardHealth.ERROR, BoardHealth.UNREACHABLE})

_VERIFY_HELP = "Probe each board before watching it; skip any that cannot be confirmed."

# Only Workday can be sliced today: the `#group=Descriptor` fragment, the live catalog and the
# descriptor -> opaque-id resolution all live in `providers/workday.py` and no sibling provider
# has an equivalent. Named here rather than discovered by probing, so refusing a board of
# another provider costs no request.
_SLICEABLE_PROVIDERS = frozenset({"workday"})

# The facet groups an operator would actually slice a board on, keyed on the parameter with its
# non-alphanumerics dropped and its case folded. The parameter is the TENANT's own JSON key and
# tenants spell one dimension differently -- measured live 2026-09-07, NVIDIA answers
# `jobFamilyGroup` and T-Mobile answers `Job_Family_Group` for the same thing, so matching the
# literal spelling would hide the only sliceable group one of them has.
_SLICEABLE_GROUPS = frozenset({"jobfamilygroup", "jobfamily"})


def _probe(
    targets: list[tuple[str, str]], settings: Settings
) -> dict[tuple[str, str], BoardHealth]:
    """Live-healthcheck (provider, slug) pairs. One Fetcher for the whole set, so its
    per-host pacing applies across the batch instead of per board."""
    providers = default_providers()
    fetcher = Fetcher(settings)
    return {(p, s): _healthcheck(providers[p], fetcher, s) for p, s in targets}


def _healthcheck(provider: Provider, fetcher: Fetcher, slug: str) -> BoardHealth:
    """Providers map FetchFailure to a BoardHealth, but Fetcher.get only converts
    TransportError and retryable statuses — httpx.TooManyRedirects and DecodingError are
    RequestError, not TransportError, so they escape both. A CLI flag whose whole job is
    to report unreachable boards must not traceback on one; bucket it as UNREACHABLE
    (same skip decision either way) the way the scan coordinator already does."""
    try:
        return provider.healthcheck(fetcher, slug)
    except Exception:
        return BoardHealth.UNREACHABLE


def _catalog_index() -> dict[tuple[str, str], CompanyEntry]:
    return {(e.provider, e.slug): e for e in load_catalog()}


def _nothing_stored(provider: str, slug: str) -> bool:
    """No `companies` table, so nothing is stored and every candidate is new.

    Reached by ASKING the schema (`inspect(...).has_table`), not by catching the query's failure.
    Two reasons. Classifying behaviour by string-matching an `OperationalError` message is exactly
    what this repo forbids; and a bare `except OperationalError` would equally swallow a locked or
    corrupt store, which is a different problem with a different answer.

    On a fresh machine an absent schema is not an error — nothing is watched, so every board really
    is new, and the header's "already stored 0" says so. A named function rather than
    `lambda p, s: False` so the reason lives with the behaviour and it cannot be mistaken for a
    stub somebody forgot to finish.
    """
    return False


def _normalized(entry: CompanyEntry) -> CompanyEntry:
    """Apply the provider's slug normalization, which `add` gets from parse_board_target
    and the import path otherwise skips entirely."""
    _, slug = parse_board_target(f"{entry.provider}:{entry.slug}")
    return entry if slug == entry.slug else entry.model_copy(update={"slug": slug})


@companies_app.command("add")
def add(
    ctx: typer.Context,
    target: str,
    verify: bool = typer.Option(False, "--verify", help=_VERIFY_HELP),
) -> None:
    """Watch a board by provider:slug or board URL."""
    try:
        provider, slug = parse_board_target(target)
    except UnknownBoardURL as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc  # no DB write on the failed-validation path
    entry = _catalog_index().get((provider, slug))
    source = "registry" if entry else "user"
    # Off the registry when it knows this board, and otherwise the employer name its SLUG
    # names — never the slug itself, which is what named 35 live rows after their hostname and
    # left `normalize_company` returning a different string for two rows naming one employer
    # (T74). `derive_employer_name` is the single source of truth for that reading; when it
    # cannot read one, the slug stands, because a guessed employer name merges two companies.
    name = entry.name if entry else (derive_employer_name(provider, slug) or slug)
    app_ctx = build_context(ctx.obj)
    if verify:
        health = _probe([(provider, slug)], app_ctx.settings)[(provider, slug)]
        if health in _UNPROVEN:
            console.print(f"[red]not watching {provider}:{slug} — probe returned {health}.[/red]")
            raise typer.Exit(code=1)  # unproven board: no DB write
        if health is BoardHealth.EMPTY:
            console.print(
                f"[yellow]note:[/yellow] {provider}:{slug} is reachable but returned no "
                "postings. Watching it anyway."
            )
    with app_ctx.engine.begin() as conn:
        watched = upsert_watch(conn, provider=provider, slug=slug, name=name, source=source)
    if watched == slug:
        console.print(f"Watching {provider}:{slug} (source={source}).")
    elif "#" in watched and "#" not in slug:
        # The whole board resolved onto its facet SLICE (T71): the slice is an in-place narrowing
        # of this very row, so watching the plain board again would list everything the slice
        # was made to exclude. Nothing here widens it back — that is the slice's slug, edited
        # in place — so say exactly that rather than call a fragment a case difference.
        console.print(
            f"[yellow]note:[/yellow] {provider}:{slug} is already watched as the facet slice "
            f"{provider}:{watched}; no second board was added. To watch the whole board again, "
            "replace the slice's slug in place."
        )
        console.print(f"Watching {provider}:{watched}.")
    else:
        # A silent no-op would leave the operator believing a new board was added. Say which
        # row the watch landed on, and do not claim `source`: the stored row keeps its own.
        console.print(
            f"[yellow]note:[/yellow] {provider}:{slug} differs only in slug case from the "
            f"board already stored as {provider}:{watched}; no second board was added."
        )
        console.print(f"Watching {provider}:{watched}.")
    if provider == "smartrecruiters":
        console.print(
            "[yellow]note:[/yellow] SmartRecruiters cannot confirm a board exists — "
            "an unknown company returns an empty board, not an error. If scans stay "
            "empty, re-check the slug."
        )


@companies_app.command("remove")
def remove(ctx: typer.Context, target: str) -> None:
    provider, slug = parse_board_target(target)
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.begin() as conn:
        # unwatch already resolves case via stored_slug; echo the STORED spelling, not the
        # typed one, so `remove ashby:KAYAK` reports `ashby:kayak` like add/import (D-339).
        stored = stored_slug(conn, provider=provider, slug=slug)
        changed = unwatch(conn, provider=provider, slug=slug)
    console.print(f"Unwatched {provider}:{stored}." if changed else "No such watch.")


@companies_app.command("names")
def names(
    ctx: typer.Context,
    apply_: bool = typer.Option(
        False, "--apply", help="Actually rewrite the names. Without it this only reports."
    ),
) -> None:
    """Repair company rows named after their SLUG rather than their employer (T74).

    WHY THIS EXISTS. `companies.name` is the input to `normalize_company`, which is a component
    of the `cross_host` posting identity. A board the bundled registry does not know used to be
    watched with `name = slug`, so a board on `careers.acme.test` was named `careers.acme.test`
    and a Workday board `acme.wd1.myworkdayjobs.com/acme/Acme_External_Site`. Two rows naming
    ONE employer therefore normalized to two different strings and could not group at all — and
    the moment a truncated board's coverage rises, the same requisition genuinely exists under
    both, because the two boards have disjoint provider id spaces.

    WHAT IT WILL NOT DO. A row whose employer name is not derivable from its slug is LEFT ALONE
    and listed as such. A wrong employer name merges two different companies' postings, which is
    far worse than a duplicate, so nothing here guesses. Rows named by the registry or by a lane
    are not touched at all: they are already employer names, and `upsert_lane_company` records
    that overwriting one is unrecoverable.

    AFTER --apply, RUN `boardwatch identities backfill`. Every identity row written under an old
    name is stale the instant the name changes; the backfill is the drain, and `identities
    verify` is what reports the gap until it runs.

    Reports by default. Safe to re-run: a row already carrying its derived name plans no write.
    """
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        rows = companies_named_by_slug(conn)
    planned = [
        (row, derive_employer_name(row.provider, row.slug))
        for row in rows
    ]
    # CASEFOLDED, and that is the whole guard on this command's own promise above that a row
    # already carrying an employer name is not touched. `companies_named_by_slug` matches
    # `name == slug` case-INSENSITIVELY, so a registry row whose catalog name differs from its
    # slug only in capitalisation (`OpenAI`/`openai`, `SpaceX`/`spacex`, `AbbVie`/`abbvie`) is
    # in the population — and `derive_employer_name` cannot re-capitalise, so an exact `!=`
    # planned to REWRITE 100 correct names down to their lowercase slug. `companies.name`
    # reaches the delivered artifact and the résumé filename, so that is a visible regression,
    # not a cosmetic one. Differing only by case means the name is already the employer's.
    changing = [
        (row, derived)
        for row, derived in planned
        if derived and derived.casefold() != row.name.casefold()
    ]
    undecidable = [row for row, derived in planned if derived is None]
    unchanged = len(planned) - len(changing) - len(undecidable)

    if not rows:
        console.print("names: no company is named after its slug — nothing to repair.")
        return
    table = Table("provider", "slug", "stored name", "derived employer", "action")
    for row, derived in planned:
        if derived is None:
            action = "left as is (not derivable)"
        elif derived.casefold() == row.name.casefold():
            action = "already correct"
        else:
            action = "rewrite" if apply_ else "would rewrite"
        table.add_row(row.provider, row.slug, row.name, derived or "—", action)
    console.print(table)

    if not apply_:
        console.print(
            f"names: {len(changing)} row(s) would be rewritten, {unchanged} already correct, "
            f"{len(undecidable)} not derivable. Re-run with --apply to write."
        )
        if changing:
            console.print(
                "  then run `boardwatch identities backfill` — the stored `cross_host` "
                "identities are keyed on the OLD name until it does."
            )
        return

    with app_ctx.engine.begin() as conn:
        written = sum(
            set_company_name(conn, company_id=row.id, name=derived) for row, derived in changing
        )
    console.print(
        f"names: rewrote {written} row(s), {unchanged} already correct, "
        f"{len(undecidable)} not derivable and left as they were."
    )
    if written:
        console.print(
            "  now run `boardwatch identities backfill`: every identity row written under the "
            "old name is stale until it does."
        )


@companies_app.command("search")
def search(ctx: typer.Context, query: str) -> None:
    """Case-insensitive substring search over the bundled catalog (offline)."""
    q = query.casefold()
    hits = [e for e in load_catalog() if q in e.name.casefold() or q in e.slug.casefold()]
    table = Table("name", "provider", "slug", "starter")
    for e in hits:
        table.add_row(e.name, e.provider, e.slug, "★" if "starter" in e.tags else "")
    console.print(table)


@companies_app.command("list")
def list_(
    ctx: typer.Context,
    as_json: bool = typer.Option(
        False, "--json", help="Emit one JSON object instead of the table."
    ),
) -> None:
    """Every watched board with its source, health and last success."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        rows = list_watches(conn)
    if as_json:
        emit_json({"rows": [dict(row._mapping) for row in rows]})
        return
    table = Table("provider", "slug", "source", "watched", "last_health", "last_ok_at")
    for r in rows:
        table.add_row(
            r.provider, r.slug, r.source, "yes" if r.watched else "no",
            r.last_health or "—", str(r.last_ok_at or "—"),
        )
    console.print(table)


class _Bucket(NamedTuple):
    """One bucket as this command reports it. `target` is the whole point: descriptor case and
    spacing are matched EXACTLY against the live catalog, so an operator who retypes a
    descriptor by hand earns a board that fails every scan — it is spelt out per bucket rather
    than left for the reader to assemble.

    The opaque facet id is deliberately NOT here. It is a tenant-specific hash resolved from
    the live board on every fetch and stored nowhere, and publishing it invites someone to
    paste it into a slug, where it means nothing on any other tenant.
    """

    descriptor: str
    postings: int | None
    target: str


class _Group(NamedTuple):
    """One facet group: the parameter an operator types, whether the default view shows it,
    and its buckets biggest-first."""

    parameter: str
    sliceable: bool
    buckets: tuple[_Bucket, ...]


def _group_is_sliceable(parameter: str) -> bool:
    """Whether this facet group is one an operator would narrow a board to.

    The bound the default view applies. Not cosmetic: one live tenant answers 1,091 `locations`
    buckets and 51 `locationRegionStateProvince` buckets beside the ONE group that decides
    which roles a slice holds (measured 2026-09-07), so printing every group by default buries
    the only useful lines under four figures of noise. `--all` prints them.
    """
    return "".join(c for c in parameter if c.isalnum()).casefold() in _SLICEABLE_GROUPS


def _buckets(provider: str, base_slug: str, parameter: str, buckets: list[FacetBucket]) -> \
        tuple[_Bucket, ...]:
    """One group's buckets, biggest first.

    A bucket whose count the board did not state sorts LAST rather than as 0 — it is unknown,
    not zero, and ranking it as zero would claim the board said something it did not. Ties
    break on the descriptor so the order is total and the output is reproducible.
    """
    ordered = sorted(
        buckets, key=lambda b: (b.postings is None, -(b.postings or 0), b.descriptor)
    )
    return tuple(
        _Bucket(
            descriptor=bucket.descriptor,
            postings=bucket.postings,
            target=f"{provider}:{base_slug}#{parameter}={bucket.descriptor}",
        )
        for bucket in ordered
    )


@companies_app.command("facets")
def facets(
    ctx: typer.Context,
    target: str,
    all_groups: bool = typer.Option(
        False, "--all", help="Print every facet group, not only the ones worth slicing on."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit one JSON object instead of the listing."
    ),
) -> None:
    """Every facet bucket a board offers to slice on, with the number of postings in each.

    READ-ONLY and store-free by construction: it never calls `build_context`, so it cannot
    migrate a database, and it needs no watched board — the whole point is to inspect a board
    BEFORE deciding to watch it. Its one cost is a single unfiltered request to the board.

    It exists because a slice's descriptor is matched against the live catalog EXACTLY, and
    until this command the only way to learn a spelling was to guess, watch the scan fail and
    read the offered names out of the stored error. The counts are what make the answer
    actionable: a blanket `#jobFamilyGroup=Technology` was wrong on 7 of 10 live boards probed
    2026-09-07 — the group holding engineering was `Engineering`, `20 - SOFTWARE` or
    `NGC - Engineering`, on one board the PARAMETER was `Job_Family_Group` instead, and on one
    board no bucket held engineering at all, which is also a real answer.
    """
    out = narrative(as_json, console)
    try:
        provider, slug = parse_board_target(target)
    except UnknownBoardURL as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if provider not in _SLICEABLE_PROVIDERS:
        # Named, and non-zero. An empty listing would read as "this board has no facets", a
        # different and false claim: the provider has no slicing mechanism at all.
        out.print(
            f"[red]{provider} boards cannot be sliced by facet — only "
            f"{', '.join(sorted(_SLICEABLE_PROVIDERS))} offers a facet catalog, so there is "
            f"nothing to list for {provider}:{slug}.[/red]"
        )
        raise typer.Exit(code=1)
    # load_settings, NOT build_context: this command must not open — and therefore must not
    # migrate — the store to answer a question about a board it may never watch (D-279).
    settings = load_settings(data_dir=ctx.obj)
    try:
        base_slug, catalog = read_facet_catalog(Fetcher(settings), slug)
    except (FetchFailure, FacetUnavailable, ValueError) as exc:
        out.print(f"[red]could not read {provider}:{slug}'s facet catalog: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    shown = [p for p in catalog if all_groups or _group_is_sliceable(p)]
    # Sliceable groups first even under `--all`, so the group that decides which roles a slice
    # holds is never printed below a `distance` or a province list.
    shown.sort(key=lambda p: not _group_is_sliceable(p))
    groups = [
        _Group(p, _group_is_sliceable(p), _buckets(provider, base_slug, p, catalog[p]))
        for p in shown
    ]
    withheld = [p for p in catalog if p not in shown]
    if as_json:
        emit_json(
            {
                "provider": provider,
                "slug": base_slug,
                "groups": [
                    dict(group._asdict(), buckets=[b._asdict() for b in group.buckets])
                    for group in groups
                ],
                "groups_withheld": withheld,
            }
        )
        return
    _print_facets(provider, base_slug, groups, withheld)


def _print_facets(
    provider: str, base_slug: str, groups: list[_Group], withheld: list[str]
) -> None:
    """The human rendering.

    Every tenant-derived string goes out with rich's markup and highlighting OFF and soft wrap
    ON, or is escaped — for three separate reasons that each break the one thing this command
    is for. A descriptor containing `[` is read as markup (the escape `companies discover`
    already documents), and rich word-wraps AND crops at the console width, either of which
    turns a copy-pasteable slug into one that is not.
    """
    console.print(
        f"{provider}:{base_slug} — {len(groups) + len(withheld)} facet group(s), "
        f"{len(groups)} shown."
    )
    for group in groups:
        counted = [b.postings for b in group.buckets if b.postings is not None]
        stated = f", {sum(counted)} postings" if len(counted) == len(group.buckets) else ""
        console.print(
            f"\n[bold]{escape(group.parameter)}[/bold] — "
            f"{len(group.buckets)} bucket(s){stated}",
            highlight=False,
        )
        for bucket in group.buckets:
            console.print(
                f"  {'—' if bucket.postings is None else bucket.postings:>7}  {bucket.target}",
                markup=False, highlight=False, soft_wrap=True,
            )
    if not groups:
        console.print(
            "\nNothing worth slicing: this board offers no job-family or job-category facet "
            "group, so a slice could only narrow it by location or time type."
        )
    if withheld:
        console.print(
            f"\n{len(withheld)} group(s) not shown ({', '.join(withheld)}); --all prints them.",
            markup=False, highlight=False, soft_wrap=True,
        )


@companies_app.command("export")
def export(ctx: typer.Context) -> None:
    """Emit the user's watches as registry-format YAML (the §3.2 contribution funnel)."""
    app_ctx = build_context(ctx.obj)
    with app_ctx.engine.connect() as conn:
        rows = list_watches(conn)
    payload = {"companies": [
        {"name": r.slug, "provider": r.provider, "slug": r.slug, "tags": []} for r in rows
    ]}
    console.print(yaml.safe_dump(payload, sort_keys=False))


@companies_app.command("discover-grnh")
def discover_grnh_(
    ctx: typer.Context,
    limit: int = typer.Option(
        200, "--limit", min=0,
        help="How many stored grnh.se seeds to follow; 0 follows every selectable one.",
    ),
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Write the candidate file here instead of stdout."),
    ] = None,
) -> None:
    """Propose greenhouse boards from stored `grnh.se` seeds, for review.

    `grnh.se` is Greenhouse's own shortener, so the redirect target names the board. MEASURED
    2026-09-02: 12 of 12 sampled seeds landed on a URL `parse_board_target` accepts, yielding 9
    distinct boards, 0 of them already watched.

    Writes a registry-format file and NOTHING ELSE — no store write, watched or otherwise, and
    the seed rows are left unresolved because a board CANDIDATE is not a resolved posting. Review
    it, delete any row whose evidence URL is ATS chrome rather than an employer board, then
    `companies import` it. That human step is the owner's ruling (D-291 build).

    **Because it writes nothing, a bounded `--limit` reads the SAME seeds every time** — the
    `(attempts, id)` order cannot move if no attempt is ever charged. So the document states its
    own coverage, and `--limit 0` follows every selectable seed. Re-running at the default does
    not advance; it re-reads the same prefix.

    **This is not wired into a run.** Arming these boards costs ~3.2s each on every future run,
    so admission stays a separate, deliberate act.
    """
    # ensure=False for the reason `discover` states: a command whose docstring promises no store
    # write must not migrate a production database as a side effect of being asked a question.
    app_ctx = build_context(ctx.obj, ensure=False)
    if not inspect(app_ctx.engine).has_table("lane_seeds"):
        console.print("[red]no lane_seeds table — run `boardwatch init` first[/red]")
        raise typer.Exit(code=1)
    with app_ctx.engine.connect() as conn:
        seeds = unresolved_seeds(
            conn,
            hosts=GRNH_HOSTS,
            max_attempts=MAX_ATTEMPTS_CONSIDERED,
            # `--limit 0` is the whole queue, not SQLite's `LIMIT 0`. Nothing here advances the
            # seed order, so a caller that needs the seeds behind the prefix has no resume
            # token to carry -- it has to ask for all of them, deliberately, at one request each.
            limit=None if limit == 0 else limit,
        )
        # Counted AFTER the select and on the same predicate: the only drift two SQLite snapshots
        # can produce here is a concurrent INSERT, and a seed inserted mid-read really was not
        # examined. `SeedCoverage.not_examined` floors the other direction at 0.
        coverage = SeedCoverage(
            selectable=unresolved_seed_count(
                conn, hosts=GRNH_HOSTS, max_attempts=MAX_ATTEMPTS_CONSIDERED
            ),
            followed=len(seeds),
        )
    resolution = grnh_resolve(seeds, Fetcher(app_ctx.settings))
    # Boards already stored are dropped, the same rule `discover` applies via `is_known`. This
    # command charges no attempt and never sets `resolved_at`, so the seed set is IDENTICAL on
    # every invocation -- without this, a reviewer who imports the good rows is handed the whole
    # list again next time, including the ATS chrome they just deleted.
    with app_ctx.engine.connect() as conn:
        resolution = grnh_without_known(
            resolution, is_known=lambda p, s: company_exists(conn, provider=p, slug=s)
        )
    document = grnh_candidate_document(
        resolution, generated_on=date.today(), coverage=coverage
    )
    if out is None:
        # Plain stdout, not `console.print`: rich WORD-WRAPS at the console width, which breaks
        # a header comment across lines that no longer start with `#` and makes the document
        # fail `safe_load` -- the exact escape `_one_line` exists to prevent, one layer down.
        typer.echo(document, nl=False)
        return
    out.write_text(document, encoding="utf-8")
    # The coverage goes to the terminal as well as into the file: an operator who never opens the
    # document must still be able to tell a partial read from a complete one.
    console.print(
        f"Wrote {len(resolution.boards)} candidate board(s) to {out} — {coverage.summary()}",
        markup=False, highlight=False, soft_wrap=True,
    )


@companies_app.command("discover")
def discover_(
    ctx: typer.Context,
    limit: int | None = typer.Option(
        None, "--limit", min=0,
        help="How many new boards to propose (default: lane_new_companies_per_run).",
    ),
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Write the candidate file here instead of stdout."),
    ] = None,
) -> None:
    """Propose company boards from the public GitHub lists in `lane_github_lists`, for review.

    Writes a registry-format file and NOTHING ELSE — no store write, watched or otherwise. Review
    it, delete any row whose evidence URL is not an employer board, then `companies import` it.
    That human step is the owner's ruling (D-291 build): a bad slug becomes a permanently failing
    board, and this repo has no quarantine and no backoff for one.
    """
    # ensure=False, the same reason `doctor` uses it: this command reads the store and must never
    # migrate it. `build_context`'s default runs `alembic upgrade head`, so without this a command
    # whose own docstring promises no store write would silently upgrade a 1.4 GB production
    # database as a side effect of being asked what boards exist (D-279).
    app_ctx = build_context(ctx.obj, ensure=False)
    repos = app_ctx.settings.lane_github_lists
    if not repos:
        # Inert, not a failure of the lists: which lists fit is tenant data (DESIGN-T183 E2).
        console.print(
            "github_lists: not attemptable (no_lists) — set lane_github_lists in config.toml; "
            "nothing was fetched",
            markup=False, highlight=False, soft_wrap=True,
        )
        raise typer.Exit(code=1)
    cap = app_ctx.settings.lane_new_companies_per_run if limit is None else limit
    result = discover(fetch_listings(Fetcher(app_ctx.settings), repos))
    if not inspect(app_ctx.engine).has_table("companies"):
        # Nothing stored, so every candidate is new. `ensure=False` deliberately does not create
        # the schema here; `companies import` does, which is the write half of this workflow and
        # the right place for it.
        selection = select(result, is_known=_nothing_stored, budget=CompanyBudget(cap))
    else:
        with app_ctx.engine.connect() as conn:
            # One point query per candidate rather than one `IN (...)` over the whole set.
            # Deliberate: `(provider, slug)` is UNIQUE and indexed so this is a few hundred index
            # seeks, and a corpus-sized `IN` list is the exact shape that crossed SQLite's 32,766
            # bound-parameter cap and killed run 70 (D-287). It also reuses the sanctioned
            # lookup — `company_exists`, not the watched-only view, because an unwatched row
            # would read as new forever.
            selection = select(
                result,
                is_known=lambda provider, slug: company_exists(
                    conn, provider=provider, slug=slug
                ),
                budget=CompanyBudget(cap),
            )
    document = candidate_document(
        selection, census=result.census, generated_on=utcnow().date(), repos=repos
    )
    if out is None:
        # Plain stdout, not `console.print`: the document is YAML a human pipes into a file, and
        # rich would read its brackets as markup.
        typer.echo(document, nl=False)
        return
    out.write_text(document, encoding="utf-8")
    console.print(
        f"Wrote {len(selection.admitted)} candidate board(s) to {out} "
        f"({len(selection.already_known)} already stored, {len(selection.refused)} held back by "
        f"the cap of {cap}). Review it, then: boardwatch companies import {out}"
    )


@companies_app.command("unscanned")
def unscanned(
    ctx: typer.Context,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Write the candidate file here instead of stdout."),
    ] = None,
) -> None:
    """Census the boards this store already holds but never scans, for review before import.

    `upsert_lane_company` writes `watched=False` for a new row, and that default is correct for
    an AGGREGATOR-keyed row: `scan/coordinator.py` looks every watched company's provider up in
    the registry, so a watched `hiringcafe` row would append `unknown provider` to every future
    run's errors. But a lane also discovers companies sitting on a REAL supported board, and
    those are stored unwatched too — so `get_watched_companies` (`watched IS TRUE`) never sees
    them and the scan fleet never reads them. Until this command the only way to see that
    population was hand-written SQL, which is why it went unnoticed and then refilled.

    Writes a registry-format file and NOTHING ELSE — no store write, watched or otherwise, and
    no network. Review it, delete any row you do not want, then `companies import`. That human
    step is the owner's ruling (D-291 build): nothing here promotes a board, and `companies
    import` stays the only admission route.

    A provider with no scanner adapter is EXCLUDED, not bucketed. Watching one would add an
    `unknown provider` line to every run forever, so it is not a candidate in any sense — the
    adapter set comes from the provider registry, never from a list written here.

    Two classes are SHOWN but never proposed: a `source='user'` row, which may have been retired
    on purpose, and a stored slug `companies import` refuses, which would abort the import of
    every row beside it.
    """
    # ensure=False for the reason `discover` states: a command whose docstring promises no store
    # write must not migrate a production database as a side effect of being asked a question.
    app_ctx = build_context(ctx.obj, ensure=False)
    if not inspect(app_ctx.engine).has_table("companies"):
        console.print("[red]no companies table — run `boardwatch init` first[/red]")
        raise typer.Exit(code=1)
    with app_ctx.engine.connect() as conn:
        rows = unwatched_scannable_companies(conn, providers=PROVIDER_NAMES)
    # `source='user'` is held back, never proposed. D-324/D-325 measured 274 postings in that
    # provenance class: an unwatched user row may have been deliberately RETIRED by `companies
    # remove`, and this command cannot tell that apart from one that was never watched. "Safe to
    # rewatch" is not inferable from `watched=0`, so the row is shown and the decision is left
    # to the reader, who can `companies add` it by hand.
    held_back = [row for row in rows if row.source == "user"]
    proposed, unimportable = _admissible([row for row in rows if row.source != "user"])
    document = _unscanned_document(proposed, held_back, unimportable, utcnow().date())
    if out is None:
        # Plain stdout, not `console.print`: the document is YAML a human pipes into a file, and
        # rich would read its brackets as markup and word-wrap the header's comment lines.
        typer.echo(document, nl=False)
        return
    out.write_text(document, encoding="utf-8")
    console.print(
        f"Wrote {len(proposed)} candidate board(s) to {out} ({len(held_back)} source=user row(s) "
        f"held back for review, {len(unimportable)} unimportable). Review it, then: "
        f"boardwatch companies import {out}"
    )


def _admissible(rows: list[Row[Any]]) -> tuple[list[Row[Any]], list[tuple[Row[Any], str]]]:
    """Split the proposals into the ones `companies import` can actually read and the rest.

    THE CANDIDATE SLUG IS NOT THIS COMMAND'S OWN OUTPUT — it is whatever a lane wrote into the
    store, and `companies import` runs every entry through `parse_board_target` before it writes
    anything. One slug that parser refuses raises `UnknownBoardURL` out of `validate_entries`
    and the import aborts for the WHOLE file, so a single malformed row would make the other
    proposals unimportable and the operator would have to find and delete it by hand.

    Checked against the importer's own parser rather than a shape test of our own, so the two
    cannot disagree. A refused row is still SHOWN with its reason — this is the same
    propose-nothing treatment a `source='user'` row gets, not a new admission bucket: nothing
    here decides the slug is wrong, only that this route cannot carry it.
    """
    keep: list[Row[Any]] = []
    refused: list[tuple[Row[Any], str]] = []
    for row in rows:
        try:
            parse_board_target(f"{row.provider}:{row.slug}")
        except UnknownBoardURL as exc:
            refused.append((row, str(exc)))
            continue
        keep.append(row)
    return keep, refused


def _unscanned_document(
    proposed: list[Row[Any]],
    held_back: list[Row[Any]],
    unimportable: list[tuple[Row[Any], str]],
    generated_on: date,
) -> str:
    """The registry-format file `companies import` accepts, behind a reviewable header.

    The header is comments, which `yaml.safe_load` ignores, and that is the only place the
    provenance can go: `CompanyEntry` sets `extra="forbid"`, so a per-entry `postings` field
    would fail the very validator the file has to pass.
    """
    payload = {
        "companies": [
            {"name": row.name, "provider": row.provider, "slug": row.slug, "tags": []}
            for row in proposed
        ]
    }
    # `safe_dump` quotes any scalar whose plain form would resolve to something else, so a board
    # named `no`, `123` or `~` survives the round trip through `safe_load`.
    body: str = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return _unscanned_header(proposed, held_back, unimportable, generated_on) + body


def _evidence(row: Row[Any]) -> str:
    """One row as the reviewer reads it. `one_line` on every stored string: a lane wrote these
    names and slugs from a third-party document, so a newline in one would end the `#` comment
    and let the remainder parse as top-level YAML (see `github_lists.one_line`).

    `first_seen_at` is the OLDEST posting this store holds for the board, or `never` when it
    holds none — which is the one value that says the board was recorded but never actually
    observed, and the reviewer's cue to check the slug before importing it.
    """
    first_seen = "never" if row.first_seen_at is None else str(row.first_seen_at)
    return (
        f"{row.provider}:{one_line(row.slug)} | {one_line(row.name)} "
        f"| {row.postings} posting(s) | first seen {one_line(first_seen)} "
        f"| source={one_line(row.source)}"
    )


def _unscanned_header(
    proposed: list[Row[Any]],
    held_back: list[Row[Any]],
    unimportable: list[tuple[Row[Any], str]],
    generated_on: date,
) -> str:
    lines = [
        "# boardwatch companies unscanned - boards this store holds but never scans, for review",
        "#",
        f"# generated {generated_on.isoformat()} by reading the store. No fetch, no store write:",
        "# nothing in this file is watched until you run `companies import` on it.",
        "#",
        "# THE POPULATION: companies.watched = 0 on a provider that HAS a scanner adapter, so",
        "# `get_watched_companies` (watched IS TRUE) never hands the board to the scan fleet.",
        "# A provider with NO adapter and an aggregator placeholder are absent from this file",
        "# entirely - not as a bucket, not as a comment - because watching one appends",
        "# `unknown provider` to every future run's errors. The adapter set is read from the",
        "# provider registry at generation time, so this list is what it meant today:",
        f"#   {', '.join(sorted(PROVIDER_NAMES))}",
        "#",
        f"# unscanned boards {len(proposed) + len(held_back) + len(unimportable)} "
        f"| proposed {len(proposed)} | held back for review {len(held_back)} "
        f"| unimportable {len(unimportable)}",
        "#",
        "# ARMING A BOARD COSTS RUN TIME FOREVER: ~3.2s per board on EVERY future run once",
        "# watched. Delete any row you do not want before `companies import`.",
        "#",
    ]
    if proposed:
        lines.append("# Check each row's evidence before importing it:")
        lines += [f"#   {_evidence(row)}" for row in proposed]
        lines.append("#")
    else:
        lines += ["# No unscanned board to propose. Nothing to import.", "#"]
    if held_back:
        lines += [
            "# HELD BACK FOR REVIEW - source=user, and therefore proposed by nothing above.",
            "# A user row that is unwatched may have been RETIRED on purpose (`companies",
            "# remove`), and `watched = 0` cannot tell that apart from one never watched. If you",
            "# want one of these back, `companies add` it by hand - deliberately, one at a time:",
        ]
        lines += [f"#   {_evidence(row)}" for row in held_back]
        lines.append("#")
    if unimportable:
        lines += [
            "# UNIMPORTABLE - `companies import` refuses the stored slug, so proposing it would",
            "# abort the import of every row above it. Shown with the parser's own reason; fix",
            "# the slug by hand if the board is real:",
        ]
        lines += [f"#   {_evidence(row)} | {one_line(reason)}" for row, reason in unimportable]
        lines.append("#")
    return "\n".join(lines) + "\n"


@companies_app.command("import")
def import_(
    ctx: typer.Context,
    path: typer.FileText,
    verify: bool = typer.Option(False, "--verify", help=_VERIFY_HELP),
) -> None:
    """Validate registry-format YAML, then watch each entry."""
    try:
        raw = yaml.safe_load(path.read()) or {}
        # Normalize through the same path `add` uses before the duplicate check, so
        # case-variant slugs on a case-insensitive provider (smartrecruiters) collapse
        # instead of writing two rows for one board — one of which `remove` could never
        # match, because it normalizes the slug the caller types.
        entries = validate_entries(
            [_normalized(CompanyEntry.model_validate(row)) for row in (raw.get("companies") or [])]
        )
    except (CatalogError, UnknownBoardURL, ValueError, yaml.YAMLError) as exc:
        # `yaml.YAMLError` subclasses Exception, NOT ValueError, so it escaped this clause and the
        # operator got a traceback. `companies discover` exists to hand a human a YAML file to edit
        # before importing it, which makes a hand-introduced syntax error an ordinary event.
        console.print(f"[red]invalid import file: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    app_ctx = build_context(ctx.obj)
    skipped: list[tuple[str, str, BoardHealth]] = []
    empty: list[str] = []
    if verify:
        health = _probe([(e.provider, e.slug) for e in entries], app_ctx.settings)
        kept: list[CompanyEntry] = []
        for e in entries:
            status = health[(e.provider, e.slug)]
            if status in _UNPROVEN:
                skipped.append((e.provider, e.slug, status))
                continue
            if status is BoardHealth.EMPTY:
                empty.append(f"{e.provider}:{e.slug}")
            kept.append(e)
        entries = kept
    recased: list[str] = []
    with app_ctx.engine.begin() as conn:
        for e in entries:
            in_catalog = (e.provider, e.slug) in _catalog_index()
            watched = upsert_watch(conn, provider=e.provider, slug=e.slug, name=e.name,
                                   source="registry" if in_catalog else "user")
            if watched != e.slug:
                recased.append(f"{e.provider}:{e.slug} -> {e.provider}:{watched}")
    console.print(f"Imported {len(entries)} watches.")
    if recased:
        # Reported, not silent: the count above would otherwise imply N new boards.
        console.print(
            "[yellow]note:[/yellow] already stored under a different slug case, watched in "
            f"place rather than added a second time: {', '.join(recased)}"
        )
    if empty:
        console.print(
            f"[yellow]note:[/yellow] reachable but currently empty (watched anyway): "
            f"{', '.join(empty)}"
        )
        if any(name.startswith("smartrecruiters:") for name in empty):
            # SmartRecruiters returns an empty board for an unknown company rather than a
            # 404, so 'empty' there is NOT evidence the board exists (see doctor's caveat).
            console.print(
                "[yellow]note:[/yellow] for smartrecruiters, 'empty' is unverifiable — it may "
                "be a typo'd slug rather than a real board with no open roles."
            )
    if skipped:
        for provider, slug, status in skipped:
            console.print(f"[red]skipped {provider}:{slug} — probe returned {status}.[/red]")
        # a partial import must not report success: the operator has to see the shortfall
        raise typer.Exit(code=1)
