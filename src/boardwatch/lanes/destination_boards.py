"""Propose company boards from the store's verified application destinations (D-692).

Every application destination the owner's browser workflow verified points at one job on some ATS.
When that URL parses to a supported provider and board, it names an employer board the store may
never have watched: resolving such a link once should make the employer's postings arrive by the
direct board scan from then on, instead of the employer needing resolution again for every wrapper.

This is a DISCOVERY source, so it watches nothing. It emits the registry format `companies import`
reads, behind a header carrying what it excluded, and the owner reviews that file. Two
false-candidate classes are refused here:

* ATS chrome — the slug ATS's own furniture parses to (`greenhouse:embed` from
  `/embed/job_app?for=<slug>&token=...`, `greenhouse:api`, `smartrecruiters:oneclick-ui`, ...).
  The catalog is `lanes/common_crawl.ATS_CHROME`, reused rather than re-spelled: it is the same
  closed list the Common Crawl discovery already refuses as "not an employer".
* a workday slug VARIANT of an already-watched tenant — the same `{host}/{tenant}` with a different
  career-site segment or case (`.../hpe/Jobsathpe` beside a watched `.../hpe/acjobsite`), or the
  unsliced board beside a watched facet slice. This is tenant-level BY THE PLAN'S RULING: the
  repo's own measurements also show one tenant can hold genuinely distinct career sites
  (`bmo/External` + `bmo/campus`), so a distinct unwatched site of a watched tenant is a KNOWN GAP
  here — the owner can still add it by hand.

No I/O: the caller supplies the destination rows and the watched sets it already read.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date

from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.lanes.common_crawl import ATS_CHROME
from boardwatch.lanes.github_lists import BoardCandidate, one_line, registry_yaml_for
from boardwatch.providers.registry import derive_employer_name


@dataclass(frozen=True)
class DestinationBoard:
    """One board a verified destination names, with the posting's own URL as evidence."""

    provider: str
    slug: str
    name: str
    evidence_posting_id: int
    evidence_url: str
    # How many DISTINCT postings' destinations named this board. One is normal.
    postings: int


@dataclass(frozen=True)
class DestinationCensus:
    """What the read covered, so an unparsed majority is never read as "nothing to find"."""

    destinations: int
    parsed: int
    unparsed: int
    already_watched: int
    false_candidates: int
    workday_variants: int
    boards: int

    def lines(self) -> list[str]:
        return [
            f"# destinations read {self.destinations} | parsed to a board {self.parsed} "
            f"| not a board URL {self.unparsed}",
            f"# already watched {self.already_watched} | ATS chrome {self.false_candidates} "
            f"| same workday tenant as a watched board {self.workday_variants}",
            f"# proposed {self.boards}",
        ]


def workday_tenant(slug: str) -> tuple[str, str] | None:
    """`(host, tenant)` from a workday `host/tenant/site` (a facet is ignored), else None.

    The tenant is the employer identity (`providers/workday.py` reads it the same way); the career
    site is one tenant's label for a candidate experience, so two site spellings are one employer.
    """
    head, _, rest = slug.partition("/")
    tenant, _, site = rest.partition("/")
    if not head or not tenant or not site:
        return None
    return head.lower(), tenant.lower()


def _board_of(url: str) -> tuple[str, str] | None:
    try:
        return parse_board_target(url)
    except (UnknownBoardURL, ValueError):
        return None


def candidate_boards(
    destinations: Sequence[tuple[int, str]],
    *,
    watched: Collection[tuple[str, str]],
    watched_workday_tenants: Collection[tuple[str, str]],
) -> tuple[tuple[DestinationBoard, ...], DestinationCensus]:
    """`(boards, census)`: the unwatched boards those destinations name, deduplicated.

    `watched` holds `(provider, lower-cased slug)` pairs; `watched_workday_tenants` holds
    `(lower host, lower tenant)` pairs for every watched workday board. The caller reads both,
    because this module does no I/O.
    """
    parsed = unparsed = already_watched = false_candidates = variants = 0
    by_key: dict[tuple[str, str], DestinationBoard] = {}
    for posting_id, url in destinations:
        provider_slug = _board_of(url)
        if provider_slug is None:
            unparsed += 1
            continue
        parsed += 1
        provider, slug = provider_slug
        key = (provider, slug.lower())
        if slug.lower() in ATS_CHROME:
            false_candidates += 1
            continue
        if key in watched:
            already_watched += 1
            continue
        if provider == "workday":
            tenant = workday_tenant(slug)
            if tenant is not None and tenant in watched_workday_tenants:
                variants += 1
                continue
        name = derive_employer_name(provider, slug) or slug
        if key in by_key:
            by_key[key] = DestinationBoard(
                provider=provider,
                slug=slug,
                name=name,
                evidence_posting_id=by_key[key].evidence_posting_id,
                evidence_url=by_key[key].evidence_url,
                postings=by_key[key].postings + 1,
            )
        else:
            by_key[key] = DestinationBoard(
                provider=provider,
                slug=slug,
                name=name,
                evidence_posting_id=posting_id,
                evidence_url=url,
                postings=1,
            )
    boards = tuple(by_key[key] for key in sorted(by_key))
    census = DestinationCensus(
        destinations=len(destinations),
        parsed=parsed,
        unparsed=unparsed,
        already_watched=already_watched,
        false_candidates=false_candidates,
        workday_variants=variants,
        boards=len(boards),
    )
    return boards, census


def candidate_document(
    boards: Sequence[DestinationBoard], *, census: DestinationCensus, generated_on: date
) -> str:
    """The registry-format file `companies import` accepts, behind a reviewable header.

    The header is comments, which `yaml.safe_load` ignores; per-entry provenance cannot be a field
    because `CompanyEntry` forbids extras.
    """
    lines = [
        "# boardwatch companies discover-destinations - boards named by verified application links",
        "#",
        f"# generated {generated_on.isoformat()} from `application_destinations`, the links a",
        "# browser check verified. A board here is one an employer's own posting link named;",
        "# nothing is watched by this command.",
        "#",
        *census.lines(),
        "#",
        "# Check each evidence URL names a real employer board and not ATS chrome:",
    ]
    lines += [
        f"#   {board.provider}:{one_line(board.slug)} | {one_line(board.name)} "
        f"| {board.postings} posting(s) | {one_line(board.evidence_url)}"
        for board in boards
    ]
    if not boards:
        lines.append("# No new boards. Nothing to import.")
    lines.append("")
    candidates = [
        BoardCandidate(
            provider=board.provider,
            slug=board.slug,
            name=board.name,
            evidence_url=board.evidence_url,
            records=board.postings,
        )
        for board in boards
    ]
    return "\n".join(lines) + registry_yaml_for(candidates)
