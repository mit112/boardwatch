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

from sqlalchemy import Engine, select

from boardwatch.core.liveness import (
    Liveness,
    verdict_for_failure,
    verdict_for_status,
    verdict_without_url,
)
from boardwatch.core.politeness import Fetcher, FetchFailure
from boardwatch.core.settings import Settings
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
    """
    fetcher = Fetcher(settings.model_copy(update={"retry_attempts": 1}))

    def probe(posting_id: int, url: str) -> Liveness:
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
