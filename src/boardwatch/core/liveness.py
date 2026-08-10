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

**"Explicit" means the stored URL itself answered gone, not something it was redirected to.**
`Fetcher` is built with `follow_redirects=True`, so a 404 can arrive from a *different* resource
than the one asked about: an employer migrating ATS points old links at a new host whose
deep-link path 404s while the requisition is live at the new URL, and the chain reports a bare
404 with no trace of the hop. Classifying that as `dead` would withhold live leads — the exact
failure this module exists to prevent — so a gone-status reached through a redirect is
`unknown`, under its own signal so the case stays auditable rather than merging into the
transport-error bucket. A redirect that ends in success needs no special handling: it is served
either way.

**What is deliberately NOT here: a closed-phrase catalog.** `PROGRAM.md` item 6 names "a saved
body containing a closed phrase" as the AUTHORITATIVE signal, inherited from job-apps, which
scraped HTML pages. boardwatch reads structured ATS APIs, and every provider assembles
`body_text` **only from employer-authored description fields of a JSON payload** — one field for
greenhouse (`content`), ashby (`descriptionHtml`), workable and workday; two joined for lever
(`descriptionPlain` + `additionalPlain`); three for smartrecruiters (`jobDescription`,
`qualifications`, `additionalInformation`). No provider ever sees the rendered careers page, so
page chrome — the "this posting is no longer accepting applications" banner a scraper would
read — is structurally incapable of reaching that column.

What *can* reach it is an employer writing closure-shaped prose inside the JD, and that is
exactly what the measurement found. Against the live corpus 2026-08-10 a nine-phrase candidate
catalog matched 11 of 23,455 open postings and **every one of the 11 was a false positive**: two
Workday boilerplate conditionals ("If the job posting is no longer available then all roles have
been filled"), one location restriction ("we are not accepting applications of candidates
outside of New York"), and eight job descriptions for roles that handle purchase requisitions.
Shipping that catalog as authoritative would have suppressed 11 live leads to catch none.
Re-derive it with:

    sqlite3 "file:$DB?mode=ro" "select count(*) from postings where status='open'
      and lower(body_text) like '%no longer accepting%'"   -- and the other eight phrases

One provider does expose a native liveness flag: `providers/smartrecruiters.py` drops a posting
whose detail payload says `active is False`. That is what "authoritative" would look like on an
API corpus — but it is **not** coverage for this gate, and the difference matters. It fetches
detail payloads only for postings NOT already in the store, and only within `detail_fetch_budget`,
so for the entire population liveness is about — postings already stored and being ranked — the
flag is never re-read. It is a first-discovery filter on 1 of 6 providers, not a liveness check.
"""

from __future__ import annotations

from dataclasses import dataclass

# Closed and ordered by confidence. `dead` is the only verdict that withholds a lead, and only
# an explicit gone-status produces it (see SIGNALS). Adding a verdict is a catalog edit, never a
# bucket invented at a call site.
VERDICTS: tuple[str, ...] = ("alive", "dead", "unknown")

# Closed catalog of why. Typed at the decision site so nothing downstream classifies a liveness
# outcome by string-matching a message.
# A run that was not probed produces no `Liveness` at all — the pipeline reports it through
# `checked is None`, so there is deliberately no `not_probed` member here. A catalog entry
# nothing emits is a bucket that cannot be audited.
SIGNALS: tuple[str, ...] = (
    "refetch_gone",  # the only signal that yields `dead`
    "refetch_gone_after_redirect",  # gone, but a different URL said so — served
    "refetch_ok",
    "refetch_error",
    "no_url",
)

# Which verdict each signal carries. The pair is fully determined, so an inconsistent
# combination is a construction bug, not a state the rest of the system should have to handle:
# `Liveness(1, "dead", "refetch_error")` would otherwise build happily and withhold a timed-out
# posting, silently inverting the fail-open direction with every catalog membership check
# passing. Enforced in `__post_init__` for that reason.
SIGNAL_VERDICTS: dict[str, str] = {
    "refetch_gone": "dead",
    "refetch_gone_after_redirect": "unknown",
    "refetch_ok": "alive",
    "refetch_error": "unknown",
    "no_url": "unknown",
}

# HTTP statuses that mean the resource is gone, as opposed to merely unavailable to us.
# 404 and 410 ONLY. Not 403: measured 2026-08-10, `pinterestcareers.com` answers 403 to an
# unfamiliar user agent for a posting that is perfectly live, so treating it as gone would
# silently blacklist whole employers. Not 5xx: a server having a bad minute says nothing about
# the requisition.
GONE_STATUSES = frozenset({404, 410})


class UnknownLivenessVerdict(Exception):
    """Raised at the construction site, so a bad value is never recovered by string-match.

    One class, two fields, and the message names which one is wrong: a caller that catches this
    can ask, and a human reading a traceback is not told "not a verdict" about a bad signal.
    """

    def __init__(self, *, verdict: str | None = None, signal: str | None = None) -> None:
        bad = f"verdict {verdict!r}" if verdict is not None else f"signal {signal!r}"
        super().__init__(f"{bad} is not in the liveness catalog")
        self.verdict = verdict
        self.signal = signal


class ContradictoryLiveness(Exception):
    """Both fields are in the catalog, but they disagree — a distinct fault from an unknown one.

    Its own class rather than a third mode of `UnknownLivenessVerdict`, because the two need
    different answers: an unknown value means the catalog is missing an entry, a contradictory
    pair means a call site built a verdict the catalog never sanctions. Carries both fields plus
    the one the signal mandates, so a traceback says what it should have been.
    """

    def __init__(self, *, verdict: str, signal: str, expected: str) -> None:
        super().__init__(f"signal {signal!r} carries verdict {expected!r}, not {verdict!r}")
        self.verdict = verdict
        self.signal = signal
        self.expected = expected


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
            raise UnknownLivenessVerdict(verdict=self.verdict)
        if self.signal not in SIGNALS:
            raise UnknownLivenessVerdict(signal=self.signal)
        expected = SIGNAL_VERDICTS[self.signal]
        if self.verdict != expected:
            raise ContradictoryLiveness(
                verdict=self.verdict, signal=self.signal, expected=expected
            )

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


def verdict_for_failure(
    posting_id: int, status_code: int | None, detail: str, *, redirected: bool = False
) -> Liveness:
    """Classify a re-fetch that raised. A gone-status still counts — the Fetcher raises
    `FetchFailure` for every non-200, so a 404 arrives here rather than through
    `verdict_for_status`, and reading only the happy path would make the probe find nothing.

    `redirected` says whether the gone-status came from the URL that was asked about or from
    somewhere it was sent. Only the former withholds; see the module docstring. It is keyword-only
    and defaults to False so that a caller which cannot know defaults to the *stricter* reading of
    its own evidence rather than being handed a fail-open it never established.
    """
    if status_code is not None and status_code in GONE_STATUSES:
        # The caller's detail is kept, not replaced by a bare "HTTP 404": the `FetchFailure`
        # message carries the URL, and withholding a lead is the one outcome whose reason
        # somebody will want to check by hand.
        if redirected:
            return Liveness(
                posting_id=posting_id,
                verdict="unknown",
                signal="refetch_gone_after_redirect",
                detail=detail,
            )
        return Liveness(
            posting_id=posting_id, verdict="dead", signal="refetch_gone", detail=detail
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
    "SIGNAL_VERDICTS",
    "VERDICTS",
    "ContradictoryLiveness",
    "Liveness",
    "UnknownLivenessVerdict",
    "verdict_for_failure",
    "verdict_for_status",
    "verdict_without_url",
]
