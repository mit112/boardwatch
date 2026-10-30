"""Is this posting still real? (P6 item 6.)

**Liveness is never cached; verdicts always are.** A verdict is a judgement about a frozen JD
and stays true as long as the JD does; liveness is a fact about the outside world at the moment
you ask, and a stored answer is wrong the instant the requisition closes. So nothing here writes
to the store, and a `dead` result does not flip `postings.status` for a posting the scanner can
reach — that column is the scanner's, derived from board-listing absence over
`CLOSE_AFTER_MISSES` complete scans, and a probe that overwrote it would let one 404 from a
flaky CDN close a live posting for good. A dead lead is dropped from the run that found it, and
the next run asks again.

**That contract is NARROWED, not repealed, by D-325, and the narrowing is exactly one clause
wide.** It rested on a premise that is false for part of the corpus: that `postings.status` has
a working owner. For a posting whose company is `watched = 0` it does not. `_process_missing`
(`scan/apply.py`) is the only writer of `status='closed'`, it runs on `complete` snapshots only,
`lanes/base.py::lane_snapshot` is always `partial`, and an unwatched company is never revisited
by the scan coordinator — so those rows are open for ever and "still open" is indistinguishable
from "unverifiable" (D-314). A lane re-acquires by SEARCH, so absence can never be evidence for
them either; age-based and missed-run closing were both measured and rejected.

So for `watched = 0` postings, and ONLY those, a `refetch_gone` — never
`refetch_gone_after_redirect`, never `refetch_error` — is allowed to increment a strike counter
of its own (`postings.death_strikes`, never `consecutive_missing`), and two strikes in different
runs close the posting. That mirrors `CLOSE_AFTER_MISSES = 2` exactly, and an `alive` probe or
any positive listing clears the counter. `pipeline/death_probe.py` owns that mechanism and
carries the full reasoning; this module still decides only what a status code MEANS and still
writes nothing itself. The measured sensitivity is 6.7% (4 of 60 postings the scanner had proved
closed), so the narrowing resolves a small fraction of D-314 and closes none of the rest.

**`pipeline/liveness.py::check_leads` is untouched by that narrowing** — the shortlist probe
still reads URLs and writes nothing, ever. One 404 against a lead withholds it from this run and
from nothing else.

**Fail-open is the whole design.** The cost of treating a dead posting as alive is one wasted
résumé; the cost of treating a live posting as dead is a job the user never sees and cannot
know they missed. Only an explicit gone-status earns `dead`. Everything else — a timeout, a refused
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

**Workday is asked through its CXS endpoint, not its page.** Every closed Workday requisition
measured still answered HTTP 200 on its page (0 of 37, D-325), so a page probe there can only
ever say `alive` — and on the death-probe path that RESETS earned strikes. The posting's JSON
endpoint answers an unposted requisition with a 403 naming error `S22` and a removed one with a
404, and `verdict_for_workday_cxs` reads exactly those (`workday_unposted`, `refetch_gone`). A
bare 403 stays `unknown`: it is the body code, not the status, that is the evidence.

**LinkedIn is asked through its guest `jobPosting` endpoint, not its job-view page** (D-653). The
page answers 200 for a closed job, which is why 0 of 7,106 `linkedin` rows had ever closed. The
endpoint's top card carries the class `closed-job__flavor--closed` on a closed job and a title
without it on an open one. `verdict_for_linkedin_guest` reads only the top card, which the endpoint
serves before the job description, so nothing an employer writes in a description can match. This
is a class in LinkedIn's own markup, not a phrase in a JD, so the catalog rejected below does not
apply to it.

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

import json
import re
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
    "refetch_gone",  # a 404/410 from the URL asked about — yields `dead`
    "workday_unposted",  # Workday's CXS 403 naming error S22 — yields `dead`
    "oracle_unposted",  # Oracle HCM's detail resource answering an empty `items` — yields `dead`
    "linkedin_closed",  # LinkedIn's guest top card marked closed — yields `dead`
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
    "workday_unposted": "dead",
    "oracle_unposted": "dead",
    "linkedin_closed": "dead",
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

# The `errorCode` Workday's CXS endpoint names in a 403 body for a requisition that has been
# unposted (measured: `{"errorCode":"S22","httpStatus":403,"message":"permission denied",...}`).
# A 403 WITHOUT it stays `unknown`, for the bot-blocker reason above.
WORKDAY_UNPOSTED_CODE = "S22"

# The class LinkedIn's guest `jobPosting` endpoint puts on the top card of a closed job (measured
# 2026-10-30, D-653: on all 40 jobs whose logged-in page read "No longer accepting applications",
# and 0 false deaths in 109 open controls; the 2 of those it marked had really closed). Matched as a
# class token inside a `class` attribute, never as text.
LINKEDIN_CLOSED_CLASS = "closed-job__flavor--closed"
_LINKEDIN_CLOSED = re.compile(
    rb"""class\s*=\s*["'](?:[^"']*\s)?"""
    + re.escape(LINKEDIN_CLOSED_CLASS).encode()
    + rb"""(?=["'\s])"""
)
# Present on every job's top card, open or closed. A 200 without it is not a job page at all (a
# login wall, an error shell), so it says nothing and must not clear earned strikes.
_LINKEDIN_TOP_CARD_TITLE = b"top-card-layout__title"
# Where the job description starts. The top card is served before it.
_LINKEDIN_DESCRIPTION = b"show-more-less-html"


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

    @property
    def gone_but_redirected(self) -> bool:
        """A gone-status that was forgiven because a redirect reached it.

        Exposed as a property so the runner counts it through the catalog rather than by
        comparing a signal string at the call site, and counted at all because otherwise this
        bucket disarms the gate silently: if an ATS starts fronting expired requisitions with
        `301 → 404`, every genuine gone posting reclassifies to `unknown`, `dead` goes to 0
        permanently, and the run reports "N checked, 0 gone, N unknown" — byte-identical to a run
        where every probe timed out. `0 dead` would read as the gate clause being MET while the
        detector was fully disarmed. A number that moves is the difference.
        """
        return self.signal == "refetch_gone_after_redirect"


def verdict_for_status(posting_id: int, status_code: int) -> Liveness:
    """Classify a completed page re-fetch. `GONE_STATUSES` is its only path to `dead`."""
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


def _cxs_error_code(body: bytes) -> object:
    """The `errorCode` of a CXS error body, or None if it is not one. Read as a field, never as a
    substring: a bot-blocker page that happens to contain `S22` must not read as a death."""
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    return payload.get("errorCode") if isinstance(payload, dict) else None


def verdict_for_workday_cxs(
    posting_id: int, status_code: int, body: bytes, *, redirected: bool = False
) -> Liveness:
    """Classify an answer from a posting's Workday CXS endpoint (`providers/workday.cxs_job_url`).

    The posting PAGE answers 200 for a closed requisition, so its status means nothing; the
    endpoint's does. Measured 2026-10-25 against 23 known-closed and 9 known-open postings, all
    consistent: a live one answers 200 with a `jobPostingInfo` object, an unposted one 403 whose
    JSON `errorCode` is `S22`, a removed one 404. Only those three shapes earn a verdict. A 200
    without a live `jobPostingInfo` (`canApply: false` included) and any other status are
    `unknown`, and the redirect rule applies to both gone shapes exactly as it does to a page probe.
    """
    if status_code == 200:
        try:
            info = json.loads(body).get("jobPostingInfo")
        except (ValueError, AttributeError):
            info = None
        if isinstance(info, dict) and info.get("canApply") is not False:
            return verdict_for_status(posting_id, status_code)
        return Liveness(
            posting_id=posting_id,
            verdict="unknown",
            signal="refetch_error",
            detail="workday CXS 200 without a live jobPostingInfo",
        )
    if status_code == 403 and _cxs_error_code(body) == WORKDAY_UNPOSTED_CODE:
        if redirected:
            return Liveness(
                posting_id=posting_id,
                verdict="unknown",
                signal="refetch_gone_after_redirect",
                detail="workday CXS 403 S22 after a redirect",
            )
        return Liveness(
            posting_id=posting_id,
            verdict="dead",
            signal="workday_unposted",
            detail="workday CXS 403 S22",
        )
    return verdict_for_failure(
        posting_id, status_code, f"workday CXS HTTP {status_code}", redirected=redirected
    )


def verdict_for_oracle_details(
    posting_id: int, status_code: int, body: bytes, *, redirected: bool = False
) -> Liveness:
    """Classify an answer from a posting's Oracle HCM detail resource
    (`providers/oraclehcm.details_url_for_page`).

    The posting page is a client-rendered shell, so its 200 means nothing. The resource answers
    200 either way and its `items` carries the difference. Measured 2026-10-27 (D-648): of 40
    postings the scanner had proved closed, 33 answered an empty `items` and 7 still returned
    their requisition; of 40 their board had listed that morning, 38 returned it and 2 answered
    empty, both absent from their board's live search beside 3 of 3 alive controls. So an empty
    `items` is `dead`, a non-empty one `alive`, and anything else `unknown`. A requisition that
    is returned is `alive` even with a null `ExternalPostedStartDate`: one listed posting had it.
    """
    if status_code == 200:
        try:
            items = json.loads(body).get("items")
        except (ValueError, AttributeError):
            items = None
        if isinstance(items, list) and items:
            return verdict_for_status(posting_id, status_code)
        if isinstance(items, list):
            if redirected:
                return Liveness(
                    posting_id=posting_id,
                    verdict="unknown",
                    signal="refetch_gone_after_redirect",
                    detail="oracle details empty items after a redirect",
                )
            return Liveness(
                posting_id=posting_id,
                verdict="dead",
                signal="oracle_unposted",
                detail="oracle details 200 with empty items",
            )
        return Liveness(
            posting_id=posting_id,
            verdict="unknown",
            signal="refetch_error",
            detail="oracle details 200 without an items list",
        )
    return verdict_for_failure(
        posting_id, status_code, f"oracle details HTTP {status_code}", redirected=redirected
    )


def verdict_for_linkedin_guest(
    posting_id: int, status_code: int, body: bytes, *, redirected: bool = False
) -> Liveness:
    """Classify an answer from a job's LinkedIn guest endpoint (`lanes/linkedin.guest_posting_url`).

    Only a 200 earns a verdict. Its top card, the part before the description, decides it: the
    closed class is `dead` (`linkedin_closed`), a title without it is `alive`, and no title is
    `unknown`. A closed card reached through a redirect is `unknown`, by the module's redirect rule.
    Every non-200 is `unknown`, a 404 included: no guest 404 has been measured against a
    known-closed job, and a 429 or 999 is LinkedIn rate-limiting, which says nothing about the job.
    """
    if status_code != 200:
        return Liveness(
            posting_id=posting_id,
            verdict="unknown",
            signal="refetch_error",
            detail=f"linkedin guest HTTP {status_code}",
        )
    top_card = body.split(_LINKEDIN_DESCRIPTION, 1)[0]
    if _LINKEDIN_CLOSED.search(top_card):
        if redirected:
            return Liveness(
                posting_id=posting_id,
                verdict="unknown",
                signal="refetch_gone_after_redirect",
                detail="linkedin guest closed after a redirect",
            )
        return Liveness(
            posting_id=posting_id,
            verdict="dead",
            signal="linkedin_closed",
            detail="linkedin guest top card closed",
        )
    if _LINKEDIN_TOP_CARD_TITLE in top_card:
        return verdict_for_status(posting_id, status_code)
    return Liveness(
        posting_id=posting_id,
        verdict="unknown",
        signal="refetch_error",
        detail="linkedin guest 200 without a top card",
    )


def verdict_without_url(posting_id: int) -> Liveness:
    """`postings.url` is nullable. Nothing to ask, so nothing is claimed."""
    return Liveness(posting_id=posting_id, verdict="unknown", signal="no_url")


__all__ = [
    "GONE_STATUSES",
    "LINKEDIN_CLOSED_CLASS",
    "SIGNALS",
    "SIGNAL_VERDICTS",
    "VERDICTS",
    "WORKDAY_UNPOSTED_CODE",
    "ContradictoryLiveness",
    "Liveness",
    "UnknownLivenessVerdict",
    "verdict_for_failure",
    "verdict_for_linkedin_guest",
    "verdict_for_status",
    "verdict_for_workday_cxs",
    "verdict_without_url",
]
