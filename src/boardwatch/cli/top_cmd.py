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
from sqlalchemy import Engine, select

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.eligibility.engine import current_evaluations
from boardwatch.eligibility.preflight import current_identity, run_eligibility
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


def profile_view_from_row(row: object) -> ProfileView:
    return ProfileView(
        skills=frozenset(getattr(row, "skills_json", None) or []),
        target_titles=tuple(getattr(row, "target_titles_json", None) or []),
        exclude_titles=tuple(getattr(row, "exclude_titles_json", None) or []),
        locations=tuple(getattr(row, "locations_json", None) or []),
        remote_only=bool(getattr(row, "remote_only", False)),
    )


def rank_open_postings(
    engine: Engine, settings: Settings, *, now: datetime | None = None, limit: int = 10
) -> list[RankedPosting]:
    run_preflight(engine, settings, console)
    run_eligibility(engine, settings, console)  # no-op on a null profile; before the check below
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
        ))
    scored.sort(key=lambda r: r.score.total, reverse=True)
    return scored[:limit]


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


def _posting_verdicts(
    engine: Engine, settings: Settings, posting_ids: list[int]
) -> dict[int, str | None]:
    """posting_id -> the CURRENT profile's verdict for it, or None if unevaluated.

    Verdicts are read for the live profile's identity, so a corrected fact or policy is
    reflected the moment its re-evaluation lands, never a leftover verdict from an old one.
    """
    if not posting_ids:
        return {}
    with engine.connect() as conn:
        identity = current_identity(conn, settings)
        if identity is None:
            return {posting_id: None for posting_id in posting_ids}
        versions = current_posting_versions(conn, posting_ids)
        evals = current_evaluations(
            conn, [cv.posting_version_id for cv in versions.values()], *identity
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
        ranked = rank_open_postings(app_ctx.engine, app_ctx.settings, limit=n)
    except NoProfileError:
        console.print("no profile yet — run `boardwatch init` first")
        raise typer.Exit(code=1) from None
    if not ranked:
        console.print("no open postings match your filters")
        return
    verdicts = _posting_verdicts(
        app_ctx.engine, app_ctx.settings, [p.posting_id for p in ranked]
    )
    hidden = 0
    visible: list[tuple[RankedPosting, str | None]] = []
    for p in ranked:
        verdict = verdicts.get(p.posting_id)
        # Only a PERSISTED ineligible is hidden; an unevaluated posting is never hidden
        # (D-P2-10), because absence of evidence must not narrow the funnel.
        if verdict == "ineligible" and not include_ineligible:
            hidden += 1
            continue
        visible.append((p, verdict))
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Score")
    table.add_column("Eligibility", no_wrap=True)
    table.add_column("Why")
    for p, verdict in visible:
        table.add_row(
            str(p.posting_id), p.title, p.company,
            f"{p.score.total:.2f}", _verdict_token(verdict), p.why,
        )
    console.print(table)
    if hidden and not include_ineligible:
        console.print(
            f'{hidden} hidden as ineligible. "no flags" means no catalogued disqualifier '
            "was detected, not that you qualify.",
            markup=False,
        )
