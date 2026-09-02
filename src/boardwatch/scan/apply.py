"""Per-board transactional apply — the §3.5 status table, verbatim.

Exactly ONE transaction per BoardSnapshot (D16). A crash anywhere rolls the
whole board back: inventory, events, validators, and the scan row commit or
vanish together (state test h — the 304-trap regression).

Rules folded in:
- D23: every posting listed in a complete or partial snapshot has
  consecutive_missing reset to 0; increments happen only on complete.
- D25 persistence rule: every positive observation refreshes ALL
  provider-sourced mutable fields and raw_json regardless of content_hash;
  only a body-hash change emits `revised` (extraction is hash-keyed, so it
  stays current through metadata-only updates). Its ONE exception is a field
  the observation itself declared `secondhand` (D-414(a), `_refreshed_fields`),
  and a declared `body_text` additionally suppresses the revision itself, so an
  aggregator's rendering never becomes the version eligibility quotes.
- D22: http_cache is upserted from observed_validators inside this same
  transaction, for `complete` snapshots only; `unchanged`/`partial`/`failed`
  never touch it. `unchanged` writes exactly one board_scans row (D15).
- Plan deviation 8: a closed posting reappearing with a changed body emits
  both `reopened` and `revised`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from boardwatch.core.clock import utcnow
from boardwatch.core.models import BoardSnapshot, RawPosting, SecondhandField
from boardwatch.core.normalize import content_hash, normalize_title
from boardwatch.core.posting_identity import IdentityInputs, compute_identities
from boardwatch.store.events import append_event
from boardwatch.store.identity_queries import write_identities
from boardwatch.store.sources import record_version_source
from boardwatch.store.tables import (
    board_scans,
    companies,
    http_cache,
    jobs,
    posting_versions,
    postings,
)

CLOSE_AFTER_MISSES = 2  # not configurable (plan Conventions)


@dataclass
class ApplyResult:
    status: str
    listed: int = 0
    new: int = 0
    revised: int = 0
    reopened: int = 0
    closed: int = 0


def apply_board(
    engine: Engine,
    snapshot: BoardSnapshot,
    company_id: int,
    run_id: int,
    scan_kind: str = "board",
) -> ApplyResult:
    """Apply one board snapshot. `scan_kind` says which subsystem produced it (D-285).

    The default is not a hidden decision: every caller on the six-provider scan path genuinely
    IS a board scan, so `"board"` states that fact. A lane passes `"lane"` explicitly, which is
    what keeps `coverage_queries.load_board_coverage` from counting a company twice when a lane
    touches a board the scan already covered this run.
    """
    started_at = utcnow()
    with engine.begin() as conn:
        if snapshot.status == "failed":
            _scan_row(
                conn, run_id, company_id, started_at, "failed", 0, snapshot.error,
                scan_kind=scan_kind,
            )
            return ApplyResult(status="failed")
        if snapshot.status == "unchanged":
            _scan_row(
                conn, run_id, company_id, started_at, "unchanged", 0, None,
                scan_kind=scan_kind,
            )
            return ApplyResult(status="unchanged")
        result = _apply_listed(conn, snapshot.postings, company_id, run_id, snapshot.url)
        result.status = snapshot.status
        if snapshot.status in ("complete", "partial"):
            _reset_listed_but_unrefreshed(
                conn, snapshot.postings, snapshot.listed_ids, company_id
            )
        if snapshot.status == "complete":
            result.closed = _process_missing(
                conn, snapshot.postings, snapshot.listed_ids, company_id, run_id
            )
            _persist_validators(conn, snapshot)
        _scan_row(
            conn, run_id, company_id, started_at, snapshot.status,
            len(snapshot.postings), snapshot.error, snapshot=snapshot, scan_kind=scan_kind,
        )
        return result


def _apply_listed(
    conn: Connection, raw_postings: list[RawPosting], company_id: int, run_id: int, source_url: str
) -> ApplyResult:
    now = utcnow()
    # A board may list one provider_posting_id more than once in a single snapshot — Workable
    # repeats a shortcode across location facets, and an aggregator may serve one posting twice.
    # `existing` is snapshotted once below and never updated in the loop, so a duplicate would
    # take the INSERT branch a second time and violate UNIQUE(company_id, provider_posting_id),
    # aborting the whole scan. Collapse to the first occurrence — the same guard the lanes apply
    # in their `_group_by_company`.
    seen_ids: set[str] = set()
    deduped: list[RawPosting] = []
    for raw in raw_postings:
        if raw.provider_posting_id in seen_ids:
            continue
        seen_ids.add(raw.provider_posting_id)
        deduped.append(raw)
    raw_postings = deduped
    result = ApplyResult(status="", listed=len(raw_postings))
    existing = {
        row.provider_posting_id: row
        for row in conn.execute(
            select(postings).where(postings.c.company_id == company_id)
        ).all()
    }
    # One query per board, for the `cross_host` identity component (P6 slice 2 §4).
    company_name = str(
        conn.execute(select(companies.c.name).where(companies.c.id == company_id)).scalar_one()
    )
    for raw in raw_postings:
        new_hash = content_hash(raw.body_text)
        row = existing.get(raw.provider_posting_id)
        if row is None:
            job_id = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])  # type: ignore[index]
            fields = _inserted_fields(raw, now)
            inserted = conn.execute(
                insert(postings).values(
                    company_id=company_id,
                    job_id=job_id,
                    provider_posting_id=raw.provider_posting_id,
                    first_seen_at=now,
                    status="open",
                    consecutive_missing=0,
                    content_hash=new_hash,
                    body_text=raw.body_text,
                    **fields,
                )
            )
            posting_id = int(inserted.inserted_primary_key[0])  # type: ignore[index]
            vid = _insert_version(conn, posting_id, new_hash, raw.body_text, now, run_id, "new")
            record_version_source(
                conn, posting_version_id=vid, run_id=run_id, source_url=source_url,
                source_record_id=raw.provider_posting_id, observed_at=now, payload_hash=new_hash,
            )
            append_event(conn, posting_id, "new", run_id)
            _write_posting_identity(
                conn, raw, posting_id=posting_id, company_id=company_id,
                company_name=company_name, title=fields["title"],
                locations=fields["locations_json"],
                content_hash=new_hash, body_text=raw.body_text, first_seen_at=now, now=now,
            )
            result.new += 1
            continue
        # D25: regardless of content_hash — minus whatever this observation declared secondhand.
        values: dict[str, Any] = _refreshed_fields(raw, now)
        values["consecutive_missing"] = 0  # D23: reset on every positive observation
        # D-325, the same rule applied to the death probe's counter. A listing is stronger
        # evidence than any number of failed probes: the posting is on a board right now. This
        # is half the drain the probe owes itself (the other half is an `alive` probe), and it
        # is what stops a strike earned during a CDN outage surviving to meet a second one
        # weeks later and close a posting nobody ever measured as dead twice in a row.
        values["death_strikes"] = 0
        if row.status == "closed":
            values["status"] = "open"
            values["closed_at"] = None
            append_event(conn, row.id, "reopened", run_id)
            result.reopened += 1
        # The whole REVISION is skipped for a secondhand body, not merely the two columns.
        # Eligibility reads the CURRENT `posting_versions` row, so leaving `_insert_version` armed
        # while withholding `postings.content_hash` would put an aggregator's text at the head of
        # the version chain — the exact substitution — AND leave the posting's own hash naming a
        # version that is no longer current. One condition, both halves (D-414(a)).
        if row.content_hash != new_hash and "body_text" not in raw.secondhand:
            values["content_hash"] = new_hash
            values["body_text"] = raw.body_text
            vid = _insert_version(conn, row.id, new_hash, raw.body_text, now, run_id, "revised")
            record_version_source(
                conn, posting_version_id=vid, run_id=run_id, source_url=source_url,
                source_record_id=raw.provider_posting_id, observed_at=now, payload_hash=new_hash,
            )
            append_event(conn, row.id, "revised", run_id)
            result.revised += 1
        conn.execute(update(postings).where(postings.c.id == row.id).values(**values))
        # AFTER the update, so the identity is computed from what was just persisted. The
        # observation may have moved title or locations without producing a revision (the D25
        # rule above refreshes them regardless of content_hash), which moves an identity key.
        # Every identity-bearing value is read the same way `content_hash` already was — out of
        # `values` when this observation wrote it, off the row when it did not. A secondhand
        # declaration (D-414(a)) leaves title and locations on the row, so reading them from `raw`
        # would key the posting on a value NO row holds, and dedup would suppress against evidence
        # that exists nowhere.
        _write_posting_identity(
            conn, raw, posting_id=int(row.id), company_id=company_id,
            company_name=company_name,
            title=values.get("title", row.title),
            locations=values.get("locations_json", row.locations_json),
            content_hash=values.get("content_hash", row.content_hash),
            body_text=values.get("body_text", row.body_text),
            first_seen_at=row.first_seen_at, now=now,
        )
    return result


def _write_posting_identity(
    conn: Connection,
    raw: RawPosting,
    *,
    posting_id: int,
    company_id: int,
    company_name: str,
    title: str,
    locations: Any,
    content_hash: str,
    body_text: str,
    first_seen_at: datetime,
    now: datetime,
) -> None:
    """Keep this posting's stored identities current, inside the board's own transaction.

    P6 slice 2 §4, closing D-098: before this, `write_identities` had exactly one caller in
    `src/` — the manual `boardwatch identities backfill`. Nothing in the scan or pipeline path
    wrote identities, so **any** run that discovered one new posting left it uncovered,
    `identities_complete()` went False and duplicate suppression silently switched off
    corpus-wide.

    Written here rather than as a sweep in the pipeline, which is what D-098 had in mind when it
    priced this work at a second corpus-wide `body_text` load: every field `IdentityInputs`
    needs is already in hand at this point, so the cost is O(postings this board listed) and no
    body is loaded that was not already in memory.

    `title`, `locations`, `content_hash` and `body_text` are PASSED rather than read off `raw`,
    for the same reason `first_seen_at` already was: what the identity must name is what the ROW
    now holds, and after a secondhand declaration (D-414(a)) each can come off the row instead of
    off this observation. `body_text` matters here as much as `content_hash` and used to be read
    from `raw`: `compute_identities` reads it, and on a secondhand UPDATE whose stored provider
    body is empty while Indeed's is not, the aggregator's text would let it record an `exact_quad`
    the persisted row cannot reproduce — `identities verify` would then read stale and the leakage
    metrics would carry a claim no recomputation from the row could confirm. `url` is deliberately
    NOT among the passed values, and that is measured rather than assumed: `compute_identities`
    reads company / provider_posting_id / title / locations / content_hash / body_text /
    company_name and never touches `IdentityInputs.url`, so passing the row's URL instead of the
    observation's produces byte-identical stored identities. URL only ranks survivors in
    `core.dedup`, off a separate loader that reads the COLUMN back. A parameter that cannot change
    an output is not a safeguard, it is a claim nobody can test.

    Deliberately NOT wrapped in a try/except. A failure fails the board's transaction, so the
    posting and its identity commit or vanish together — the D16 property this module is built
    on. A posting stored without its identity is exactly the state that disables suppression.
    """
    write_identities(
        conn,
        posting_id,
        compute_identities(
            IdentityInputs(
                posting_id=posting_id,
                company_id=company_id,
                company_name=company_name,
                provider_posting_id=raw.provider_posting_id,
                title=title,
                # Mirrors identity_queries.load_identity_inputs' coercion: non-string elements
                # are dropped, not stringified, so a JSON `[null]` cannot become the truthy
                # location component `["none"]` and let two postings suppress on evidence
                # neither one has. The guard also earns its keep on the `locations_json` column,
                # which is JSON and hands back whatever was stored.
                locations=(
                    [x for x in locations if isinstance(x, str)]
                    if isinstance(locations, list)
                    else None
                ),
                content_hash=content_hash,
                body_text=body_text,
                url=raw.url,
                first_seen_at=first_seen_at,
            )
        ),
        now=now,
    )


def _insert_version(
    conn: Connection, posting_id: int, content_hash: str, body_text: str,
    captured_at: datetime, run_id: int, capture_reason: str,
) -> int:
    """Append an immutable content version (D29). Called on new and body-revision only."""
    return int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=content_hash, body_text=body_text,
                captured_at=captured_at, run_id=run_id, capture_reason=capture_reason,
            )
        ).inserted_primary_key[0]  # type: ignore[index]
    )


# Which columns each declarable field owns. The `title` -> normalized_title and `salary` -> four
# columns fan-outs live HERE and not in the declaration, so a lane declares what it observed and
# can never leave a derived column refreshed from a value the row no longer holds.
_SECONDHAND_COLUMNS: dict[SecondhandField, tuple[str, ...]] = {
    "title": ("title", "normalized_title"),
    "url": ("url",),
    "locations": ("locations_json",),
    "remote_policy": ("remote_policy",),
    "department": ("department",),
    "posted_at": ("posted_at",),
    "updated_at": ("updated_at",),
    # DELIBERATELY EMPTY, and the only entry that is. `content_hash` and `body_text` are not
    # `_mutable_fields` columns: `_apply_listed` writes them inside the revision branch, together
    # with the immutable `posting_versions` row and the `revised` event, and all four have to be
    # withheld or none of them. So the declaration is honoured at that branch's own condition and
    # there is nothing left for this map to drop. The emptiness is asserted rather than assumed by
    # test_body_text_is_declarable_but_owns_no_mutable_column, and the exhaustiveness assertion in
    # test_every_column_the_writer_refreshes_is_classified_exactly_once still forces any FUTURE
    # declarable field into this map.
    "body_text": (),
    "salary": ("salary_min", "salary_max", "salary_currency", "salary_period"),
    "raw_json": ("raw_json",),
}


def _refreshed_fields(raw: RawPosting, now: datetime) -> dict[str, Any]:
    """`_mutable_fields` minus the columns this observation is not the record of truth for.

    D-414(a). D25 refreshes every provider-sourced field regardless of `content_hash`, which is
    right for a provider reading the employer's own board and wrong for an aggregator lane whose
    hit converged onto that provider's `(company_id, provider_posting_id)`: the lane never looked
    at the provider's `remote_policy`, `department` or `salary_*` at all, and the location it did
    read is its own index of the posting, not the employer's field. Writing either over a
    provider's row is a live deletion path — with `location_filter_mode = "hard"` a posting the
    provider recorded as remote and the aggregator renders as one metro is hard-vetoed, and a lead
    the pipeline already held is dropped in the same run, because the lane stage runs after the
    scan and before the ranker.

    UPDATE PATH ONLY. `_inserted_fields` is the INSERT half and they differ on purpose, because
    the two paths lose different things: on UPDATE a prior observation exists and withholding
    preserves it, while on INSERT withholding replaces a value the lane genuinely holds with a
    schema default. The one INSERT exception is stated there.

    `last_seen_at` and the miss counters are untouched by this and no declaration may withhold
    them. A listing is positive evidence that the posting is ALIVE regardless of whose text
    arrived, so `consecutive_missing` and `death_strikes` still reset — otherwise a stale strike
    survives to meet a second one and closes a posting the lane just watched being served.

    The `content_hash` / `body_text` pair is NOT here because it is not a `_mutable_fields` column;
    it is written in `_apply_listed`'s revision branch, which reads the declaration itself.

    `del` rather than `pop(name, None)`: a rename that leaves `_SECONDHAND_COLUMNS` pointing at a
    column `_mutable_fields` no longer writes must fail loudly, not silently stop protecting it.
    """
    fields = _mutable_fields(raw, now)
    for name in raw.secondhand:
        for column in _SECONDHAND_COLUMNS[name]:
            del fields[column]
    return fields


def _inserted_fields(raw: RawPosting, now: datetime) -> dict[str, Any]:
    """`_mutable_fields` with a secondhand LOCATION downgraded to no location evidence at all.

    D-414(a), and the reason the INSERT needs a rule of its own after all. The original split said
    a secondhand INSERT is harmless because a later provider board scan corrects it. That holds for
    a TIER-2 lane-first company only, and the store says why three times: `upsert_lane_company`
    writes `watched=False` for it (D-285, load-bearing — a watched row on a provider the scanner
    cannot parse would add an `unknown provider` line to every run forever); `get_watched_companies`
    filters `watched.is_(True)`; and `scan.coordinator` takes its company rows from nowhere else, so
    a tier-2 hit's INSERT is the only writer that row will ever have. A TIER-1 hit is now
    auto-watched (`upsert_lane_company(watch=True)`), so a scan DOES correct it — next run, not this
    one, because the lane stage runs after the scan. Either way this INSERT's location decides at
    least one run, and a location the aggregator assigned that classifies `non_us` would hard-veto —
    DELETE — the lead under `location_filter_mode = "hard"` on a role never placed outside the US.
    `classify_location` is a positive US allowlist that drops only a CONFIRMED non-US posting, so a
    US metro or an unresolved string is KEPT: the hazard is a false `non_us`, not a metro.

    FAIL-SAFE DIRECTION, chosen for THIS gate and different from the one next door. The location
    gate's failure modes are not symmetric: a false `non_us` DELETES a real lead permanently and
    invisibly, while a false `unknown` merely declines to filter one. `classify_location` builds a
    per-segment verdict list and returns `unknown` when it is empty, so `[]` classifies `unknown` —
    which the hard gate KEEPS (Mit's fail-open ruling, D-251). Recording no location is therefore
    the direction that cannot delete. It costs the location-bearing identity kinds: with `[]`,
    `normalized_locations` returns None and `compute_identities` emits no `company_title_location`,
    `cross_host` or `exact_quad`, so this row can neither suppress nor be suppressed on a place the
    aggregator assigned. That is the same direction — no evidence is not evidence of sameness.

    ONLY `locations`, and the rest of the declaration is deliberately still written. `title` and
    `url` cannot be withheld and leave a usable row, and `title` is the field the lane's own search
    facet matched on, which is the closest to first-hand anything it carries. `department`,
    `salary_*`, `posted_at`, `updated_at` and `raw_json` move a score or a display line; none of
    them can veto. `remote_policy` arrives `unknown` from the lane anyway. Location is singled out
    because it is the one declared field that BOTH hard-vetoes and can be withheld without making
    the row unusable. The residual exposure is recorded rather than widened: an exclude-title
    filter reads Indeed's title, so a lane-first row whose title the aggregator re-worded can still
    be filtered on a string the employer never wrote.
    """
    fields = _mutable_fields(raw, now)
    if "locations" in raw.secondhand:
        fields["locations_json"] = []
    return fields


def _mutable_fields(raw: RawPosting, now: datetime) -> dict[str, Any]:
    """All provider-sourced mutable fields + raw_json (the D25 persistence rule)."""
    return {
        "title": raw.title,
        "normalized_title": normalize_title(raw.title),
        "url": raw.url,
        "locations_json": raw.locations,
        "remote_policy": raw.remote_policy,
        "department": raw.department,
        "posted_at": raw.posted_at,
        "updated_at": raw.updated_at,
        "salary_min": raw.salary_min,
        "salary_max": raw.salary_max,
        "salary_currency": raw.salary_currency,
        "salary_period": raw.salary_period,
        "raw_json": raw.raw_json,
        "last_seen_at": now,
    }


def _reset_listed_but_unrefreshed(
    conn: Connection,
    raw_postings: list[RawPosting],
    listed_ids: frozenset[str],
    company_id: int,
) -> None:
    """D23 for subset-detail providers, on BOTH complete and partial snapshots: a posting
    positively LISTED but not among the refreshed postings (SmartRecruiters known/skipped)
    is untouched by _apply_listed, so reset its miss counter here. No-op when listed_ids is
    empty — single-request providers already reset every listed posting via _apply_listed."""
    if not listed_ids:
        return
    applied = {raw.provider_posting_id for raw in raw_postings}
    to_reset = tuple(listed_ids - applied)
    if not to_reset:
        return
    conn.execute(
        update(postings)
        .where(
            postings.c.company_id == company_id,
            postings.c.status == "open",
            postings.c.provider_posting_id.in_(to_reset),
            postings.c.consecutive_missing != 0,
        )
        .values(consecutive_missing=0)
    )


def _process_missing(
    conn: Connection,
    raw_postings: list[RawPosting],
    listed_ids: frozenset[str],
    company_id: int,
    run_id: int,
) -> int:
    """Close postings absent from the board (complete snapshots only). `listed_ids` is the
    full live inventory when the provider fetched only a subset of details (SmartRecruiters
    skips known postings); it falls back to the applied postings for single-request providers
    that return the whole board. Listed-but-skipped rows already had their miss counter reset
    by _reset_listed_but_unrefreshed, so this loop only skips or closes."""
    applied = {raw.provider_posting_id for raw in raw_postings}
    effective = listed_ids or frozenset(applied)
    open_rows = conn.execute(
        select(
            postings.c.id, postings.c.provider_posting_id, postings.c.consecutive_missing
        ).where(postings.c.company_id == company_id, postings.c.status == "open")
    ).all()
    closed = 0
    now = utcnow()
    for row in open_rows:
        if row.provider_posting_id in effective:
            continue
        misses = row.consecutive_missing + 1
        if misses >= CLOSE_AFTER_MISSES:
            conn.execute(
                update(postings)
                .where(postings.c.id == row.id)
                .values(consecutive_missing=misses, status="closed", closed_at=now)
            )
            append_event(conn, row.id, "closed", run_id)
            closed += 1
        else:
            conn.execute(
                update(postings)
                .where(postings.c.id == row.id)
                .values(consecutive_missing=misses)
            )
    return closed


def _persist_validators(conn: Connection, snapshot: BoardSnapshot) -> None:
    """D22: complete snapshots only; same transaction as the applied inventory."""
    observed = snapshot.observed_validators
    if observed is None:
        return
    stmt = sqlite_insert(http_cache).values(
        url=snapshot.url,
        etag=observed.etag,
        last_modified=observed.last_modified,
        fetched_at=utcnow(),
        status=200,
    )
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[http_cache.c.url],
            set_={
                "etag": stmt.excluded.etag,
                "last_modified": stmt.excluded.last_modified,
                "fetched_at": stmt.excluded.fetched_at,
                "status": stmt.excluded.status,
            },
        )
    )


def _scan_row(
    conn: Connection,
    run_id: int,
    company_id: int,
    started_at: datetime,
    status: str,
    listed: int,
    error: str | None,
    *,
    snapshot: BoardSnapshot | None = None,
    scan_kind: str = "board",
) -> None:
    conn.execute(
        insert(board_scans).values(
            run_id=run_id,
            company_id=company_id,
            started_at=started_at,
            finished_at=utcnow(),
            status=status,
            postings_listed=listed,
            error=error,
            scan_kind=scan_kind,
            # NULL, not 0, when there is no snapshot: a failed board's coverage is undefined.
            board_reported_total=None if snapshot is None else snapshot.board_reported_total,
            board_enumerated=None if snapshot is None else snapshot.board_enumerated,
            detail_deferred=None if snapshot is None else snapshot.detail_deferred,
            board_total_censored=(
                None
                if snapshot is None or snapshot.board_total_censored is None
                else int(snapshot.board_total_censored)
            ),
        )
    )
