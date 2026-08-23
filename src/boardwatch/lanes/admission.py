"""The per-run cap on companies a lane may add (JD-acquisition spec §4.6).

Owner ruling (D-278): adding a company's whole board IS breadth, and breadth is last. So a
lane may add companies only under an explicit per-run cap, and every addition is reported.
Unbounded, one Simplify pull adds 5,695 companies; the largest single non-six company in
those lists is a UK grocer with 1,639 postings that the US-only gate discards anyway.

Refusals are IDENTIFIED, not merely counted. A company dropped silently is
indistinguishable from one the lane never saw, and the difference is the whole diagnostic
value. Each side is reported as the `(provider, slug)` pair it was keyed on, in order.

Open question (not decided here): `companies.source` is constrained to `('registry','user')`.
A lane-discovered company is neither — it was not shipped in the registry and the user did
not type it. Two options exist: (1) reuse `'registry'`, since the company is program-discovered
rather than user-entered, or (2) migrate the column to add a third value (e.g. `'lane'`) that
distinguishes lane-discovered companies from the shipped registry. Option 2 is a schema change
and is the owner's call, not this task's. Nothing in this task inserts a company row, so the
choice is not forced yet — it is recorded here for whoever writes that insert.
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
    from one already watched, because that needs a store query
    (`queries.get_watched_companies(conn, provider=, slug=)`). A runner that calls `admit()`
    for every company a lane saw spends all ten slots on companies already watched: reach
    never widens, and the refusal list looks exactly like a normal capped run, so nothing
    reports the failure. The is-it-new check belongs with the runner that holds the
    connection and is deliberately NOT built here.
    """

    def __init__(self, limit: int) -> None:
        if limit < 0:
            raise ValueError(f"company budget cannot be negative: {limit}")
        self._limit = limit
        self._admitted: list[CompanyKey] = []
        self._refused: list[CompanyKey] = []

    def admit(self, provider: str, slug: str) -> bool:
        key: CompanyKey = (provider, slug)
        if key in self._admitted:
            # Already paid for. Two postings from one employer are one company.
            return True
        if len(self._admitted) >= self._limit:
            self._refused.append(key)
            return False
        self._admitted.append(key)
        return True

    @property
    def admitted(self) -> tuple[CompanyKey, ...]:
        return tuple(self._admitted)

    @property
    def refused(self) -> tuple[CompanyKey, ...]:
        return tuple(self._refused)
