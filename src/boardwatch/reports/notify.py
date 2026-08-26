"""Pure selection of NEW matching postings for `boardwatch notify` (P5).

A "new match" is a posting with a `new` posting_events row past the notify cursor whose
current state passes the profile's hard filters and is not persisted `ineligible`. This
module is pure and side-effect-free: it reads current DB state only — it never runs
preflight, eligibility, or an LLM, so `scan && notify` stays cheap. One connection in,
one value object out, no rendering, no delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import Connection, select

from boardwatch.core.clock import utcnow
from boardwatch.core.settings import Settings
from boardwatch.eligibility.preflight import current_identity
from boardwatch.eligibility.read import current_verdicts
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.rank.heuristic import ProfileView, passes_hard_filters, score_posting
from boardwatch.rank.leveling import load_leveling, resolve_schemes
from boardwatch.rank.role_gate import role_verdict, zero_signal_verdict
from boardwatch.rank.seniority_gate import TargetBand, seniority_verdict
from boardwatch.store.param_chunks import id_chunks
from boardwatch.store.queries import body_is_empty, current_posting_versions
from boardwatch.store.tables import companies, extractions, posting_events, postings


@dataclass(frozen=True)
class NotifyItem:
    posting_id: int
    title: str
    company: str
    url: str | None
    score: float
    verdict: str | None


@dataclass(frozen=True)
class NotifyResult:
    items: tuple[NotifyItem, ...]
    since_event_id: int
    max_event_id: int

    @property
    def is_empty(self) -> bool:
        return not self.items


def _new_ids_and_max(conn: Connection, since_event_id: int) -> tuple[set[int], int]:
    # max_event_id advances over ALL events (any kind) past the cursor, not just
    # `new` ones: a window with only reopened/revised/closed events must still move
    # the floor forward, or those events get re-scanned every run indefinitely. This
    # is safe because event ids are monotonic and selection stays gated on
    # `kind == "new"`, so a later `new` event always has a higher id and can never
    # be skipped by advancing past an earlier non-`new` event.
    rows = conn.execute(
        select(posting_events.c.id, posting_events.c.posting_id, posting_events.c.kind)
        .where(posting_events.c.id > since_event_id)
        .order_by(posting_events.c.id)
    ).all()
    # The cursor is the floor: an empty window must not move it backwards.
    max_event_id = since_event_id
    ids: set[int] = set()
    for row in rows:
        max_event_id = max(max_event_id, int(row.id))
        if row.kind == "new":
            ids.add(int(row.posting_id))
    return ids, max_event_id


def select_new_matches(
    conn: Connection,
    since_event_id: int,
    profile: ProfileView,
    settings: Settings,
    *,
    now: datetime | None = None,
    include_non_swe: bool = False,
    include_zero_signal: bool = False,
    include_over_seniority: bool = False,
) -> NotifyResult:
    now = now or utcnow()
    new_ids, max_event_id = _new_ids_and_max(conn, since_event_id)
    if not new_ids:
        return NotifyResult(items=(), since_event_id=since_event_id, max_event_id=max_event_id)
    version = load_taxonomy(settings.config_dir).version
    base = (
        select(
            postings.c.id,
            postings.c.title,
            postings.c.url,
            postings.c.posted_at,
            postings.c.locations_json,
            postings.c.remote_policy,
            companies.c.name.label("company_name"),
            companies.c.provider,
            companies.c.slug,
            extractions.c.json.label("extraction_json"),
            # The zero-signal rule's third input, computed in SQLite so the body itself is
            # never transferred. See `queries.body_is_empty`.
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
    )
    # Chunked past SQLite's bound-parameter cap. `new_ids` is NOT bounded by one run: the
    # cursor only advances when matches are delivered or when there are none, so on an install
    # with no delivery channel configured (both default off) it stays at 0 and this set is the
    # whole history of `new` events — 37,438 today. Concatenation is exact here: no GROUP BY or
    # DISTINCT, and the ordering happens in Python after every chunk is read.
    rows = [
        row
        for chunk in id_chunks(sorted(new_ids))
        for row in conn.execute(base.where(postings.c.id.in_(chunk))).all()
    ]
    versions = current_posting_versions(conn, list(new_ids))
    # Read-only: the live profile's (profile_hash, rules_hash) without running the lane.
    identity = current_identity(conn, settings)
    profile_hash, rules_hash = identity if identity is not None else (None, None)
    verdicts = current_verdicts(
        conn,
        [cv.posting_version_id for cv in versions.values()],
        profile_hash,
        rules_hash,
    )
    # Loaded ONCE: `load_leveling` reads (and may parse an override) on every call, so a
    # per-row load would put a YAML parse inside the notify loop.
    leveling = load_leveling(settings.config_dir)
    schemes, _binding_warning = resolve_schemes(leveling, settings.config_dir)
    tier = leveling.fields["software"]
    target_band = cast(TargetBand, profile.target_seniority_band)
    items: list[NotifyItem] = []
    for row in rows:
        if not passes_hard_filters(
            row.title, list(row.locations_json or []), row.remote_policy,
            profile, settings.location_filter_mode,
        ):
            continue
        if verdicts.get(int(row.id)) == "ineligible":
            continue
        role = role_verdict(row.title)[0]
        # Same default as `top`: a non-software title is not a "new match" worth a push.
        # Suppressed rather than dropped — `top --include-non-swe` still shows it.
        if not include_non_swe and role == "not_swe":
            continue
        # Same default as `top`, and in the same ORDER (before the band gate): a posting whose
        # title carried no role signal and whose body yielded no recognised term is not a "new
        # match" worth a push, and pushing it would advance the cursor past a posting `top`
        # refuses to show — a delivered lead that no drain can bring back. `unmeasured` is
        # pushed: an abstain is never a suppression, exactly as `uncertain` band is.
        # Suppressed rather than dropped — `top --include-zero-signal` still shows it.
        if not include_zero_signal and zero_signal_verdict(
            role, row.extraction_json, body_empty=bool(row.body_empty)
        )[0] == "veto":
            continue
        # Same default as `top`: a title above the operator's target band is not a "new match"
        # worth a push. `uncertain` is pushed — an abstain is never a suppression.
        band, _ = seniority_verdict(
            row.title, schemes.get((row.provider, row.slug)), target_band, tier, leveling,
        )
        if not include_over_seniority and band == "above_band":
            continue
        skills = set((row.extraction_json or {}).get("skills", []))
        score = score_posting(
            profile, skills, row.title, row.posted_at,
            list(row.locations_json or []), row.remote_policy,
            settings.weights, now, settings.recency_half_life_days,
            settings.zero_skill_coverage_prior,
        )
        items.append(NotifyItem(
            posting_id=int(row.id), title=row.title, company=row.company_name,
            url=row.url, score=score.total, verdict=verdicts.get(int(row.id)),
        ))
    items.sort(key=lambda i: i.score, reverse=True)
    return NotifyResult(
        items=tuple(items), since_event_id=since_event_id, max_event_id=max_event_id
    )
