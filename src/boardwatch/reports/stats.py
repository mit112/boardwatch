"""`boardwatch stats` — a one-screen read-only readout over the local DB.

summarize() is pure and holds the honesty-critical rule: the window partition is disjoint
and keeps `unevaluated` (no current verdict) separate from `qualified`, so an empty
eligibility ledger reads as "N unevaluated", never as "0 qualified". compute_stats() (below)
is the thin I/O wrapper that reuses top's preflight/eligibility/filter seams.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from rich.console import Console
from sqlalchemy import Engine, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.eligibility.preflight import run_eligibility
from boardwatch.eligibility.read import current_verdicts
from boardwatch.extract.preflight import run_preflight
from boardwatch.rank.heuristic import passes_hard_filters, profile_view_from_row
from boardwatch.rank.leveling import load_bindings, load_leveling
from boardwatch.rank.role_gate import role_verdict
from boardwatch.rank.seniority_gate import TargetBand, seniority_verdict
from boardwatch.store.queries import current_posting_versions, get_profile
from boardwatch.store.stats_queries import count_open_postings, count_tracked_submitted
from boardwatch.store.tables import companies, postings


@dataclass(frozen=True)
class PostingStat:
    posting_id: int
    posted_at: datetime | None
    passes_filters: bool
    verdict: str | None  # "eligible" | "uncertain" | "ineligible" | None (unevaluated)
    non_swe: bool = False  # title role gate says non-software; `top` hides these by default
    # title seniority gate says above the target band; `top` hides these by default (D-246)
    over_seniority: bool = False


@dataclass(frozen=True)
class StatsReport:
    window_days: int
    qualified: int
    uncertain: int
    ineligible: int
    unevaluated: int
    seen: int
    passes_filters: int
    non_swe: int
    not_ineligible: int
    tracked: int
    # Reported the same way `non_swe` is, and for the same reason: `top` hides these, so a
    # readout that never counted them would disagree with the shortlist it describes (D-246).
    over_seniority: int = 0


def summarize(
    stats: list[PostingStat], *, now: datetime, window_days: int, seen: int, tracked: int
) -> StatsReport:
    cutoff = now - timedelta(days=window_days)
    in_window = [
        s for s in stats
        if s.passes_filters and s.posted_at is not None and s.posted_at >= cutoff
    ]
    qualified = sum(1 for s in in_window if s.verdict == "eligible")
    uncertain = sum(1 for s in in_window if s.verdict == "uncertain")
    ineligible = sum(1 for s in in_window if s.verdict == "ineligible")
    unevaluated = sum(1 for s in in_window if s.verdict is None)
    passes = sum(1 for s in stats if s.passes_filters)
    # Reported alongside the chain, NOT subtracted from it. The role gate hides these from
    # `top`, so an unreported count would make this readout disagree with what `top` shows;
    # folding it into `passes_filters`/`not_ineligible`/the window buckets instead would
    # redefine numbers the parity window is already measuring. Counted, not silent.
    non_swe = sum(1 for s in stats if s.passes_filters and s.non_swe)
    over_seniority = sum(1 for s in stats if s.passes_filters and s.over_seniority)
    not_ineligible = sum(1 for s in stats if s.passes_filters and s.verdict != "ineligible")
    return StatsReport(
        window_days=window_days,
        qualified=qualified, uncertain=uncertain, ineligible=ineligible, unevaluated=unevaluated,
        seen=seen, passes_filters=passes, non_swe=non_swe,
        not_ineligible=not_ineligible, tracked=tracked, over_seniority=over_seniority,
    )


def compute_stats(
    engine: Engine, settings: Settings, *,
    window_days: int, now: datetime | None = None, output_console: Console,
) -> StatsReport | None:
    """Two readouts over the local DB, or None when no profile exists.

    Reuses top's seams verbatim: preflight backfills extractions, run_eligibility computes the
    current identity hashes (a no-op on a null profile), current_verdicts reads the current
    profile's verdict per posting. No writes beyond what preflight/eligibility already do.
    """
    run_preflight(engine, settings, output_console)
    elig = run_eligibility(engine, settings, output_console)
    now = now or utcnow()
    with engine.connect() as conn:
        profile_row = get_profile(conn)
        if profile_row is None:
            return None
        profile = profile_view_from_row(profile_row)
        rows = conn.execute(
            select(
                postings.c.id, postings.c.title, postings.c.posted_at,
                postings.c.locations_json, postings.c.remote_policy,
                companies.c.provider, companies.c.slug,
            )
            .join(companies, postings.c.company_id == companies.c.id)
            .where(postings.c.status == "open")
        ).all()
        versions = current_posting_versions(conn, None)
        verdicts = current_verdicts(
            conn, [cv.posting_version_id for cv in versions.values()],
            elig.profile_hash, elig.rules_hash,
        )
        seen = count_open_postings(conn)
        tracked = count_tracked_submitted(conn)
    # Loaded ONCE, outside the comprehension: `load_leveling` parses YAML on every call.
    leveling = load_leveling(settings.config_dir)
    schemes = {
        key: leveling.schemes[name]
        for key, name in load_bindings(settings.config_dir).items()
        if name in leveling.schemes
    }
    tier = leveling.fields["software"]
    target_band = cast(TargetBand, profile.target_seniority_band)
    stats = [
        PostingStat(
            posting_id=int(row.id),
            posted_at=row.posted_at,
            passes_filters=passes_hard_filters(
                row.title, list(row.locations_json or []), row.remote_policy,
                profile, settings.location_filter_mode,
            ),
            verdict=verdicts.get(int(row.id)),
            non_swe=role_verdict(row.title)[0] == "not_swe",
            over_seniority=seniority_verdict(
                row.title, schemes.get((row.provider, row.slug)), target_band, tier, leveling,
            )[0] == "above_band",
        )
        for row in rows
    ]
    return summarize(stats, now=now, window_days=window_days, seen=seen, tracked=tracked)
