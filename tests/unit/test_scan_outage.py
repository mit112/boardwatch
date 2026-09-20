"""`is_systemic_scan_outage` (D-037): the single outage predicate `run_scan` (standalone) and
`run_pipeline` both classify a run by. Pure function, no DB.

The contract is "attempted boards > 0 AND NOT ONE of them returned any usable postings" —
complete == 0 AND unchanged == 0 AND partial == 0. `partial` is load-bearing and was the
defect: a board that comes back `partial` holds real postings, so a scan containing one has
evidence in hand and is degraded, not a systemic outage (owner ruling, 2026-09-20).
"""

import pytest

from boardwatch.scan.coordinator import is_systemic_scan_outage


def test_true_when_every_board_attempted_returned_nothing_usable() -> None:
    assert is_systemic_scan_outage(attempted=5, complete=0, unchanged=0, partial=0) is True


def test_false_when_nothing_was_attempted() -> None:
    """An empty watch list is an honest empty day, not an outage."""
    assert is_systemic_scan_outage(attempted=0, complete=0, unchanged=0, partial=0) is False


def test_false_when_any_board_completed() -> None:
    assert is_systemic_scan_outage(attempted=5, complete=1, unchanged=0, partial=0) is False


def test_false_when_any_board_was_unchanged() -> None:
    """Unchanged is a healthy outcome (nothing new to fetch), not a dead board."""
    assert is_systemic_scan_outage(attempted=5, complete=0, unchanged=1, partial=0) is False


def test_false_when_boards_split_between_complete_and_unchanged() -> None:
    """A normal healthy scan — some boards complete, some unchanged, none of either at zero —
    is definitively not an outage. Distinct from the single-clause cases above: both `complete`
    and `unchanged` are nonzero here, not just one of the two."""
    assert is_systemic_scan_outage(attempted=5, complete=2, unchanged=3, partial=0) is False


@pytest.mark.parametrize(
    ("attempted", "complete", "unchanged", "partial", "expected"),
    [
        # The live case: runs 23/26/31/36/37 in the store, each one board attempted and back
        # `partial` with postings in hand. Degraded, never fatal.
        (1, 0, 0, 1, False),
        # The same run with the one board dead instead. Zero usable evidence stays fatal.
        (1, 0, 0, 0, True),
        (0, 0, 0, 0, False),
        # One complete and one partial: usable twice over.
        (2, 1, 0, 1, False),
    ],
)
def test_the_exact_boundary_on_partial(
    attempted: int, complete: int, unchanged: int, partial: int, expected: bool
) -> None:
    """The boundary the owner ruling moved. `(1,0,0,1)` vs `(1,0,0,0)` is the whole change:
    one board back `partial` is degraded success, one board back `failed` is the outage."""
    assert (
        is_systemic_scan_outage(
            attempted=attempted, complete=complete, unchanged=unchanged, partial=partial
        )
        is expected
    )
