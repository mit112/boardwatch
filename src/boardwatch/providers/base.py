"""Provider protocol (§3.3, amended by D22; BoardHealth amended by D27)."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any, Protocol

from boardwatch.core.models import BoardRequest, BoardSnapshot
from boardwatch.core.politeness import Fetcher, FetchFailure


class BoardHealth(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    DEAD = "dead"
    ERROR = "error"
    UNREACHABLE = "unreachable"  # D27: no HTTP response received (transport-level, after retries)


def health_from_failure(exc: FetchFailure, *, dead_status: int = 404) -> BoardHealth:
    """D27 mapping for a FetchFailure: status_code is None (transport) → UNREACHABLE;
    the provider dead signature → DEAD; any other HTTP error → ERROR. Parse failure of
    a 200 body is the provider's own concern (it maps to ERROR there), not this helper."""
    if exc.status_code is None:
        return BoardHealth.UNREACHABLE
    if exc.status_code == dead_status:
        return BoardHealth.DEAD
    return BoardHealth.ERROR


def count_listed_ids(rows: Iterable[Any], id_key: str) -> int:
    """`BoardSnapshot.board_enumerated` for a single-request provider: the number of DISTINCT
    posting ids the board listed this run.

    Counted off the RAW rows — before the detail budget truncates anything and before a
    per-row parse failure drops one — because the column exists so that
    `board_reported_total - board_enumerated` is a *listing* shortfall. `len(postings)` would
    make it a parse-failure count instead, and every provider would mean something different
    by the same persisted column (D-271).

    A row with no usable id is excluded rather than counted, which is what makes the live
    Mastercard case visible: SmartRecruiters reported 1129 and could only key 1128, and an
    id-less row is precisely a posting we cannot fetch, dedupe, or close.
    """
    return len(
        {
            str(row[id_key])
            for row in rows
            if isinstance(row, dict) and row.get(id_key) is not None
        }
    )


# Subdomain labels that name a CAREER SITE rather than an employer. CLOSED catalog: a host
# whose every label is in here derives NO employer name at all, rather than falling through to
# the next label along and returning a vendor's or a registrar's word for it.
_CAREER_SITE_LABELS = frozenset(
    {
        "apply", "career", "careers", "employment", "hire", "hiring", "job", "jobs", "join",
        "opportunities", "recruiting", "recruitment", "talent", "work", "www",
    }
)


def employer_label_from_host(host: str, *, vendor_suffixes: tuple[str, ...] = ()) -> str | None:
    """The employer's own token out of a board HOST, or None when the host does not name one.

    The rule is THE FIRST LABEL THAT IS NOT A CAREER-SITE WORD, after any of the provider's own
    vendor suffixes is removed and the host's public label is dropped. Deliberately not "the
    registrable domain": that needs the public suffix list, and without one `acme.co.uk` reads
    as `co`. Measured against every host shape
    in the registry, the first-label rule is right on all of them —
    `careers.qualcomm.com` -> `qualcomm`, `jobs.northropgrumman.com` -> `northropgrumman`,
    `acme.eightfold.ai` -> `acme`, `ngc.wd1.myworkdayjobs.com` -> `ngc`,
    `acme.fa.us2.oraclecloud.com` -> `acme` — and it is right on `acme.co.uk` too.

    NO CASE IS INVENTED. The token is returned exactly as the (already lowercased) host spells
    it, because any capitalization would be a guess: `northropgrumman` cannot be word-split
    without a dictionary, and a wrong display name is cosmetic while a wrong EMPLOYER name
    merges two companies' postings. `normalize_company` folds case anyway, so the casing has no
    effect on whether two rows for one employer group.

    None means "this host does not name an employer" — the caller must leave the existing name
    alone and REPORT it, never guess.
    """
    candidate = host.strip().lower().strip(".")
    vendor = next((s for s in vendor_suffixes if candidate.endswith(s)), None)
    if vendor is not None:
        # The suffix already carried the public part, so what remains is tenant labels only.
        labels = [label for label in candidate[: -len(vendor)].split(".") if label]
    else:
        labels = [label for label in candidate.split(".") if label]
        # Drop the public part. Only the LAST label, not a public-suffix lookup: one label is
        # what every registry host needs dropped, and dropping one too few leaves `acme.co.uk`
        # reading `acme` (right) while a PSL-less attempt at two would read `co.uk` as the whole
        # domain. What this buys is that `jobs.com` derives NOTHING instead of `com` — an
        # all-career-site host is reported, never guessed at.
        labels = labels[:-1] or labels
    for label in labels:
        if label not in _CAREER_SITE_LABELS:
            return label
    return None


class Provider(Protocol):
    name: str
    # public paste hostnames a user would enter; distinct from board_url()'s API host
    board_hosts: tuple[str, ...]

    def board_url(self, slug: str) -> str:
        """Canonical fetch URL == the http_cache key; stable parameter order."""
        ...

    def fetch_board(self, fetcher: Fetcher, request: BoardRequest) -> BoardSnapshot: ...

    def healthcheck(self, fetcher: Fetcher, slug: str) -> BoardHealth: ...
