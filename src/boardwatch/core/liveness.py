"""Is this posting still real? (P6 item 6.)

**Liveness is never cached; verdicts always are.** A verdict is a judgement about a frozen JD
and stays true as long as the JD does; liveness is a fact about the outside world at the moment
you ask, and a stored answer is wrong the instant the requisition closes. So nothing here writes
to the store, and in particular a `dead` result must never flip `postings.status` — that column
is the scanner's, derived from board-listing absence over `CLOSE_AFTER_MISSES` complete scans,
and a probe that overwrote it would let one 404 from a flaky CDN close a live posting for good.
A dead lead is dropped from the run that found it, and the next run asks again.

**Fail-open is the whole design.** The cost of treating a dead posting as alive is one wasted
résumé; the cost of treating a live posting as dead is a job Mit never sees and cannot know he
missed. Only an explicit gone-status earns `dead`. Everything else — a timeout, a refused
connection, a 403 from a bot-blocker, a 500, a redirect to a careers homepage, a posting with no
URL at all — is `unknown`, and `unknown` is served.

**What is deliberately NOT here: a closed-phrase catalog.** `PROGRAM.md` item 6 names "a saved
body containing a closed phrase" as the AUTHORITATIVE signal, inherited from job-apps, which
scraped HTML pages. boardwatch reads structured ATS APIs and every provider builds `body_text`
from the payload's description field alone (`greenhouse` `content`, `ashby` `descriptionHtml`,
`workable`/`workday` `description`/`jobDescription`, `lever`'s assembled sections,
`smartrecruiters` `_body_text`). Page chrome — the "this posting is no longer accepting
applications" banner — is structurally incapable of reaching that column. Measured against the
live corpus 2026-08-10, a nine-phrase candidate catalog matched 11 of 23,455 open postings and
**every one of the 11 was a false positive**: two Workday boilerplate conditionals ("If the job
posting is no longer available then all roles have been filled"), one location restriction ("we
are not accepting applications of candidates outside of New York"), and eight job descriptions
for roles that handle purchase requisitions. Shipping that catalog as authoritative would have
suppressed 11 live leads to catch none. Re-derive it with:

    sqlite3 "file:$DB?mode=ro" "select count(*) from postings where status='open'
      and lower(body_text) like '%no longer accepting%'"   -- and the other eight phrases

Where a provider offers its own liveness flag the authoritative signal already exists and is
already used: `providers/smartrecruiters.py` drops a posting whose detail payload says
`active is False`. That is what "authoritative" looks like on an API corpus.
"""

from __future__ import annotations

from dataclasses import dataclass

# Closed and ordered by confidence. `dead` is the only verdict that withholds a lead, and only
# an explicit gone-status produces it (see SIGNALS). Adding a verdict is a catalog edit, never a
# bucket invented at a call site.
VERDICTS: tuple[str, ...] = ("alive", "dead", "unknown")

# Closed catalog of why. Typed at the decision site so nothing downstream classifies a liveness
# outcome by string-matching a message.
SIGNALS: tuple[str, ...] = (
    "refetch_gone",  # the only signal that yields `dead`
    "refetch_ok",
    "refetch_error",
    "no_url",
    "not_probed",
)

# HTTP statuses that mean the resource is gone, as opposed to merely unavailable to us.
# 404 and 410 ONLY. Not 403: measured 2026-08-10, `pinterestcareers.com` answers 403 to an
# unfamiliar user agent for a posting that is perfectly live, so treating it as gone would
# silently blacklist whole employers. Not 5xx: a server having a bad minute says nothing about
# the requisition.
GONE_STATUSES = frozenset({404, 410})


class UnknownLivenessVerdict(Exception):
    """Raised at the decision site, so a bad verdict can never be recovered by string-match."""

    def __init__(self, verdict: str) -> None:
        super().__init__(f"{verdict!r} is not a liveness verdict")
        self.verdict = verdict


@dataclass(frozen=True)
class Liveness:
    """One posting's liveness at one instant. Carries no timestamp on purpose — a timestamp
    invites somebody to store it, and a stored liveness is the thing this module exists to
    prevent."""

    posting_id: int
    verdict: str
    signal: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise UnknownLivenessVerdict(self.verdict)
        if self.signal not in SIGNALS:
            raise UnknownLivenessVerdict(self.signal)

    @property
    def withholds(self) -> bool:
        """Whether this result keeps the lead off the list. Exactly one verdict does."""
        return self.verdict == "dead"


def verdict_for_status(posting_id: int, status_code: int) -> Liveness:
    """Classify a completed re-fetch. `GONE_STATUSES` is the only path to `dead`."""
    if status_code in GONE_STATUSES:
        return Liveness(
            posting_id=posting_id,
            verdict="dead",
            signal="refetch_gone",
            detail=f"HTTP {status_code}",
        )
    return Liveness(
        posting_id=posting_id,
        verdict="alive",
        signal="refetch_ok",
        detail=f"HTTP {status_code}",
    )


def verdict_for_failure(posting_id: int, status_code: int | None, detail: str) -> Liveness:
    """Classify a re-fetch that raised. A gone-status still counts — the Fetcher raises
    `FetchFailure` for every non-200, so a 404 arrives here rather than through
    `verdict_for_status`, and reading only the happy path would make the probe find nothing."""
    if status_code is not None and status_code in GONE_STATUSES:
        return Liveness(
            posting_id=posting_id,
            verdict="dead",
            signal="refetch_gone",
            detail=f"HTTP {status_code}",
        )
    return Liveness(
        posting_id=posting_id, verdict="unknown", signal="refetch_error", detail=detail
    )


def verdict_without_url(posting_id: int) -> Liveness:
    """`postings.url` is nullable. Nothing to ask, so nothing is claimed."""
    return Liveness(posting_id=posting_id, verdict="unknown", signal="no_url")


__all__ = [
    "GONE_STATUSES",
    "SIGNALS",
    "VERDICTS",
    "Liveness",
    "UnknownLivenessVerdict",
    "verdict_for_failure",
    "verdict_for_status",
    "verdict_without_url",
]
