"""Record employer links the store already held evidence for but never wrote (D-690).

Two populations, both already on disk, both invisible to the delivery path before this step:

1. **Link-ledger entries.** `apply-routes.toml` names JSON ledgers the owner's browser workflow
   wrote, each `{"<posting_id>": {"company": "<url>", "company_status": "..."}}`. The route loader
   has always read their statuses and never their URLs, so a posting whose employer link was
   already found could still be delivered with the aggregator wrapper. swaploy_middle_links.py in
   job-apps wrote destinations from the same ledgers, but only for entries whose status was one of
   its own verified values; the 13 the review measured (statuses `unknown`, `unverified`, `none`
   and a bare `grnh.se` short link) were skipped for ever. This step reads the same ledgers, keeps
   a URL only when it names ONE posting (not a careers homepage or a shortener landing page), asks
   the run's own liveness prober about it, and records it only on an `alive` verdict.

2. **`grnh.se` short links on the standing queue.** Greenhouse's own shortener is stored as the
   posting's source URL by the Indeed lane. `lanes/grnh_seeds.resolve` already follows that one
   request shape; this step applies it to the postings being delivered, so the lead reaches its
   employer's posting without a browser.

It also drains the `lane_seeds` `grnh.se` backlog (`drain_grnh_seeds`), which is a different
deliverable: a seed resolves to a BOARD, and a board is a candidate for the owner to review, never
a watch this code writes. The review measured 2,018 such seeds with zero attempts; the drain is
capped at `GRNH_DRAIN_LIMIT` per run because one request per seed at the Fetcher's per-host pace is
what bounds the added wall clock.

**What a write must not become.** A destination is where the owner applies, so a link is written
only when (a) it is a single posting's URL, (b) the run's own liveness prober says `alive`, and
(c) the posting has no destination yet — a browser-verified link always wins.
`record_application_destination` validates transport safety only; the three checks above are this
module's job.

**Isolation.** Both readers are additive: a failure costs the link and nothing else, so the runner
treats a raise as one alert line and lets the run finish (`_record_on_disk_links`). Network work
happens OUTSIDE the write transaction, because a ledger probe is seconds and a SQLite write lock
held across it would refuse the web viewer's own writes for that long.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from sqlalchemy import Connection, Engine, func, select

from boardwatch.core.liveness import GONE_STATUSES
from boardwatch.core.politeness import Fetcher, FetchFailure, identifying_user_agent
from boardwatch.delivery.apply_routes import ApplyRoutes
from boardwatch.lanes.grnh_seeds import (
    GRNH_HOSTS,
    MAX_ATTEMPTS_CONSIDERED,
    ResolvedBoard,
    one_line,
    resolve,
)
from boardwatch.pipeline.liveness import LivenessProber
from boardwatch.store.application_destinations import (
    InvalidApplicationDestinationError,
    read_application_destinations,
    record_application_destination,
)
from boardwatch.store.seed_queries import (
    LaneSeed,
    record_seed_attempt,
    unresolved_seed_count,
    unresolved_seeds,
)
from boardwatch.store.tables import companies, postings

EVIDENCE_GRNH_PREFIX = "grnh:v1:"

# The same floor `lanes/grnh_seeds.py` applies to this host: a redirect service is not a board and
# holds no per-tenant load, so the client's own per-host pace is the whole delay.
_GRNH_CRAWL_DELAY_SECONDS = 1.0

# One request per seed at the Fetcher's per-host pace is about 300 s for a full batch. A run is
# lengthened by that at most once; raising the cap spends the operator's morning for no extra reach
# this run could use, because a resolved seed leaves the queue permanently.
GRNH_DRAIN_LIMIT = 300

# The candidate file the drain maintains. It is the registry format `companies import` reads, with
# the provenance the reviewer needs in comments, exactly as `companies discover-grnh` writes it.
GRNH_CANDIDATE_FILENAME = "grnh-board-candidates.yaml"

_GRNH_HOSTS = frozenset(GRNH_HOSTS)

# ---------------------------------------------------------------------------------------------
# The single-posting test. PORTED VERBATIM IN SPIRIT from job-apps
# `autoapply/swap_middle_links.py::specific`/`clean`, which is the predicate that decided which
# ledger entries were the employer's own posting when that writer ran. It is duplicated here rather
# than imported because job-apps is not a dependency of this package; the two must agree, and the
# tests below pin every class the original enumerated. If one changes, both must.
# ---------------------------------------------------------------------------------------------

# A host that is never an employer's own posting page.
_NOT_EMPLOYER = re.compile(
    r"(^|\.)(indeed\.com|linkedin\.com|jobright\.ai|searchwithjack\.com|go\.vansh\.nyc|grnh\.se"
    r"|recruitics\.com|appcast\.io)$"
)
# Path endings that name a portal rather than one posting, unless an id is present.
_GENERIC_ENDPOINTS = frozenset(
    {
        "jobdetail",
        "recruitment.html",
        "job",
        "jobs",
        "apply",
        "search",
        "careers",
        "opportunitydetail",
        "maininforeq.asp",
        "join-team",
    }
)
# Query keys a ledger recorded on the employer URL that are the middle link's own tracking.
_TRACKING = re.compile(
    r"^(utm_.*|source|iis|iisn|indeed-apply-token|cmpid|spread|_gl|rx_.*|ref|gh_src|board_id"
    r"|cid|mobile|width|height|bga|needsRedirect|jan1offset|jun1offset|in_iframe|mode"
    r"|first_page|last_page|team)$"
)
_GENERIC_PATH = re.compile(r"(/[a-z-]{2,5})?/(careers?|jobs|career-home|careers-home)?")


def _clean(url: str) -> str:
    """The URL without the middle link's tracking parameters or fragment."""
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _TRACKING.match(k)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def posting_link(url: str) -> str | None:
    """The cleaned URL when it names ONE posting, else `None`.

    Deliberately strict, and deliberately a closed rule: a careers homepage, a portal search page
    and a shortener landing are not application destinations. The false positives this test exists
    to refuse are ledger entries like `https://ars2.equest.com/` (a portal root) and
    `https://dsp.prng.co/jkRaQwb` (a short token with no posting shape).
    """
    if not url or any(char.isspace() for char in url):
        return None
    try:
        cleaned = _clean(url)
        parts = urlsplit(cleaned)
        _ = parts.port
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host or parts.scheme not in {"http", "https"} or parts.username or parts.password:
        return None
    if _NOT_EMPLOYER.search(host):
        return None
    if re.search(r"applicant_id|sessionid|jsessionid", parts.query, re.IGNORECASE):
        return None  # a session-bound link is dead for anybody else
    path = parts.path.rstrip("/").lower()
    if re.search(r"(^|&)pid=\d", parts.query) or (
        host.endswith(".recruitee.com") and path.startswith("/o/")
    ):
        return cleaned
    if path.rsplit("/", 1)[-1] in _GENERIC_ENDPOINTS and not re.search(r"\d", path + parts.query):
        return None
    has_id = bool(re.search(r"\d", path + parts.query))
    if not path or _GENERIC_PATH.fullmatch(path) or not (has_id or path.count("/") >= 3):
        return None
    return cleaned


@dataclass(frozen=True)
class OnDiskReport:
    """What the delivery-side step did, split by source so neither half hides the other."""

    ledger_considered: int = 0
    ledger_not_a_posting: int = 0
    ledger_written: int = 0
    ledger_dead: int = 0
    ledger_unknown: int = 0
    grnh_considered: int = 0
    grnh_written: int = 0
    grnh_dead: int = 0
    grnh_unknown: int = 0
    # A half that had candidates but no client to ask. Distinct from "found nothing": the runner
    # says so rather than printing a clean zero.
    ledger_unmeasured: bool = False
    grnh_unmeasured: bool = False


@dataclass(frozen=True)
class _LedgerCandidate:
    posting_id: int
    source_url: str
    url: str
    evidence_ref: str


@dataclass(frozen=True)
class _GrnhCandidate:
    posting_id: int
    source_url: str


@dataclass(frozen=True)
class _Write:
    posting_id: int
    source_url: str
    url: str
    evidence_ref: str


def _host(url: str) -> str:
    """The URL's lower-cased host, `""` for a value `urlsplit` refuses. Never raises: a stored
    posting URL is data, and one malformed row must not cost the whole step."""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _matches(host: str, entries: Sequence[str]) -> bool:
    return bool(host) and any(host == entry or host.endswith(f".{entry}") for entry in entries)


def _needs_an_employer_link(source_url: str, ledger_url: str, routes: ApplyRoutes) -> bool:
    """Whether this posting's own URL is a middle link the ledger entry can improve.

    Refused when the source is already a direct employer URL that disagrees with the ledger, for
    the reason job-apps' `swap_links` refuses it: an aged ledger entry must not replace a current
    direct link, and the caller cannot tell which is right. A marker-bearing company page counts
    as a middle link because the employer form is behind it.
    """
    config = routes.config
    if config is None:
        return False
    if _matches(_host(source_url), config.unresolved_hosts):
        return True
    if _matches(_host(source_url), config.native_fill_hosts):
        return True
    lowered = source_url.lower()
    if any(marker.lower() in lowered for marker in config.unresolved_url_markers):
        return True
    # The ledger entry naming the posting's own URL is not a replacement at all.
    return source_url == ledger_url


def _pending_postings(
    engine: Engine, posting_ids: Sequence[int]
) -> dict[int, str]:
    """The source URL of every requested posting with no destination row, read in chunks.

    `posting_ids` is the shortlist plus the standing queue (bounded by delivery, not the corpus),
    so a plain `IN` is safe here — the corpus-scaled hazard `store.param_chunks` exists for is the
    ranker's full read, not this one.
    """
    ids = sorted(set(posting_ids))
    if not ids:
        return {}
    with engine.connect() as conn:
        held = read_application_destinations(conn, ids)
        return {
            int(row.id): str(row.url)
            for row in conn.execute(
                select(postings.c.id, postings.c.url).where(postings.c.id.in_(ids))
            )
            if row.url and int(row.id) not in held
        }


def _split_candidates(
    source_urls: dict[int, str], routes: ApplyRoutes
) -> tuple[list[_LedgerCandidate], list[_GrnhCandidate]]:
    """The ledger and short-link candidates among postings with no destination."""
    ledger: list[_LedgerCandidate] = []
    grnh: list[_GrnhCandidate] = []
    for posting_id, source_url in sorted(source_urls.items()):
        host = _host(source_url)
        if host in _GRNH_HOSTS:
            grnh.append(_GrnhCandidate(posting_id=posting_id, source_url=source_url))
            continue
        link = routes.ledger_links.get(posting_id)
        if link is not None and _needs_an_employer_link(source_url, link.url, routes):
            ledger.append(
                _LedgerCandidate(
                    posting_id=posting_id,
                    source_url=source_url,
                    url=link.url,
                    evidence_ref=link.evidence_ref,
                )
            )
    return ledger, grnh


def _ledger_writes(
    candidates: Sequence[_LedgerCandidate],
    *,
    prober: LivenessProber,
) -> tuple[list[_Write], int, int, int, int]:
    """(writes, considered, not_a_posting, dead, unknown) for the ledger half.

    `alive` is the only verdict that writes. A `dead` link is reported and dropped; `unknown`
    (timeout, wall, 5xx) is kept out of both, because a failed check is not a negative result.
    """
    writes: list[_Write] = []
    not_a_posting = dead = unknown = 0
    for candidate in candidates:
        url = posting_link(candidate.url)
        if url is None:
            not_a_posting += 1
            continue
        verdict = prober(candidate.posting_id, url)
        if verdict.verdict == "alive":
            writes.append(
                _Write(
                    posting_id=candidate.posting_id,
                    source_url=candidate.source_url,
                    url=url,
                    evidence_ref=candidate.evidence_ref,
                )
            )
        elif verdict.verdict == "dead":
            dead += 1
        else:
            unknown += 1
    return writes, len(candidates), not_a_posting, dead, unknown


def _grnh_delivery_writes(
    candidates: Sequence[_GrnhCandidate], *, fetcher: Fetcher
) -> tuple[list[_Write], int, int, int]:
    """(writes, considered, dead, unknown) for the short links on postings being delivered.

    One GET with the resolver's own request shape and pacing, but read for the DESTINATION rather
    than for the board: `lanes/grnh_seeds.resolve` keeps a landing only when `parse_board_target`
    accepts it, and a destination must also accept the employer's own careers site (the measured
    HelloFresh link lands on `careers.hellofresh.com`, a real posting page and not a registered
    board). So the redirect target is classified by the same single-posting test the ledger half
    uses, and a gone-status from that target is DEAD while any other failure stays UNKNOWN.
    """
    writes: list[_Write] = []
    dead = unknown = 0
    for candidate in candidates:
        final_url = ""
        try:
            result = fetcher.get(
                candidate.source_url,
                headers={"User-Agent": identifying_user_agent()},
                min_host_delay=_GRNH_CRAWL_DELAY_SECONDS,
            )
        except FetchFailure as exc:
            if exc.status_code in GONE_STATUSES:
                dead += 1  # the redirect target answered gone: the posting is gone
            else:
                unknown += 1  # a wall, a timeout or a 5xx is not evidence the posting is gone
            continue
        except Exception:  # noqa: BLE001 - one short link must not cost the batch
            unknown += 1
            continue
        else:
            final_url = result.final_url or candidate.source_url
        url = posting_link(final_url)
        if url is None:
            # Landed on a homepage, an aggregator or the shortener itself. That is not a gone
            # status and not alive-as-a-posting, so it is UNKNOWN: the link says nothing about
            # whether the job is open.
            unknown += 1
            continue
        writes.append(
            _Write(
                posting_id=candidate.posting_id,
                source_url=candidate.source_url,
                url=url,
                evidence_ref=f"{EVIDENCE_GRNH_PREFIX}{candidate.posting_id}",
            )
        )
    return writes, len(candidates), dead, unknown


def _persist(engine: Engine, writes: Sequence[_Write], *, now: datetime) -> frozenset[int]:
    """Write the destinations and read them back; the readback is the verification, not the call.

    **No-clobber.** Every candidate was read before the network work began, and the other writer
    of this table (job-apps' Stop hook) takes no scan lease, so it can land a browser-verified
    destination in that window. The write therefore refuses to replace any existing row, and the
    readback confirms which URLs are actually stored: a row the other writer won is reported as
    not landed, never as overwritten.

    Returns the posting ids whose stored destination URL is the one written. A single transaction,
    after every probe has finished, so the write lock is held for the writes' own duration and not
    for a probe's.
    """
    if not writes:
        return frozenset()
    with engine.begin() as conn:
        for write in writes:
            try:
                record_application_destination(
                    conn,
                    posting_id=write.posting_id,
                    url=write.url,
                    source_url=write.source_url,
                    evidence_ref=write.evidence_ref,
                    verified_at=now,
                    only_if_absent=True,
                )
            except InvalidApplicationDestinationError:
                continue  # a URL the writer refuses is a report, not a crash
        stored = read_application_destinations(conn, [write.posting_id for write in writes])
    return frozenset(
        write.posting_id
        for write in writes
        if (found := stored.get(write.posting_id)) is not None and found.url == write.url
    )


def record_on_disk_links(
    engine: Engine,
    posting_ids: Sequence[int],
    *,
    routes: ApplyRoutes,
    prober: LivenessProber | None,
    fetcher: Fetcher | None,
    now: datetime,
) -> OnDiskReport:
    """Record the employer links this store already holds for the postings being delivered.

    `prober`/`fetcher` are the run's own clients, passed in rather than built here so that which
    hosts are asked is the caller's decision and no test reaches the network. `None` leaves that
    half UNMEASURED, never "nothing found": the report simply counts nothing for it and the runner
    says which half it skipped.
    """
    source_urls = _pending_postings(engine, posting_ids)
    if not source_urls:
        return OnDiskReport()
    ledger_candidates, grnh_candidates = _split_candidates(source_urls, routes)
    ledger_unmeasured = prober is None and bool(ledger_candidates)
    grnh_unmeasured = fetcher is None and bool(grnh_candidates)
    if prober is None:
        ledger_candidates = []
    if fetcher is None:
        grnh_candidates = []
    writes: list[_Write] = []
    ledger_considered = ledger_not_a_posting = ledger_dead = ledger_unknown = 0
    grnh_considered = grnh_dead = grnh_unknown = 0
    if prober is not None:
        ledger_writes, ledger_considered, ledger_not_a_posting, ledger_dead, ledger_unknown = (
            _ledger_writes(ledger_candidates, prober=prober)
        )
        writes += ledger_writes
    if fetcher is not None:
        grnh_writes, grnh_considered, grnh_dead, grnh_unknown = _grnh_delivery_writes(
            grnh_candidates, fetcher=fetcher
        )
        writes += grnh_writes
    stored = _persist(engine, writes, now=now)
    return OnDiskReport(
        ledger_considered=ledger_considered,
        ledger_not_a_posting=ledger_not_a_posting,
        ledger_written=sum(
            1
            for write in writes
            if write.posting_id in stored
            and not write.evidence_ref.startswith(EVIDENCE_GRNH_PREFIX)
        ),
        ledger_dead=ledger_dead,
        ledger_unknown=ledger_unknown,
        grnh_considered=grnh_considered,
        grnh_written=sum(
            1
            for write in writes
            if write.posting_id in stored and write.evidence_ref.startswith(EVIDENCE_GRNH_PREFIX)
        ),
        grnh_dead=grnh_dead,
        grnh_unknown=grnh_unknown,
        ledger_unmeasured=ledger_unmeasured,
        grnh_unmeasured=grnh_unmeasured,
    )


# ---------------------------------------------------------------------------------------------
# The `lane_seeds` short-link backlog: resolve, propose the boards for review, retire the seeds.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SeedOutcome:
    """One seed's turn: the board its redirect named, and whether the posting had since expired."""

    seed_id: int
    board: ResolvedBoard | None
    expired: bool


@dataclass(frozen=True)
class SeedDrainReport:
    """What one drain did. `selectable` is what the cap left behind, not what the queue holds."""

    selectable: int = 0
    followed: int = 0
    resolved: int = 0
    already_known: int = 0
    failed: int = 0
    proposed: int = 0
    candidates_path: Path | None = None
    problem: str | None = None


def follow_seeds(seeds: Sequence[LaneSeed], *, fetcher: Fetcher) -> tuple[SeedOutcome, ...]:
    """One follow per seed, with the existing resolver and no added concurrency."""
    outcomes: list[SeedOutcome] = []
    for seed in seeds:
        resolution = resolve((seed,), fetcher)
        outcomes.append(
            SeedOutcome(
                seed_id=seed.id,
                board=resolution.boards[0] if resolution.boards else None,
                expired=bool(resolution.census.from_expired_posting),
            )
        )
    return tuple(outcomes)


def _distinct_boards(outcomes: Sequence[SeedOutcome]) -> list[ResolvedBoard]:
    seen: set[tuple[str, str]] = set()
    boards: list[ResolvedBoard] = []
    for outcome in outcomes:
        board = outcome.board
        if board is None:
            continue
        key = (board.provider, board.slug.lower())
        if key in seen:
            continue
        seen.add(key)
        boards.append(board)
    return boards


def _existing_candidates(path: Path) -> list[dict[str, object]] | None:
    """The file's `companies:` rows, `[]` when there is no file, `None` when it cannot be read.

    `None` is deliberately distinct from `[]`: rewriting a file this process could not parse would
    discard the owner's edits, so the caller refuses to write instead.
    """
    if not path.exists():
        return []
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(loaded, dict):
        return None
    rows = loaded.get("companies")
    if not isinstance(rows, list):
        return None
    # A row whose shape this step cannot preserve makes the WHOLE file unreadable, rather than
    # being filtered out: filtering would rewrite the file without the owner's row.
    if not all(
        isinstance(row, dict)
        and isinstance(row.get("provider"), str)
        and isinstance(row.get("slug"), str)
        for row in rows
    ):
        return None
    return rows


def write_grnh_candidates(
    path: Path,
    boards: Sequence[ResolvedBoard],
    *,
    generated_on: str,
    selectable: int,
    followed: int,
    already_known: int,
    failed: int,
    expired: int,
) -> int:
    """Merge boards into the candidate file and return how many entries were ADDED.

    Merged rather than overwritten: a board proposed on an earlier run stays proposed until the
    owner imports or deletes it, which is what lets a resolved seed be retired without losing the
    board it bought.
    """
    existing = _existing_candidates(path)
    if existing is None:
        raise ValueError(f"{path} is not a candidate file this step can merge into")
    known_keys = {(str(row["provider"]), str(row["slug"]).lower()) for row in existing}
    added = 0
    for board in boards:
        key = (board.provider, board.slug.lower())
        if key in known_keys:
            continue
        known_keys.add(key)
        existing.append(
            {"name": board.slug, "provider": board.provider, "slug": board.slug, "tags": []}
        )
        added += 1
    payload = {"companies": existing}
    body: str = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    lines = [
        "# boardwatch grnh.se seed drain - candidate greenhouse boards, for review before import",
        "#",
        f"# generated {generated_on} by following grnh.se short links stored in `lane_seeds`.",
        "# Greenhouse's own shortener; the redirect target names the board.",
        "#",
        f"# seeds selectable {selectable} | followed this run {followed} "
        f"| failed {failed} | already watched {already_known}",
        f"# {expired} of the followed seeds named a posting that has since expired "
        "-- a live board, a dead requisition.",
        f"# {added} board(s) added this run; {len(existing) - added} carried from earlier runs.",
        "#",
        "# THE NAME IS THE SLUG. Nothing in a redirect carries the employer's display name.",
        "# Rename before importing. Arming a board costs scan time on every future run.",
        "#",
    ]
    if boards:
        lines.append("# Check each evidence URL names a real employer board, not ATS chrome:")
        lines += [
            f"#   {board.provider}:{one_line(board.slug)} | {one_line(board.final_url)}"
            for board in boards
        ]
        lines.append("#")
    # Atomic: a crash mid-write would leave a truncated file that later runs refuse to touch, and
    # the boards already resolved would be lost until the owner fixes it.
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text("\n".join(lines) + "\n" + body, encoding="utf-8")
    tmp.replace(path)
    return added


def _watched_boards(
    conn: Connection, boards: Sequence[ResolvedBoard]
) -> set[tuple[str, str]]:
    """The (provider, lower slug) pairs among `boards` that are already WATCHED.

    `company_exists` is the wrong test here: it says "stored, watched or not", and a lane-stored
    but unwatched board is exactly a board this file exists to propose — `companies import` watches
    an existing row. Excluding it would retire the seed while the board could never be armed.
    """
    keys: set[tuple[str, str]] = set()
    for board in boards:
        row = conn.execute(
            select(companies.c.id)
            .where(
                companies.c.provider == board.provider,
                func.lower(companies.c.slug) == board.slug.lower(),
                companies.c.watched.is_(True),
            )
            .limit(1)
        ).first()
        if row is not None:
            keys.add((board.provider, board.slug.lower()))
    return keys


def drain_grnh_seeds(
    engine: Engine,
    *,
    fetcher: Fetcher,
    run_id: int,
    now: datetime,
    data_dir: Path,
    limit: int = GRNH_DRAIN_LIMIT,
) -> SeedDrainReport:
    """Follow this run's share of the stored `grnh.se` backlog and retire what resolved.

    A seed is RETIRED when its redirect names a board (live or expired requisition), because the
    board itself is carried into the candidate file first; a seed whose link is dead or unreachable
    is charged an attempt and retires through the existing ceiling instead. That ordering is what
    makes the retirement honest: no seed leaves the queue before its board is on disk. If this
    reads the existing candidate file as unparseable it writes nothing and records no attempt, so
    the seeds stay selectable until the owner fixes the file.
    """
    with engine.connect() as conn:
        seeds = unresolved_seeds(
            conn,
            hosts=_GRNH_HOSTS,
            max_attempts=MAX_ATTEMPTS_CONSIDERED,
            limit=limit,
        )
        selectable = unresolved_seed_count(
            conn, hosts=_GRNH_HOSTS, max_attempts=MAX_ATTEMPTS_CONSIDERED
        )
    if not seeds:
        return SeedDrainReport(selectable=selectable)
    outcomes = follow_seeds(seeds, fetcher=fetcher)
    boards = _distinct_boards(outcomes)
    with engine.connect() as conn:
        watched_keys = _watched_boards(conn, boards)
    new_boards = [
        board for board in boards if (board.provider, board.slug.lower()) not in watched_keys
    ]
    already_known = len(boards) - len(new_boards)
    failed = sum(1 for outcome in outcomes if outcome.board is None)
    expired = sum(1 for outcome in outcomes if outcome.expired)
    path = data_dir / GRNH_CANDIDATE_FILENAME
    added = 0
    if new_boards:
        try:
            added = write_grnh_candidates(
                path,
                new_boards,
                generated_on=now.date().isoformat(),
                selectable=selectable,
                followed=len(outcomes),
                already_known=already_known,
                failed=failed,
                expired=expired,
            )
        except (OSError, ValueError) as exc:
            return SeedDrainReport(
                selectable=selectable,
                followed=len(outcomes),
                resolved=len(boards),
                already_known=already_known,
                failed=failed,
                problem=f"{path}: {exc}",
            )
    with engine.begin() as conn:
        for outcome in outcomes:
            record_seed_attempt(
                conn,
                outcome.seed_id,
                run_id=run_id,
                now=now,
                resolved=outcome.board is not None,
            )
    return SeedDrainReport(
        selectable=selectable,
        followed=len(outcomes),
        resolved=len(boards),
        already_known=already_known,
        failed=failed,
        proposed=added,
        candidates_path=path if new_boards else None,
    )
