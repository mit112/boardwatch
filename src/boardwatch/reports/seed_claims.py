"""Which unresolved `lane_seeds` rows NO registered resolver can ever select (D-422).

`unresolved_seeds` requires a host set and deliberately offers no all-hosts form, so routing is
by catalog: a resolver sees exactly the hosts its own `SEED_HOSTS`/`SEED_HOST_SUFFIXES` claim.
That is the right design -- an all-hosts read would let a vendor one resolver cannot parse starve
every vendor behind it -- but it has a cost nothing else measures. **A seed on a host outside
every catalog is selected by nothing, so it is attempted by nothing, so the `attempts` ceiling
never ages it out.** A bound on work only bounds work that happens; the row sits unresolved and
unattempted forever and reports itself as nothing at all.

First reading, run 143: **109 of 773 seeds (14.1%) claimable, 664 (85.9%) across 197 hosts
claimable by nothing.** That is not waste and this report must not be read as calling it waste --
`grnh.se` (109), `eeho.fa.us2.oraclecloud.com` (Oracle HCM) and `lockheedmartin.eightfold.ai`
(Eightfold) are queues whose consumers do not exist YET, which is the outcome the durable handoff
was designed for (D-416). The point is that the queue must not accumulate unmeasured, because an
unmeasured queue is indistinguishable from a drained one.

**This module has no I/O.** It consumes rows the caller already read and classifies them, the
same split every other report in this package keeps.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardwatch.lanes import jsonld
from boardwatch.store.seed_queries import ResolverCatalog, UnclaimedHost

# Every resolver's seed catalog, by lane name. **Imported, never re-spelled** -- a second copy of
# a host set is how a vendor joins the resolver and never the report, and that error is silent in
# the worse direction: a host this report calls unclaimed while a resolver quietly drains it sends
# someone to build a resolver that already exists.
#
# A lane that declares `SEED_HOSTS` and is missing here would make its whole backlog read as
# unclaimed, so `tests/unit/test_seed_claims.py` scans `boardwatch.lanes` for the declaration
# and fails on any module absent from this map. Registration is not something to remember.
SEED_RESOLVERS: dict[str, ResolverCatalog] = {
    jsonld.JsonLdLane.name: ResolverCatalog(
        hosts=jsonld.SEED_HOSTS,
        host_suffixes=jsonld.SEED_HOST_SUFFIXES,
        max_attempts=jsonld.SEED_MAX_ATTEMPTS,
    ),
}


def enabled_catalogs(lanes_enabled: tuple[str, ...]) -> tuple[ResolverCatalog, ...]:
    """The catalogs of the resolvers that will actually RUN, in `lanes_enabled` order.

    **Registered is not enabled, and for this report the difference is the whole point.**
    `settings.lanes_enabled` is empty by default and `pipeline.runner` builds only the lanes it
    names, so a resolver present in `SEED_RESOLVERS` but absent from the config drains nothing.
    Counting its hosts as claimable would take the leak's worst case — seeds nothing will ever
    select — and report it as the healthy half, which is the exact inversion this command exists to
    prevent.
    """
    return tuple(
        SEED_RESOLVERS[name] for name in lanes_enabled if name in SEED_RESOLVERS
    )


@dataclass(frozen=True)
class SeedClaimReport:
    """The claimed/unclaimed split over unresolved seeds, and every unclaimed host by size."""

    unresolved: int
    unclaimed: int
    hosts: tuple[UnclaimedHost, ...]

    @property
    def claimed(self) -> int:
        return self.unresolved - self.unclaimed

    @property
    def unclaimed_share(self) -> float | None:
        """`None` rather than 0.0 on an empty queue -- a share of nothing is not zero percent.

        The four non-measured buckets in `board_coverage` use the same word for the same reason:
        inventing a number to satisfy a type is how a metric starts lying.
        """
        return self.unclaimed / self.unresolved if self.unresolved else None


def build_seed_claim_report(
    *, unresolved: int, hosts: tuple[UnclaimedHost, ...]
) -> SeedClaimReport:
    """Classify one reading. `unresolved` is the whole unresolved queue, `hosts` its unclaimed part.

    `unclaimed` is summed from `hosts` rather than taken as a third argument, so the total and its
    breakdown cannot disagree -- a caller passing both would eventually pass two reads taken either
    side of a write.
    """
    return SeedClaimReport(
        unresolved=unresolved, unclaimed=sum(h.seeds for h in hosts), hosts=hosts
    )
