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
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.rank.heuristic import passes_hard_filters, profile_view_from_row
from boardwatch.rank.leveling import load_leveling, resolve_schemes
from boardwatch.rank.role_gate import role_verdict, zero_signal_verdict
from boardwatch.rank.seniority_gate import TargetBand, seniority_verdict
from boardwatch.store.queries import body_is_empty, current_posting_versions, get_profile
from boardwatch.store.stats_queries import count_open_postings, count_tracked_submitted
from boardwatch.store.tables import companies, extractions, postings


@dataclass(frozen=True)
class PostingStat:
    posting_id: int
    posted_at: datetime | None
    passes_filters: bool
    verdict: str | None  # "eligible" | "uncertain" | "ineligible" | None (unevaluated)
    non_swe: bool = False  # title role gate says non-software; `top` hides these by default
    # No role signal in the title AND no recognised term in a body that WAS read; `top` hides
    # these by default. Set ONLY for postings the role gate passed, same reason as below.
    zero_signal: bool = False
    # Title seniority gate says above the target band; `top` hides these by default (D-246).
    # Set ONLY for postings the role gate AND the zero-signal rule passed, mirroring `top`'s
    # gate ORDER: see the loop in `compute_stats`. The buckets are disjoint there, so they have
    # to be disjoint here.
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
    # Same again for the zero-signal veto. Reported rather than merely subtracted out of
    # `over_seniority`: a posting the ordering moves out of one bucket has to land in a named
    # one, or ordering the gates correctly would make it vanish from the readout entirely.
    zero_signal: int = 0


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
    zero_signal = sum(1 for s in stats if s.passes_filters and s.zero_signal)
    over_seniority = sum(1 for s in stats if s.passes_filters and s.over_seniority)
    not_ineligible = sum(1 for s in stats if s.passes_filters and s.verdict != "ineligible")
    return StatsReport(
        window_days=window_days,
        qualified=qualified, uncertain=uncertain, ineligible=ineligible, unevaluated=unevaluated,
        seen=seen, passes_filters=passes, non_swe=non_swe,
        not_ineligible=not_ineligible, tracked=tracked, over_seniority=over_seniority,
        zero_signal=zero_signal,
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
    # Read ONCE, outside the connection: the extraction join below keys on it, exactly as
    # `top`'s does, so the two surfaces read the same row for the same posting.
    version = load_taxonomy(settings.config_dir).version
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
                # The zero-signal rule's two body inputs. Joined here, on the same key `top`
                # uses, because this readout re-derives `top`'s gate chain and cannot order a
                # gate it has no input for.
                extractions.c.json.label("extraction_json"),
                body_is_empty().label("body_empty"),
            )
            .join(companies, postings.c.company_id == companies.c.id)
            .outerjoin(
                extractions,
                (extractions.c.posting_id == postings.c.id)
                & (extractions.c.content_hash == postings.c.content_hash)
                & (extractions.c.kind == "taxonomy")
                & (extractions.c.engine_version == version),
            )
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
    schemes, _binding_warning = resolve_schemes(leveling, settings.config_dir)
    tier = leveling.fields["software"]
    target_band = cast(TargetBand, profile.target_seniority_band)
    stats: list[PostingStat] = []
    for row in rows:
        # ORDERED exactly as `top_cmd` gates, because these two counts describe one gate chain.
        # There the role gate `continue`s before the seniority gate ever runs, so a posting that
        # is both non-software and over-band is `hidden_non_swe` and nothing else. Evaluated
        # independently, such a posting landed in both buckets and `over_seniority` read higher
        # than the funnel's `hidden_over_seniority` for the same corpus -- two numbers for one
        # gate that could not be reconciled.
        role = role_verdict(row.title)[0]
        non_swe = role == "not_swe"
        # Between the two, exactly where the ranker `continue`s on it: an `uncertain` +
        # zero-skill + above-band posting is `hidden_zero_signal` in the funnel and must not
        # ALSO be `over_seniority` here, which is the same irreconcilable double-count the
        # comment above records for `non_swe`.
        zero_signal = not non_swe and zero_signal_verdict(
            role, row.extraction_json, body_empty=bool(row.body_empty),
        )[0] == "veto"
        over_seniority = not non_swe and not zero_signal and seniority_verdict(
            row.title, schemes.get((row.provider, row.slug)), target_band, tier, leveling,
        )[0] == "above_band"
        stats.append(PostingStat(
            posting_id=int(row.id),
            posted_at=row.posted_at,
            passes_filters=passes_hard_filters(
                row.title, list(row.locations_json or []), row.remote_policy,
                profile, settings.location_filter_mode,
            ),
            verdict=verdicts.get(int(row.id)),
            non_swe=non_swe,
            zero_signal=zero_signal,
            over_seniority=over_seniority,
        ))
    return summarize(stats, now=now, window_days=window_days, seen=seen, tracked=tracked)
