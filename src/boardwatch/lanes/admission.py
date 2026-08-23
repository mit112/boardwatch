"""The per-run cap on companies a lane may add (JD-acquisition spec §4.6).

Owner ruling (D-278): adding a company's whole board IS breadth, and breadth is last. So a
lane may add companies only under an explicit per-run cap, and every addition is reported.
Unbounded, one Simplify pull adds 5,695 companies; the largest single non-six company in
those lists is a UK grocer with 1,639 postings that the US-only gate discards anyway.

Refusals are NAMED, not merely counted. A company dropped silently is indistinguishable
from one the lane never saw, and the difference is the whole diagnostic value.

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


class CompanyBudget:
    """Admits at most `limit` distinct new companies, recording both sides."""

    def __init__(self, limit: int) -> None:
        if limit < 0:
            raise ValueError(f"company budget cannot be negative: {limit}")
        self._limit = limit
        self._admitted: list[str] = []
        self._refused: list[str] = []

    def admit(self, company_name: str) -> bool:
        if company_name in self._admitted:
            # Already paid for. Two postings from one employer are one company.
            return True
        if len(self._admitted) >= self._limit:
            self._refused.append(company_name)
            return False
        self._admitted.append(company_name)
        return True

    @property
    def admitted(self) -> tuple[str, ...]:
        return tuple(self._admitted)

    @property
    def refused(self) -> tuple[str, ...]:
        return tuple(self._refused)
