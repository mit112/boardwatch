"""Re-fetch the shortlist's postings and drop the ones that are provably gone (P6 item 6).

Sits between the ranker and the tailor loop, which is the only place it can sit: the gate clause
is "**0** dead postings reaching the lead list", and the lead list is what the tailor loop
builds. Ranking is a pure DB read by design and stays that way — `rank_open_postings` does no
network I/O and this does not change that.

Scale is what makes it affordable. The ranker's corpus is ~23,000 open postings; its shortlist
is `--top N`, defaulting to 10 (`DEFAULT_TOP_N`; 8 -> 40 by D-272, 40 -> 10 by D-293).
Probing the shortlist is tens of requests; probing the corpus would be a second full crawl
and is never done.

The prober is passed IN rather than constructed here, and `None` means "not probed". That is the
fail-open direction spelled as a default: a caller that says nothing gets today's behaviour and
a funnel that reports the check as *unmeasured* rather than as zero dead (the D-022/D-023 rule).
`cli/run_cmd.py` supplies the real one, so a real run always checks.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from urllib.parse import unquote, urlsplit

from rich.console import Console
from sqlalchemy import Engine, select

from boardwatch.core.liveness import (
    LinkedInGuestObservation,
    Liveness,
    verdict_for_adp_requisition,
    verdict_for_eightfold_position,
    verdict_for_failure,
    verdict_for_linkedin_guest,
    verdict_for_oracle_details,
    verdict_for_smartrecruiters_posting,
    verdict_for_status,
    verdict_for_workday_cxs,
    verdict_without_url,
)
from boardwatch.core.politeness import Fetcher, FetchFailure, FetchResult
from boardwatch.core.settings import Settings
from boardwatch.lanes.linkedin import LANE_NAME as LINKEDIN_LANE
from boardwatch.lanes.linkedin import guest_posting_url
from boardwatch.pipeline.progress import StageProgress
from boardwatch.providers.adp import requisition_url_for_page
from boardwatch.providers.eightfold import (
    board_domain,
    position_details_url,
    position_page_target,
)
from boardwatch.providers.oraclehcm import details_url_for_page
from boardwatch.providers.smartrecruiters import posting_api_target
from boardwatch.providers.workday import cxs_job_url
from boardwatch.store.tables import postings

# A probe of one posting. Injectable so tests never touch the network and so the pipeline does
# not have to know how a URL is fetched.
LivenessProber = Callable[[int, str], Liveness]


def asks_linkedin_guest(settings: Settings) -> bool:
    """Whether the prober asks a LinkedIn job-view URL through the guest endpoint (D-653).

    Only when the user enabled the LinkedIn lane: that endpoint is the lane's opt-in request
    (D-290). One function, so the death probe's ordering and the prober cannot disagree on it.
    """
    return LINKEDIN_LANE in settings.lanes_enabled


def build_prober(settings: Settings) -> LivenessProber:
    """The production prober: one GET per posting through the politeness Fetcher.

    `retry_attempts=1`. Retrying is right for a scan, which must not lose a whole board to one
    blip, and wrong here: a liveness probe is a point-in-time question whose unknown answer is
    already safe, so a retry buys nothing and spends the operator's morning. With the Fetcher's
    30 s timeout, one attempt bounds a shortlist of 20 at ten minutes in the pathological case
    instead of thirty.

    GET, not HEAD: `Fetcher` exposes `get`/`post_json` only, and reusing it keeps the identifying
    user agent, the per-host serial pacing and the host locks that make repeated probing polite.
    What reuse also brings is `follow_redirects=True`, so the status this sees may belong to a
    resource the stored URL was sent to rather than the posting itself — `FetchFailure.redirected`
    is forwarded for exactly that reason, and `core/liveness.py` decides what it means.

    A Workday posting page is asked about through its CXS endpoint instead, because the page
    answers 200 whether or not the requisition is open (`core/liveness.py`). An Oracle HCM posting
    page is asked through its requisition detail resource, for the same reason (D-648), and a
    LinkedIn job-view page through the guest `jobPosting` endpoint (D-653) — only when the user
    has enabled the LinkedIn lane, because that endpoint is the lane's opt-in request (D-290).

    D-684 adds three more, each measured against same-host open and closed controls: an ADP
    recruitment page is asked through ADP's public requisition resource (the page is one shell for
    every jobId); a SmartRecruiters posting is asked through its API's `active` flag first and, if
    that says nothing, through its page exactly as before; an Eightfold position page is fetched as
    before and, when it carries the tenant's `pcsx-data` blob, its `position_details` is asked.
    """
    fetcher = Fetcher(settings.model_copy(update={"retry_attempts": 1}))
    ask_linkedin_guest = asks_linkedin_guest(settings)

    def probe_workday(posting_id: int, cxs_url: str) -> Liveness:
        try:
            result = fetcher.get(cxs_url, headers={"Accept": "application/json"})
        except FetchFailure as exc:
            if exc.status_code is None:
                return verdict_for_failure(posting_id, None, str(exc))
            return verdict_for_workday_cxs(
                posting_id, exc.status_code, exc.body, redirected=exc.redirected
            )
        except Exception as exc:  # noqa: BLE001 - any transport fault is `unknown`, never `dead`
            return verdict_for_failure(posting_id, None, f"{type(exc).__name__}: {exc}")
        return verdict_for_workday_cxs(posting_id, result.status_code, result.content)

    def probe_oracle(posting_id: int, details_url: str) -> Liveness:
        try:
            result = fetcher.get(details_url, headers={"Accept": "application/json"})
        except FetchFailure as exc:
            if exc.status_code is None:
                return verdict_for_failure(posting_id, None, str(exc))
            return verdict_for_oracle_details(
                posting_id, exc.status_code, exc.body, redirected=exc.redirected
            )
        except Exception as exc:  # noqa: BLE001 - any transport fault is `unknown`, never `dead`
            return verdict_for_failure(posting_id, None, f"{type(exc).__name__}: {exc}")
        # An empty `items` is a death only from the resource asked about, so a 200 that came from
        # somewhere else carries the redirect rule too. The query is compared as well, because the
        # requisition's identity lives there; decoded, so a re-encoded `;` or `,` is not a move.
        final, asked = urlsplit(result.final_url), urlsplit(details_url)
        moved = bool(result.final_url) and (
            (final.hostname, final.path, unquote(final.query))
            != (asked.hostname, asked.path, unquote(asked.query))
        )
        return verdict_for_oracle_details(
            posting_id, result.status_code, result.content, redirected=moved
        )

    def probe_linkedin(posting_id: int, guest_url: str) -> Liveness:
        try:
            result = fetcher.get(guest_url)
        except FetchFailure as exc:
            if exc.status_code is None:
                verdict = verdict_for_failure(posting_id, None, str(exc))
            else:
                verdict = verdict_for_linkedin_guest(
                    posting_id, exc.status_code, exc.body, redirected=exc.redirected
                )
            status = exc.observed_status if exc.observed_status is not None else exc.status_code
            return replace(verdict, linkedin_guest=LinkedInGuestObservation(status))
        except Exception as exc:  # noqa: BLE001 - any transport fault is `unknown`, never `dead`
            verdict = verdict_for_failure(posting_id, None, f"{type(exc).__name__}: {exc}")
            return replace(verdict, linkedin_guest=LinkedInGuestObservation(None))
        moved = bool(result.final_url) and urlsplit(result.final_url)[:3] != urlsplit(guest_url)[:3]
        verdict = verdict_for_linkedin_guest(
            posting_id, result.status_code, result.content, redirected=moved
        )
        return replace(verdict, linkedin_guest=LinkedInGuestObservation(result.status_code))

    def moved(final_url: str, asked: str) -> bool:
        """Whether a 200 came from somewhere other than the resource asked about. The query is
        compared decoded, because the requisition's identity can live there."""
        final, wanted = urlsplit(final_url), urlsplit(asked)
        return bool(final_url) and (
            (final.hostname, final.path, unquote(final.query))
            != (wanted.hostname, wanted.path, unquote(wanted.query))
        )

    def ask_json(
        posting_id: int, resource_url: str, classify: Callable[..., Liveness]
    ) -> Liveness:
        """One GET of a JSON resource, classified by `classify(posting_id, status, body,
        redirected=...)`. A transport fault is `unknown`; every non-200 reaches `classify` with its
        body, because a wall and an application's own 404 are told apart by the body."""
        try:
            result = fetcher.get(resource_url, headers={"Accept": "application/json"})
        except FetchFailure as exc:
            if exc.status_code is None:
                return verdict_for_failure(posting_id, None, str(exc))
            return classify(posting_id, exc.status_code, exc.body, redirected=exc.redirected)
        except Exception as exc:  # noqa: BLE001 - any transport fault is `unknown`, never `dead`
            return verdict_for_failure(posting_id, None, f"{type(exc).__name__}: {exc}")
        return classify(
            posting_id,
            result.status_code,
            result.content,
            redirected=moved(result.final_url, resource_url),
        )

    def fetch_page(posting_id: int, url: str) -> tuple[Liveness, FetchResult | None]:
        """The plain page probe, plus the response when there was one."""
        try:
            result = fetcher.get(url)
        except FetchFailure as exc:
            return (
                verdict_for_failure(
                    posting_id, exc.status_code, str(exc), redirected=exc.redirected
                ),
                None,
            )
        except Exception as exc:  # noqa: BLE001 - any transport fault is `unknown`, never `dead`
            # Deliberately broad. The whole point is that nothing except an explicit gone-status
            # withholds a lead, so an unforeseen client error must not become a silent veto.
            return verdict_for_failure(posting_id, None, f"{type(exc).__name__}: {exc}"), None
        return verdict_for_status(posting_id, result.status_code), result

    def probe_eightfold(posting_id: int, url: str, host: str, position_id: str) -> Liveness:
        verdict, page = fetch_page(posting_id, url)
        if page is None or verdict.verdict != "alive":
            return verdict
        try:
            domain = board_domain(page.content)
        except ValueError:
            return verdict  # not an Eightfold career page: today's reading of the page stands
        details = position_details_url(host, domain, position_id)
        # The page's 200 is no evidence here (a closed position serves it), so an API answer that
        # says nothing is `unknown`, not the page's `alive`: that would clear earned strikes.
        return ask_json(
            posting_id,
            details,
            lambda pid, status, body, *, redirected: verdict_for_eightfold_position(
                pid, status, body, position_id=position_id, redirected=redirected
            ),
        )

    def probe(posting_id: int, url: str) -> Liveness:
        cxs_url = cxs_job_url(url)
        if cxs_url is not None:
            return probe_workday(posting_id, cxs_url)
        details_url = details_url_for_page(url)
        if details_url is not None:
            return probe_oracle(posting_id, details_url)
        guest_url = guest_posting_url(url) if ask_linkedin_guest else None
        if guest_url is not None:
            return probe_linkedin(posting_id, guest_url)
        requisition_url = requisition_url_for_page(url)
        if requisition_url is not None:
            return ask_json(posting_id, requisition_url, verdict_for_adp_requisition)
        posting = posting_api_target(url)
        if posting is not None:
            api_url, posting_ref = posting
            flagged = ask_json(
                posting_id,
                api_url,
                lambda pid, status, body, *, redirected: verdict_for_smartrecruiters_posting(
                    pid, status, body, posting_ref=posting_ref, redirected=redirected
                ),
            )
            if flagged.withholds:
                return flagged
            # `active: true` is not `alive` (core/liveness.py): the page decides, as it always did.
        position = position_page_target(url)
        if position is not None:
            return probe_eightfold(posting_id, url, *position)
        return fetch_page(posting_id, url)[0]

    return probe


def check_leads(
    engine: Engine,
    posting_ids: Sequence[int],
    *,
    prober: LivenessProber,
    console: Console | None = None,
) -> dict[int, Liveness]:
    """Probe each posting once, in the order given. Reads URLs; writes nothing, ever."""
    if not posting_ids:
        return {}
    with engine.connect() as conn:
        # NOT chunked, and that is a precondition rather than an oversight: `posting_ids` is
        # `ranked.visible`, which `runner.py` bounds by `top_n` because it calls
        # `rank_open_postings` with every `include_*` at its False default. Open ONE of those
        # flags from the pipeline and `visible` becomes corpus-scaled — ~19k — and this binds
        # past SQLite's parameter cap and dies exactly as run 70 did (D-287/D-289). If that
        # ever changes, this needs `store.param_chunks.id_chunks` like the rest.
        urls = {
            int(row.id): (row.url or "")
            for row in conn.execute(
                select(postings.c.id, postings.c.url).where(postings.c.id.in_(posting_ids))
            ).all()
        }
    results: dict[int, Liveness] = {}
    progress = StageProgress("shortlist probe", len(posting_ids), console=console)
    for posting_id in posting_ids:
        url = urls.get(posting_id, "")
        results[posting_id] = (
            prober(posting_id, url) if url else verdict_without_url(posting_id)
        )
        progress.advance(item=str(posting_id))
    progress.finish()
    return results


__all__ = ["LivenessProber", "build_prober", "check_leads"]
