"""The per-run cap on companies a lane may add (JD-acquisition spec §4.6).

Owner ruling (D-278): adding a company's whole board IS breadth, and breadth is last. So a
lane may add companies only under an explicit per-run cap, and every addition is reported.
Unbounded, one Simplify pull adds 5,695 companies; the largest single non-six company in
those lists is a UK grocer with 1,639 postings that the US-only gate discards anyway.

Refusals are IDENTIFIED, not merely counted. A company dropped silently is
indistinguishable from one the lane never saw, and the difference is the whole diagnostic
value. Each side is reported as the `(provider, slug)` pair it was keyed on, in order.

A lane-discovered company is stored under `companies.source = 'lane'`, a third value the
`p_lane_companies` migration added (D-285). Reusing `'registry'` was rejected: it would make the
shipped registry indistinguishable from whatever an aggregator happened to surface, so nobody
could audit either. `queries.upsert_lane_company` is the only sanctioned insert.
"""

from __future__ import annotations

DEFAULT_NEW_COMPANIES_PER_RUN = 10

# The identity a company is admitted under: `(provider, slug)`, which is exactly what the
# store uniquely keys a company on — `companies` has UNIQUE(provider, slug), and
# `upsert_watch(provider=, slug=, ...)` conflict-resolves on that pair. It is also the form
# the user already reads and types everywhere else (`provider:slug`, as accepted by
# `core.board_urls` and `companies add`), so it needs no separate display name to be
# legible in a refusal report — and a report is actionable from it, which a name is not.
CompanyKey = tuple[str, str]


class CompanyBudget:
    """Admits at most `limit` distinct new companies, recording both sides.

    A company is `(provider, slug)`, NOT a display name. A budget keyed on a name miscounts
    in both directions against the store it is capping: one employer whose aggregator name
    varies ("Acme", "Acme Inc.", "ACME Corp") burns three slots for the one row
    UNIQUE(provider, slug) actually holds, and two different employers that share a name on
    different providers burn one slot between them, taking the run silently OVER the cap.
    This cap enforces "breadth is last", so miscounting it is a control failure.

    WHAT THIS CLASS CANNOT VERIFY, and its caller therefore owes. `admit()` has NO notion of
    *new*. It caps distinct companies presented to it; it cannot tell an unwatched company
    from one already stored, because that needs a store query
    (`queries.company_exists(conn, provider=, slug=)` — not the watched-only lookup, since a
    lane company is stored unwatched and would read as new forever). A runner that calls `admit()`
    for every company a lane saw spends all ten slots on companies already watched: reach
    never widens, and the refusal list looks exactly like a normal capped run, so nothing
    reports the failure. The is-it-new check belongs with the runner that holds the
    connection and is deliberately NOT built here.

    `limit=None` is uncapped: `admit()` never refuses. NOT `limit=0` — 0 already means
    something real and different (the off switch: admit nothing, still report every refusal),
    so a caller that wants "no cap" for one lane has to say so, not repurpose the value that
    already means the opposite.

    `tier1` IS A SECOND BUDGET, NOT A SECOND NUMBER, and the nesting is what makes "no separate
    bound" expressible at all. A lane's admissions can be opposite in kind: an Indeed tier-1 hit
    dereferences to a SUPPORTED employer board that joins the scan fleet and pays off on every
    later run, while a tier-2 hit is a permanently-secondhand aggregator row (D-452). One cap
    could not tell them apart, so one uncapped run admitted 58 boards and the cap went back on
    over the whole lane (D-459). Three states are needed and only two fit in an `int | None`:
    no separate bound (`tier1=None` — tier 1 charges THIS budget, which is what every existing
    config does), a bounded tier 1 (`CompanyBudget(n)`), and an uncapped tier 1
    (`CompanyBudget(None)`). A budget object carries all three without a sentinel, and it comes
    with the refusal reporting the tier already needs.

    `admitted` and `refused` are this budget's own entries followed by the nested one's, so each
    side stays in first-seen order WITHIN a tier. The tier is readable off the pair itself — a
    tier-2 Indeed company is keyed under `indeed` and a tier-1 one under the real provider it
    converged onto — so no caller needs a new bucket to tell the two refusals apart.
    """

    def __init__(self, limit: int | None, *, tier1: CompanyBudget | None = None) -> None:
        if limit is not None and limit < 0:
            raise ValueError(f"company budget cannot be negative: {limit}")
        self._limit = limit
        self._tier1 = tier1
        self._admitted: list[CompanyKey] = []
        self._refused: list[CompanyKey] = []

    def admit(self, provider: str, slug: str, *, tier1: bool = False) -> bool:
        if tier1 and self._tier1 is not None:
            # Charged to the tier's OWN budget and to nothing else: a tier-1 admission must not
            # spend a slot the tier-2 half is counting on, and vice versa. With no separate
            # bound configured this branch never runs and the tier flag changes nothing, which
            # is what makes the absent key today's behaviour exactly.
            return self._tier1.admit(provider, slug)
        key: CompanyKey = (provider, slug)
        if key in self._admitted:
            # Already paid for. Two postings from one employer are one company.
            return True
        if self._limit is not None and len(self._admitted) >= self._limit:
            # Deduplicated on the same rule as `_admitted`, and for the same reason: a refusal
            # COUNT that lists one employer three times overstates how much reach the cap cost,
            # which is the one number this report exists to give. Re-asking about an already
            # refused company is still False — the budget is spent either way.
            if key not in self._refused:
                self._refused.append(key)
            return False
        self._admitted.append(key)
        return True

    @property
    def admitted(self) -> tuple[CompanyKey, ...]:
        return tuple(self._admitted) + (self._tier1.admitted if self._tier1 else ())

    @property
    def refused(self) -> tuple[CompanyKey, ...]:
        return tuple(self._refused) + (self._tier1.refused if self._tier1 else ())
