"""boardwatch top (§2.3): ranked shortlist computed on demand (D17).

The # column is the posting's DB id — `show <id>` takes exactly what top
displays (plan deviation 11). There is NO --new flag in P0; the event cursor
is P2's. rank_open_postings() is the in-process top path the perf smoke
benchmarks (§6.3-7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import Connection, Engine, select

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.eligibility.engine import current_evaluations
from boardwatch.eligibility.preflight import run_eligibility
from boardwatch.extract.preflight import run_preflight
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.rank.explain import why_summary
from boardwatch.rank.heuristic import ProfileView, Score, passes_hard_filters, score_posting
from boardwatch.store.queries import current_posting_versions, get_profile
from boardwatch.store.tables import companies, extractions, postings

console = Console()


class NoProfileError(Exception):
    pass


@dataclass(frozen=True)
class RankedPosting:
    posting_id: int
    title: str
    company: str
    score: Score
    why: str
    verdict: str | None = None  # the current profile's eligibility verdict, None if unevaluated


@dataclass(frozen=True)
class RankedResults:
    """The shortlist plus the count hidden as ineligible, so `top` can report both."""

    visible: list[RankedPosting]
    hidden_ineligible: int


def profile_view_from_row(row: object) -> ProfileView:
    return ProfileView(
        skills=frozenset(getattr(row, "skills_json", None) or []),
        target_titles=tuple(getattr(row, "target_titles_json", None) or []),
        exclude_titles=tuple(getattr(row, "exclude_titles_json", None) or []),
        locations=tuple(getattr(row, "locations_json", None) or []),
        remote_only=bool(getattr(row, "remote_only", False)),
    )


def rank_open_postings(
    engine: Engine,
    settings: Settings,
    *,
    now: datetime | None = None,
    limit: int = 10,
    include_ineligible: bool = False,
) -> RankedResults:
    run_preflight(engine, settings, console)
    stats = run_eligibility(engine, settings, console)  # no-op on a null profile; before the check
    version = load_taxonomy(settings.config_dir).version
    now = now or utcnow()
    with engine.connect() as conn:
        profile_row = get_profile(conn)
        if profile_row is None:
            raise NoProfileError
        profile = profile_view_from_row(profile_row)
        rows = conn.execute(
            select(
                postings.c.id,
                postings.c.title,
                postings.c.posted_at,
                postings.c.locations_json,
                postings.c.remote_policy,
                companies.c.name.label("company_name"),
                extractions.c.json.label("extraction_json"),
            )
            .join(companies, postings.c.company_id == companies.c.id)
            .outerjoin(
                extractions,
                (extractions.c.posting_id == postings.c.id)
                & (extractions.c.content_hash == postings.c.content_hash)
                & (extractions.c.kind == "taxonomy")
                & (extractions.c.engine_version == version),
            )
            .where(
                postings.c.status == "open",
            )
        ).all()
        # The run computed the identity; reuse it rather than reload the catalog.
        verdicts = _current_verdicts(conn, stats.profile_hash, stats.rules_hash)
    scored: list[RankedPosting] = []
    for row in rows:
        skills = set((row.extraction_json or {}).get("skills", []))
        score = score_posting(
            profile, skills, row.title, row.posted_at,
            list(row.locations_json or []), row.remote_policy,
            settings.weights, now, settings.recency_half_life_days,
        )
        if not passes_hard_filters(
            row.title,
            list(row.locations_json or []),
            row.remote_policy,
            profile,
            settings.location_filter_mode,
        ):
            continue
        scored.append(RankedPosting(
            posting_id=int(row.id), title=row.title, company=row.company_name,
            score=score, why=why_summary(score, row.posted_at, now),
            verdict=verdicts.get(int(row.id)),
        ))
    scored.sort(key=lambda r: r.score.total, reverse=True)
    # Hide persisted-ineligible postings BEFORE the limit, so `top N` returns up to N shown
    # rows instead of losing an eligible posting that ranks just below an ineligible one. An
    # unevaluated posting (verdict None) is never hidden (D-P2-10). The hidden count spans the
    # whole shortlist, not just the top N, so the user sees how many the filter removed.
    visible: list[RankedPosting] = []
    hidden = 0
    for posting in scored:
        if not include_ineligible and posting.verdict == "ineligible":
            hidden += 1
            continue
        if len(visible) < limit:
            visible.append(posting)
    return RankedResults(visible=visible, hidden_ineligible=hidden)


def count_filter_matches(engine: Engine, settings: Settings) -> int | None:
    """Count open postings that pass hard filters, or None if no profile."""
    version = load_taxonomy(settings.config_dir).version
    with engine.connect() as conn:
        profile_row = get_profile(conn)
        if profile_row is None:
            return None
        profile = profile_view_from_row(profile_row)
        rows = conn.execute(
            select(
                postings.c.title,
                postings.c.posted_at,
                postings.c.locations_json,
                postings.c.remote_policy,
                extractions.c.json.label("extraction_json"),
            )
            .outerjoin(
                extractions,
                (extractions.c.posting_id == postings.c.id)
                & (extractions.c.content_hash == postings.c.content_hash)
                & (extractions.c.kind == "taxonomy")
                & (extractions.c.engine_version == version),
            )
            .where(postings.c.status == "open")
        ).all()
    count = 0
    for row in rows:
        if passes_hard_filters(
            row.title,
            list(row.locations_json or []),
            row.remote_policy,
            profile,
            settings.location_filter_mode,
        ):
            count += 1
    return count


def _verdict_token(verdict: str | None) -> str:
    """A one-token eligibility flag, chosen so no value reads as a clean bill of health
    (D-P2-18): `eligible` means only that no catalogued disqualifier was detected."""
    return {
        "ineligible": "blocked",
        "uncertain": "check",
        "eligible": "no flags",
    }.get(verdict or "", "-")


def _current_verdicts(
    conn: Connection, profile_hash: str | None, rules_hash: str | None
) -> dict[int, str | None]:
    """posting_id -> the CURRENT profile's verdict for it, or None if unevaluated.

    Set-oriented over every open posting (no per-posting query) and keyed on the identity the
    run already computed, so a corrected fact or policy is reflected the moment its
    re-evaluation lands, never a leftover verdict from an old profile.
    """
    if profile_hash is None or rules_hash is None:
        return {}
    versions = current_posting_versions(conn, None)
    evals = current_evaluations(
        conn, [cv.posting_version_id for cv in versions.values()], profile_hash, rules_hash
    )
    return {
        posting_id: (evals.get(cv.posting_version_id) or (None, None))[1]
        for posting_id, cv in versions.items()
    }


def top(
    ctx: typer.Context,
    n: int = typer.Argument(10, help="Number of postings to show."),
    include_ineligible: bool = typer.Option(
        False, "--include-ineligible", help="Show postings persisted as ineligible."
    ),
) -> None:
    """Rank open postings against your profile (on-demand, §3.6)."""
    app_ctx = build_context(ctx.obj)
    try:
        results = rank_open_postings(
            app_ctx.engine, app_ctx.settings, limit=n, include_ineligible=include_ineligible
        )
    except NoProfileError:
        console.print("no profile yet — run `boardwatch init` first")
        raise typer.Exit(code=1) from None
    if not results.visible and not results.hidden_ineligible:
        console.print("no open postings match your filters")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Score")
    table.add_column("Eligibility", no_wrap=True)
    table.add_column("Why")
    for p in results.visible:
        table.add_row(
            str(p.posting_id), p.title, p.company,
            f"{p.score.total:.2f}", _verdict_token(p.verdict), p.why,
        )
    console.print(table)
    if results.hidden_ineligible and not include_ineligible:
        console.print(
            f'{results.hidden_ineligible} hidden as ineligible. "no flags" means no catalogued '
            "disqualifier was detected, not that you qualify.",
            markup=False,
        )
