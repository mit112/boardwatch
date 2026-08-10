"""boardwatch top (§2.3): ranked shortlist computed on demand (D17).

The # column is the posting's DB id — `show <id>` takes exactly what top
displays (plan deviation 11). --new narrows the shortlist to postings with a
`new` event past the digest cursor (D18). rank_open_postings() is the
in-process top path the perf smoke benchmarks (§6.3-7).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import Connection, Engine, select

from boardwatch.cli.context import build_context
from boardwatch.core.clock import utcnow
from boardwatch.core.dedup import Suppression, resolve_duplicates
from boardwatch.core.ledger import LedgerRow
from boardwatch.core.settings import Settings
from boardwatch.eligibility.preflight import run_eligibility
from boardwatch.eligibility.read import current_gate_verdicts, current_verdicts
from boardwatch.extract.preflight import run_preflight
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.rank.explain import why_summary
from boardwatch.rank.heuristic import (
    Score,
    passes_hard_filters,
    profile_view_from_row,
    score_posting,
)
from boardwatch.rank.role_gate import RoleVerdict, role_verdict
from boardwatch.store.app_state import get_digest_cursor
from boardwatch.store.identity_queries import (
    identities_complete,
    load_identities,
    load_identity_inputs,
)
from boardwatch.store.ledger_queries import live_dispositions, record_disposition
from boardwatch.store.queries import current_posting_versions, get_profile
from boardwatch.store.regroup import job_anchors
from boardwatch.store.tables import companies, extractions, posting_events, postings

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
    role: RoleVerdict = "uncertain"  # title role gate; "not_swe" is hidden unless asked for
    role_reason: str = ""
    # The survivor this posting was suppressed in favour of. Set only when the row is
    # surfaced by the `--include-duplicates` drain; a normally-visible posting has None.
    duplicate_of: int | None = None
    # The live ledger disposition that suppressed this row, set only when it is surfaced by the
    # `--include-handled` drain (P6 slice 2). A normally-visible posting has None.
    handled_as: str | None = None


@dataclass(frozen=True)
class RankedResults:
    """The shortlist plus every count needed to account for the postings considered.

    `considered` and the six drop counts exist so the funnel's shortlist stage can reconcile:
    `considered == len(visible) + skipped_not_new + hidden_hard_filter + hidden_non_swe +
    hidden_ineligible + hidden_duplicate + hidden_handled + hidden_below_cutoff`. Each is its own
    counter,
    incremented where the posting actually leaves, never a remainder computed by subtraction —
    a remainder cannot catch a `continue` that forgot to count, which is the only way this
    identity realistically breaks (P0 item 3).

    That `considered` is `len(rows)` rather than that sum is a **code-review invariant, not a
    tested one**: the loop's exits are exhaustive, so rewriting it as the sum is behaviourally
    identical on every valid input and no test can tell them apart. It still matters — with
    `len(rows)` a single deleted counter is caught; with the sum it is self-consistent and
    invisible.
    """

    visible: list[RankedPosting]
    hidden_ineligible: int
    hidden_non_swe: int = 0
    # Postings the ranker looked at: open postings joined to their company. Measured
    # independently of the loop below, which is what lets the identity above fail.
    considered: int = 0
    # Vetoed before the role gate or any score. Two clauses, but only one has ever been
    # observed firing: measured 2026-08-06, all 11,517 were exclude-title vetoes and none was
    # a location veto, because `location_filter_mode` defaults to `soft`.
    hidden_hard_filter: int = 0
    # Cleared every filter but ranked outside `limit`. The bucket that did not exist before
    # item 3: on a real run at --top 5, 4,442 postings left here and appeared in no counter at
    # all. (The larger 11,517 went out through hidden_hard_filter, also uncounted before.)
    hidden_below_cutoff: int = 0
    # Narrowed away by `--new`. A scoping choice rather than a rejection, kept as its own
    # bucket so the identity holds for `top --new` too instead of only for the pipeline.
    skipped_not_new: int = 0
    # Suppressed as a provable duplicate of a surviving posting (P6 slice 1). Only
    # `exact_quad` can land a posting here, and only when identities are COMPLETE — a
    # partial backfill suppresses nothing. Drained by `--include-duplicates`.
    hidden_duplicate: int = 0
    # Whether the dedup gate was actually open. Defaults to False, the noisy direction: a
    # caller that forgets to set it gets "suppression disabled" rather than silently
    # claiming the subsystem ran. `hidden_duplicate == 0` on its own is ambiguous — it means
    # either "no duplicates found" or "dedup never ran" — and nothing in the shipped
    # automated path writes identities, so the second case is the common one.
    identities_are_complete: bool = False
    # Suppressed by a live ledger disposition — the job was already built, already refused, or
    # surfaced recently enough to still be inside its `seen` TTL (P6 slice 2). Drained by
    # `--include-handled`, and unlike `hidden_duplicate` this bucket is NOT gated on identity
    # completeness: a disposition is a record of a decision this program made, and it governs
    # whether or not dedup is currently running.
    hidden_handled: int = 0
    # The duplicate groups this run resolved, threaded out so the pipeline can project them onto
    # canonical jobs without recomputing dedup over the corpus a second time. Empty when
    # identities are incomplete, which is the same condition that leaves `hidden_duplicate` at 0.
    suppressions: tuple[Suppression, ...] = ()
    # The canonical jobs this call put in front of the user, in rank order. Populated whether or
    # not the `seen` write actually happened, so a caller that ranked with `record_surfaced=False`
    # can record the decision at the point it genuinely takes one (the pipeline, after tailoring).
    surfaced_job_ids: tuple[int, ...] = ()


def rank_open_postings(
    engine: Engine,
    settings: Settings,
    *,
    now: datetime | None = None,
    limit: int = 10,
    include_ineligible: bool = False,
    include_non_swe: bool = False,
    include_duplicates: bool = False,
    include_handled: bool = False,
    only_new: bool = False,
    output_console: Console = console,
    run_id: int | None = None,
    record_surfaced: bool = True,
) -> RankedResults:
    """Rank the open corpus. `record_surfaced=False` ranks WITHOUT consuming the queue.

    The `seen` write makes ranking a mutation (D-103, Mit's ruling), which is right for a caller
    that *delivers* a lead to somebody and wrong for one that merely needs the population.
    Delivering callers leave the default; `eligibility gate request` (which judges the shortlist
    and hands it back) and the pipeline (which records its own dispositions after the tailor loop,
    so a crash cannot suppress a lead it never built) pass False. `surfaced_job_ids` is populated
    either way, so a caller that opts out can still record the decision once it has one.
    """
    run_preflight(engine, settings, output_console)
    stats = run_eligibility(
        engine, settings, output_console, run_id=run_id
    )  # no-op on a null profile; before the check
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
        versions = current_posting_versions(conn, None)
        verdicts = current_verdicts(
            conn,
            [cv.posting_version_id for cv in versions.values()],
            stats.profile_hash,
            stats.rules_hash,
        )
        # The agent-lane final gate (§P5, task 1/2): a separate ledger keyed on the same
        # identity. Read-only here, fail-open by construction — a missing/uncertain/eligible
        # gate row never changes anything, only a persisted `ineligible` does (below).
        gate_verdicts = current_gate_verdicts(
            conn,
            [cv.posting_version_id for cv in versions.values()],
            stats.profile_hash,
            stats.rules_hash,
        )
        new_ids = _new_posting_ids(conn) if only_new else None
    scored: list[RankedPosting] = []
    hidden_non_swe = 0
    skipped_not_new = 0
    hidden_hard_filter = 0
    for row in rows:
        if new_ids is not None and int(row.id) not in new_ids:
            skipped_not_new += 1
            continue
        if not passes_hard_filters(
            row.title,
            list(row.locations_json or []),
            row.remote_policy,
            profile,
            settings.location_filter_mode,
        ):
            hidden_hard_filter += 1
            continue
        # The role gate is categorical, so it runs beside the score rather than inside it:
        # no title fuzz can rescue a "Deal Strategist". It is counted and reportable, never
        # a silent drop — a veto you cannot see is how a real job disappears unnoticed.
        role, role_reason = role_verdict(row.title)
        if role == "not_swe" and not include_non_swe:
            hidden_non_swe += 1
            continue
        skills = set((row.extraction_json or {}).get("skills", []))
        score = score_posting(
            profile, skills, row.title, row.posted_at,
            list(row.locations_json or []), row.remote_policy,
            settings.weights, now, settings.recency_half_life_days,
            settings.zero_skill_coverage_prior,
        )
        why = why_summary(score, row.posted_at, now)
        scored.append(RankedPosting(
            posting_id=int(row.id), title=row.title, company=row.company_name,
            score=score,
            why=f"{why} · role: {role_reason}" if role == "not_swe" else why,
            verdict=verdicts.get(int(row.id)),
            role=role, role_reason=role_reason,
        ))
    scored.sort(key=lambda r: r.score.total, reverse=True)
    # Hide persisted-ineligible postings BEFORE the limit, so `top N` returns up to N shown
    # rows instead of losing an eligible posting that ranks just below an ineligible one. An
    # unevaluated posting (verdict None) is never hidden (D-P2-10). The hidden count spans the
    # whole shortlist, not just the top N, so the user sees how many the filter removed.
    visible: list[RankedPosting] = []
    hidden = 0
    hidden_below_cutoff = 0
    hidden_duplicate = 0
    # Dedup runs last, over the post-eligibility population (design §1.4): the survivor is
    # elected among postings that would otherwise have been visible, so a group can never be
    # annihilated by electing a survivor an upstream filter had already hidden.
    eligible: list[RankedPosting] = []
    for posting in scored:
        if not include_ineligible and (
            posting.verdict == "ineligible"
            or gate_verdicts.get(posting.posting_id) == "ineligible"
        ):
            hidden += 1
            continue
        eligible.append(posting)

    # A second connection, deliberately. The function's existing `with engine.connect()`
    # block closes at `new_ids = ...`, well before scoring; every later line here runs with
    # no connection open, so reusing that `conn` raises ResourceClosedError. And the data
    # this needs cannot be prefetched inside the first block, because it is keyed on
    # `eligible`, which does not exist until scoring and the eligibility filter have run.
    #
    # The completeness gate: a partial backfill suppresses nothing. Not because partial
    # coverage is unsafe (an uncovered posting joins no group and is never suppressed) but
    # because survivor election over a subset is backfill-order-dependent, and Gate P6 has
    # to re-derive 20 sampled suppressions from the data.
    suppressions: dict[int, Suppression] = {}
    anchors: dict[int, int] = {}
    handled: dict[int, LedgerRow] = {}
    eligible_ids = [p.posting_id for p in eligible]
    with engine.connect() as dedup_conn:
        # Completeness is evaluated over ALL open postings, not just the eligible ones — it
        # is a property of the backfill, not of this query.
        ids_complete = identities_complete(dedup_conn)
        if ids_complete:
            identities = load_identities(dedup_conn, eligible_ids)
            # Bounded by eligible_ids on purpose: body_text is the largest column in the
            # schema, and the unfiltered call would pull every open posting's body into
            # memory to deduplicate a few thousand leads.
            inputs_by_id = {
                row.posting_id: row for row in load_identity_inputs(dedup_conn, eligible_ids)
            }
            suppressions = {
                s.posting_id: s
                for s in resolve_duplicates(
                    [inputs_by_id[i] for i in eligible_ids if i in inputs_by_id], identities
                )
            }
        # The ledger (P6 slice 2 §5.1). Read in the same connection but OUTSIDE the completeness
        # gate above: a stored disposition records a decision this program already made, so it
        # governs whether or not dedup happens to be running this minute.
        anchors = job_anchors(dedup_conn, eligible_ids)
        handled = live_dispositions(
            dedup_conn, now=now, job_ids=sorted(set(anchors.values()))
        )

    # Only non-duplicate rows are counted against `limit`. Drained duplicates are appended
    # unconditionally, so `--include-duplicates` can return more than `limit` rows.
    # Deliberate: a drain bounded by the rank cutoff reaches only the suppressed rows that
    # would also have ranked, which is not a re-entry path for the bucket — and the bucket is
    # what has to be auditable (a suppression that cannot be listed is a leak, not a filter).
    # The reconciliation identity still holds in both modes: with the drain open every
    # eligible posting lands in `visible` or `hidden_below_cutoff`; with it closed,
    # duplicates land in `hidden_duplicate` instead.
    kept = 0
    hidden_handled = 0
    surfaced_job_ids: list[int] = []
    for posting in eligible:
        suppression = suppressions.get(posting.posting_id)
        if suppression is not None and not include_duplicates:
            hidden_duplicate += 1
            continue
        if suppression is not None:
            visible.append(replace(posting, duplicate_of=suppression.survivor_posting_id))
            continue
        # The ledger check sits after dedup and before the cutoff. Before the cutoff for the same
        # reason eligibility is: `top 8` should return 8 ACTIONABLE rows, not 8 slots of which
        # five were built last week.
        job_id = anchors.get(posting.posting_id)
        disposition = handled.get(job_id) if job_id is not None else None
        if disposition is not None and not include_handled:
            hidden_handled += 1
            continue
        if disposition is not None:
            visible.append(replace(posting, handled_as=disposition.disposition))
            continue
        if kept < limit:
            if job_id is not None:
                surfaced_job_ids.append(job_id)
            visible.append(posting)
            kept += 1
        else:
            # Counted, not discarded. Everything here cleared every filter and was beaten
            # only by rank, which is a different reason from every other bucket and the one
            # the funnel could not name before P0 item 3.
            hidden_below_cutoff += 1
    if record_surfaced:
        _record_surfaced(engine, settings, surfaced_job_ids, now=now, run_id=run_id)
    return RankedResults(
        surfaced_job_ids=tuple(surfaced_job_ids),
        visible=visible,
        hidden_ineligible=hidden,
        hidden_non_swe=hidden_non_swe,
        considered=len(rows),
        hidden_hard_filter=hidden_hard_filter,
        hidden_below_cutoff=hidden_below_cutoff,
        skipped_not_new=skipped_not_new,
        hidden_duplicate=hidden_duplicate,
        identities_are_complete=ids_complete,
        hidden_handled=hidden_handled,
        suppressions=tuple(suppressions.values()),
    )


def _record_surfaced(
    engine: Engine,
    settings: Settings,
    job_ids: Sequence[int],
    *,
    now: datetime,
    run_id: int | None,
) -> None:
    """Mark the jobs this call surfaced as leads `seen`, TTL'd by `seen_ttl_days`.

    Written here rather than by each caller so `top` and the pipeline cannot drift on what counts
    as "surfaced". That makes the ranker a writer, which it already was — it calls
    `run_eligibility`, which persists verdicts.

    Monotonic, so this is a no-op against a job already `built` or `skipped`: `record_disposition`
    returns False without writing rather than downgrading it.

    **Not swallowed.** A failed `seen` write means tomorrow's run re-serves today's rows, which
    is the exact defect this slice exists to remove — measured live, five postings each tailored
    across four separate runs. Silently degrading back to that is worse than failing loudly.

    Consequence, deliberate and reversible: two `top` invocations inside the TTL show different
    rows, because the first advanced the queue. `--include-handled` brings them back, and the
    command says so whenever the bucket is non-empty.
    """
    if not job_ids:
        return
    expires_at = now + timedelta(days=settings.seen_ttl_days)
    with engine.begin() as conn:
        for job_id in job_ids:
            record_disposition(
                conn,
                job_id,
                disposition="seen",
                reason="surfaced",
                expires_at=expires_at,
                now=now,
                run_id=run_id,
            )


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


def _why_cell(posting: RankedPosting) -> str:
    """A drained row names why it was suppressed, inline, so it can never be read as an ordinary
    lead. Both drains annotate; a normally-visible row is unannotated."""
    if posting.duplicate_of is not None:
        return f"{posting.why} · duplicate of {posting.duplicate_of}"
    if posting.handled_as is not None:
        return f"{posting.why} · already {posting.handled_as}"
    return posting.why


def _verdict_token(verdict: str | None) -> str:
    """A one-token eligibility flag, chosen so no value reads as a clean bill of health
    (D-P2-18): `eligible` means only that no catalogued disqualifier was detected."""
    return {
        "ineligible": "blocked",
        "uncertain": "check",
        "eligible": "no flags",
    }.get(verdict or "", "-")


def _new_posting_ids(conn: Connection) -> set[int]:
    """Posting ids with a `new` event past the digest cursor (D18).

    `new` only: a reopened or revised posting is in the digest but is not a new
    opportunity, and --new is documented as "postings with a `new` event after the
    digest cursor".
    """
    cursor = get_digest_cursor(conn)
    rows = conn.execute(
        select(posting_events.c.posting_id)
        .where(posting_events.c.id > cursor)
        .where(posting_events.c.kind == "new")
    ).all()
    return {int(row.posting_id) for row in rows}


def top(
    ctx: typer.Context,
    n: int = typer.Argument(10, help="Number of postings to show."),
    include_ineligible: bool = typer.Option(
        False, "--include-ineligible", help="Show postings persisted as ineligible."
    ),
    include_non_swe: bool = typer.Option(
        False, "--include-non-swe", help="Show postings the title role gate reads as non-software."
    ),
    include_duplicates: bool = typer.Option(
        False, "--include-duplicates", help="Show postings suppressed as duplicates."
    ),
    include_handled: bool = typer.Option(
        False,
        "--include-handled",
        help="Show postings already built, skipped, or surfaced inside their seen TTL.",
    ),
    new: bool = typer.Option(
        False, "--new", help="Only postings first seen since your last digest."
    ),
    no_record: bool = typer.Option(
        False,
        "--no-record",
        help="Rank without marking anything `seen`, so this call does not advance the queue. "
        "Use it for a second look, or for a script that ranks once to display and again to act.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output ranked postings as JSON."),
) -> None:
    """Rank open postings against your profile (on-demand, §3.6)."""
    app_ctx = build_context(ctx.obj)
    output_console = Console(stderr=json_output)
    try:
        results = rank_open_postings(
            app_ctx.engine,
            app_ctx.settings,
            limit=n,
            include_ineligible=include_ineligible,
            include_non_swe=include_non_swe,
            include_duplicates=include_duplicates,
            include_handled=include_handled,
            only_new=new,
            output_console=output_console,
            record_surfaced=not no_record,
        )
    except NoProfileError:
        output_console.print("no profile yet — run `boardwatch init` first")
        raise typer.Exit(code=1) from None
    if json_output and results.hidden_handled and not include_handled:
        # Printed to stderr, BEFORE the JSON, and before the early return below: a script whose
        # ranked array came back empty because the queue was already advanced would otherwise get
        # `[]` with no reason at all, which is indistinguishable from "no matches exist".
        output_console.print(
            f"{results.hidden_handled} hidden as already handled (built, skipped, or surfaced "
            "recently) — re-run with --include-handled to see them.",
            markup=False,
        )
    if json_output:
        console.print_json(
            json.dumps(
                [
                    {
                        "posting_id": p.posting_id,
                        "title": p.title,
                        "company": p.company,
                        "score": p.score.total,
                        "why": p.why,
                        "role": p.role,
                        "duplicate_of": p.duplicate_of,
                        "handled_as": p.handled_as,
                    }
                    for p in results.visible
                ]
            )
        )
        return
    # Printed before the empty-output guard, and regardless of whether anything was hidden:
    # this is the one state where the absence of a duplicate count means nothing was
    # measured. Nothing in the automated path writes identities — `scan` refreshes postings
    # but never recomputes their identity rows — so a single newly discovered posting closes
    # the completeness gate and disables suppression until the backfill is re-run by hand.
    if not results.identities_are_complete:
        output_console.print(
            "duplicate suppression is OFF: some open postings have no current-version "
            "identity, so 0 duplicates here means not measured, not none. Run "
            "`boardwatch identities backfill`.",
            markup=False,
        )
    if not results.visible and not results.hidden_ineligible and not results.hidden_non_swe:
        if new:
            output_console.print("nothing new since your last digest")
        else:
            output_console.print("no open postings match your filters")
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
            f"{p.score.total:.2f}", _verdict_token(p.verdict),
            _why_cell(p),
        )
    console.print(table)
    if results.hidden_ineligible and not include_ineligible:
        console.print(
            f'{results.hidden_ineligible} hidden as ineligible. "no flags" means no catalogued '
            "disqualifier was detected, not that you qualify.",
            markup=False,
        )
    if results.hidden_non_swe and not include_non_swe:
        console.print(
            f"{results.hidden_non_swe} hidden as non-software roles — see them with "
            "--include-non-swe, each with the title text that vetoed it.",
            markup=False,
        )
    if results.hidden_duplicate and not include_duplicates:
        console.print(
            f"{results.hidden_duplicate} hidden as duplicates — see them with "
            "--include-duplicates, each naming the posting it duplicates.",
            markup=False,
        )
    if results.hidden_handled and not include_handled:
        # Printed because the queue advancing is otherwise indistinguishable from the corpus
        # shrinking: a job you were shown yesterday is simply absent today, with no visible
        # reason. `seen` rows lapse on their own; `built`/`skipped` need `ledger reopen`.
        console.print(
            f"{results.hidden_handled} hidden as already handled (built, skipped, or surfaced "
            "recently) — see them with --include-handled, each naming its disposition.",
            markup=False,
        )
