"""Resolve `grnh.se` short links to the greenhouse boards behind them, for review (D-428).

One request shape, and no others:

    GET https://grnh.se/<token>     -- follow the redirect, read WHERE IT LANDED

No key, no cookie, no TLS bypass, no app impersonation, and the `identifying_user_agent()` D22
owes any host that answers us honestly.

WHY THE PREMISE IS MEASURED RATHER THAN ASSUMED. 12 stored seeds were sampled live on
2026-09-02: **12 of 12 followed their redirect to a URL `parse_board_target` accepts** (0 misses,
0 errors), yielding **9 distinct greenhouse boards** -- ~1.3 seeds per board, so the 122 stored
seeds are roughly 90 boards. **0 of the 9 were already watched and 6 were absent from `companies`
entirely**, so this is board-fleet GROWTH, not re-discovery. `parse_board_target` already accepts
`boards.greenhouse.io/<slug>` and `job-boards.greenhouse.io/<slug>`, so the landing spot exists
and NO new ATS adapter is needed.

THIS IS NOT A `Lane`, and the difference is structural rather than a naming preference -- the
same reason `lanes/github_lists.py` is not one. A lane returns `LaneResult`: postings plus an
`AcquisitionTally`. This returns neither. A `grnh.se` link resolves to a BOARD, and a board is a
company-discovery deliverable, not a posting one. It is deliberately absent from
`pipeline.runner.LANE_FACTORIES`, so it costs a run NOTHING until an operator invokes it.

IT WRITES NOTHING -- not the store, not `watched`, not `lane_seeds`. The owner's ruling (D-291
build, decision 2) is that a human sits between a discovered slug and what the machine watches,
because a bad slug becomes a permanently failing board and there is no quarantine and no backoff
for one. So this emits a registry-format candidate file and `companies import` -- unchanged, and
still the only sanctioned watched-write -- executes the file a human read.

THE SEED ROWS ARE LEFT UNRESOLVED, DELIBERATELY, and this is the module's one honest debt.
Marking `resolved_at` here would claim the seed became a posting, which is false: it became a
board CANDIDATE that a human may yet delete. The rows stay selectable so that a future in-run
resolver -- or a re-run of this command -- still sees them. **The consequence, stated rather than
discovered later: `boardwatch seeds` keeps reporting these 122 as claimed by nothing, and that
stays TRUE of the automated pipeline, which is what that report measures.**

THIS MODULE DOES NOT DECLARE `SEED_HOSTS`, and the omission is deliberate rather than an
oversight. `reports/seed_claims.py` maps a LANE NAME to the catalog it drains DURING A RUN, and
`tests/unit/test_seed_claims.py` fails any `boardwatch.lanes` module that declares `SEED_HOSTS`
without registering there. Declaring it would register a resolver that no run ever calls, and the
report would then count these seeds as claimable -- taking the leak's worst case and printing it
as the healthy half, which is the exact inversion D-426 built that report to prevent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

import yaml

from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.core.politeness import Fetcher, FetchFailure, identifying_user_agent
from boardwatch.store.seed_queries import LaneSeed

# `grnh.se` is Greenhouse's own shortener and gives every link the same bare host, so an exact
# host set is the whole catalog -- there is no tenant subdomain to match a suffix against.
GRNH_HOSTS = frozenset({"grnh.se"})

# Greenhouse's shortener is a redirect service, not a board: it answers fast and holds no
# per-tenant load. The floor `Fetcher` already applies per host is the pacing that matters.
_CRAWL_DELAY_SECONDS = 1.0

# Mirrors the ceiling an in-run resolver charges against a seed. Nothing here charges an attempt
# -- this command writes nothing -- but a seed some future resolver has already exhausted should
# not be proposed here forever, so the same bound selects what is still worth following.
MAX_ATTEMPTS_CONSIDERED = 3


def _board_of(url: str) -> tuple[str, str] | None:
    """`(provider, slug)` if this URL names a board boardwatch serves, else None.

    One spelling of the parse, because it is now reached from BOTH the 200 path and the
    failed-response path and two copies would let those two disagree about what a board is.
    """
    if not url:
        return None
    try:
        provider, slug = parse_board_target(url)
    except (UnknownBoardURL, ValueError):
        return None
    return provider, slug


@dataclass(frozen=True)
class ResolvedBoard:
    """One seed that landed on a board `parse_board_target` accepts."""

    provider: str
    slug: str
    seed_url: str
    final_url: str


@dataclass(frozen=True)
class GrnhCensus:
    """What the pass actually did, in the four outcomes that can happen.

    Reported in full rather than as a success count, because the three non-success rows are the
    ones that would justify abandoning the lever, and a bare "N boards found" hides them.

    The outcomes are disjoint and exhaustive: every seed read lands in exactly one of `resolved`,
    `duplicate`, `off_board` and `failed`. `duplicate` exists because ~1.3 seeds share one board,
    so without it a 122-seed pass reports 90 boards and 32 seeds accounted for by nothing.
    """

    seeds_read: int
    resolved: int
    duplicate: int
    off_board: int
    failed: int
    # A SUBSET of `resolved`, reported separately and deliberately NOT part of the sum below: a
    # board named by a redirect whose posting has since 404'd. It is a real board and a dead
    # requisition, and collapsing the two would make an aged backlog look like a dead lane.
    from_expired_posting: int = 0
    # A SUBSET of `resolved` that the caller dropped because `companies` already holds it. Also
    # outside the sum: the seed WAS resolved, it just buys nothing.
    already_stored: int = 0

    def reconciles(self) -> bool:
        """`seeds_read` must equal the four disjoint outcomes. Pinned by the suite.

        A seed that falls into none of them is a silent loss, and the header's job is to let a
        reviewer notice exactly that.
        """
        return self.seeds_read == self.resolved + self.duplicate + self.off_board + self.failed


@dataclass(frozen=True)
class GrnhResolution:
    boards: tuple[ResolvedBoard, ...]
    census: GrnhCensus
    errors: tuple[str, ...]


def resolve(seeds: tuple[LaneSeed, ...], fetcher: Fetcher) -> GrnhResolution:
    """Follow each seed's redirect and keep the ones that land on a parseable board.

    **This function does not raise.** One dead short link must not discard the boards already
    resolved in the same pass -- the same isolation `lanes/jsonld.py` applies per seed, and for
    the same reason. A typed `FetchFailure` is counted as `failed`; any OTHER exception is
    additionally carried out in `errors`, because that is a code defect and folding it into a
    content outcome would disguise it as "the link went somewhere we do not serve".
    """
    boards: list[ResolvedBoard] = []
    errors: list[str] = []
    off_board = failed = duplicate = expired = 0
    seen: set[tuple[str, str]] = set()

    for seed in seeds:
        try:
            try:
                result = fetcher.get(
                    seed.url,
                    headers={"User-Agent": identifying_user_agent()},
                    min_host_delay=_CRAWL_DELAY_SECONDS,
                )
            except FetchFailure as exc:
                # A redirect target that answers 404/403/410 has ALREADY NAMED ITS BOARD in the
                # `Location` it was reached through, and an aged seed backlog is mostly expired
                # requisitions — the Indeed lane discovers a posting, the employer closes it, the
                # seed is followed weeks later. Discarding those would throw away exactly the
                # boards this command exists to find and report them as dead short links. The
                # board is kept; the dead requisition is counted separately.
                board = _board_of(exc.final_url)
                if board is None:
                    failed += 1
                    continue
                provider, slug = board
                key = (provider, slug.lower())
                if key in seen:
                    duplicate += 1
                    continue
                seen.add(key)
                expired += 1
                boards.append(
                    ResolvedBoard(
                        provider=provider, slug=slug, seed_url=seed.url, final_url=exc.final_url
                    )
                )
                continue
            # The REQUESTED url is `grnh.se/<token>`; only the FINAL one names the board. Reading
            # `seed.url` here would parse the shortener forever and resolve nothing.
            final = result.final_url
            # Empty means a 304 -- the ONLY construction that leaves it unset. A shortener that
            # answers 200 without moving is a different case and falls through with `final ==
            # seed.url`, which `parse_board_target` refuses on the `grnh.se` host.
            board = _board_of(final)
            if board is None:
                off_board += 1
                continue
            provider, slug = board
            # ~1.3 seeds share one board, so without this the list proposes the same board four
            # times (`speechify` carried 4 of the 12 sampled seeds).
            #
            # `.lower()` is LOAD-BEARING, not belt-and-braces: `GreenhouseProvider` declares no
            # `normalize_slug`, so `parse_board_target` returns the path segment VERBATIM. Two
            # seeds reaching `/Speechify/` and `/speechify/` are one board, and emitting both
            # would import as two companies against a `(provider, slug)` unique index.
            key = (provider, slug.lower())
            if key in seen:
                duplicate += 1
                continue
            seen.add(key)
            boards.append(
                ResolvedBoard(provider=provider, slug=slug, seed_url=seed.url, final_url=final)
            )
        except Exception as exc:  # noqa: BLE001 - one crashing seed must not discard the pass
            errors.append(f"{seed.url}: {exc!r}")
            failed += 1

    return GrnhResolution(
        boards=tuple(boards),
        census=GrnhCensus(
            seeds_read=len(seeds),
            resolved=len(boards),
            duplicate=duplicate,
            off_board=off_board,
            failed=failed,
            from_expired_posting=expired,
        ),
        errors=tuple(errors),
    )


def without_known(
    resolution: GrnhResolution, *, is_known: Callable[[str, str], bool]
) -> GrnhResolution:
    """Drop boards `companies` already holds, and record how many.

    Separate from `resolve` because that function touches no store and must stay that way; the
    caller owns the connection. The census keeps `resolved` at what was RESOLVED and reports the
    drop alongside, so the file never implies the seeds themselves went nowhere.
    """
    kept = tuple(b for b in resolution.boards if not is_known(b.provider, b.slug))
    dropped = len(resolution.boards) - len(kept)
    return GrnhResolution(
        boards=kept,
        census=replace(resolution.census, already_stored=dropped),
        errors=resolution.errors,
    )


def candidate_document(resolution: GrnhResolution, *, generated_on: date) -> str:
    """The registry-format file `companies import` accepts, behind a reviewable header.

    The header is comments, which `yaml.safe_load` ignores, and that is the only place the
    provenance can go: `CompanyEntry` sets `extra="forbid"`, so a per-entry `seed_url` field
    would fail the very validator the file has to pass. The owner reviews this file away from the
    terminal that produced it, so what it excluded has to travel with it.
    """
    payload = {
        "companies": [
            {"name": b.slug, "provider": b.provider, "slug": b.slug, "tags": []}
            for b in resolution.boards
        ]
    }
    # `safe_dump` quotes any scalar whose plain form would resolve to something else, so a board
    # named `no`, `123` or `~` survives the round trip through `safe_load`.
    body: str = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return _header(resolution, generated_on) + body


def _one_line(value: str) -> str:
    """Collapse anything that could break out of a one-line `#` comment.

    A slug or URL reaches this file from a redirect target, so it is remote input: a newline in
    it would end the comment and let the rest be parsed as YAML.
    """
    return " ".join(value.split())


def _header(resolution: GrnhResolution, generated_on: date) -> str:
    c = resolution.census
    lines = [
        "# boardwatch seeds resolve - candidate greenhouse boards, for review before import",
        "#",
        f"# generated {generated_on.isoformat()} by following grnh.se short links stored in",
        "# `lane_seeds`. Greenhouse's own shortener; the redirect target is the board.",
        "#",
        f"# seeds read {c.seeds_read} | distinct boards {c.resolved} "
        f"| same board again {c.duplicate} | landed off-board {c.off_board} "
        f"| fetch failed {c.failed}",
        f"# of the boards, {c.from_expired_posting} were named by a posting that has since "
        "expired -- a live board, a dead requisition.",
        f"# already watched or stored, so dropped from this file: {c.already_stored}",
        "#",
        "# THE NAME IS THE SLUG. Nothing in a redirect carries the employer's display name, and",
        "# inventing one would put an unsourced string in the registry. Rename before importing.",
        "#",
        "# ARMING THIS COSTS RUN TIME FOREVER: ~3.2s per board on EVERY future run once watched.",
        "# Delete any row you do not want before `companies import`.",
        "#",
    ]
    if resolution.boards:
        # The evidence URL is not decoration: it is the only thing that makes a bad slug
        # refusable at a glance, and greenhouse HAS a live one -- `boards.greenhouse.io/embed/
        # job_app?token=<n>` parses to the board `embed`. `greenhouse:embed` beside that URL is
        # obviously ATS chrome; `greenhouse:embed` on its own is not. Not filtered here for the
        # same reason `lanes/github_lists.py` does not filter it: a suppression list is a guess
        # about which slugs are chrome, and the human step already exists.
        lines.append("# Check each evidence URL names a real employer board and not ATS chrome:")
        lines += [
            f"#   {b.provider}:{_one_line(b.slug)} | {_one_line(b.final_url)}"
            for b in resolution.boards
        ]
        lines.append("#")
    else:
        lines += ["# No boards resolved. Nothing to import.", "#"]
    if resolution.errors:
        lines += ["# ERRORS (a code defect, not a dead link):"]
        # `_one_line` here too: an exception's `repr` is the one value in this header that is not
        # a URL the seed writer already refused whitespace in.
        lines += [f"#   {_one_line(e)}" for e in resolution.errors[:10]]
        if len(resolution.errors) > 10:
            lines += [f"#   ... and {len(resolution.errors) - 10} more"]
        lines += ["#"]
    return "\n".join(lines) + "\n"
