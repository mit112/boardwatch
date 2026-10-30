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
from urllib.parse import unquote, urlsplit

from sqlalchemy import Engine, select

from boardwatch.core.liveness import (
    Liveness,
    verdict_for_failure,
    verdict_for_linkedin_guest,
    verdict_for_oracle_details,
    verdict_for_status,
    verdict_for_workday_cxs,
    verdict_without_url,
)
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.core.settings import Settings
from boardwatch.lanes.linkedin import LANE_NAME as LINKEDIN_LANE
from boardwatch.lanes.linkedin import guest_posting_url
from boardwatch.providers.oraclehcm import details_url_for_page
from boardwatch.providers.workday import cxs_job_url
from boardwatch.store.tables import postings

# A probe of one posting. Injectable so tests never touch the network and so the pipeline does
# not have to know how a URL is fetched.
LivenessProber = Callable[[int, str], Liveness]


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
    """
    fetcher = Fetcher(settings.model_copy(update={"retry_attempts": 1}))
    ask_linkedin_guest = LINKEDIN_LANE in settings.lanes_enabled

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
                return verdict_for_failure(posting_id, None, str(exc))
            return verdict_for_linkedin_guest(
                posting_id, exc.status_code, exc.body, redirected=exc.redirected
            )
        except Exception as exc:  # noqa: BLE001 - any transport fault is `unknown`, never `dead`
            return verdict_for_failure(posting_id, None, f"{type(exc).__name__}: {exc}")
        moved = bool(result.final_url) and urlsplit(result.final_url)[:3] != urlsplit(guest_url)[:3]
        return verdict_for_linkedin_guest(
            posting_id, result.status_code, result.content, redirected=moved
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
        try:
            result = fetcher.get(url)
        except FetchFailure as exc:
            return verdict_for_failure(
                posting_id, exc.status_code, str(exc), redirected=exc.redirected
            )
        except Exception as exc:  # noqa: BLE001 - any transport fault is `unknown`, never `dead`
            # Deliberately broad. The whole point is that nothing except an explicit gone-status
            # withholds a lead, so an unforeseen client error must not become a silent veto.
            return verdict_for_failure(posting_id, None, f"{type(exc).__name__}: {exc}")
        return verdict_for_status(posting_id, result.status_code)

    return probe


def check_leads(
    engine: Engine,
    posting_ids: Sequence[int],
    *,
    prober: LivenessProber,
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
    for posting_id in posting_ids:
        url = urls.get(posting_id, "")
        results[posting_id] = (
            prober(posting_id, url) if url else verdict_without_url(posting_id)
        )
    return results


__all__ = ["LivenessProber", "build_prober", "check_leads"]
