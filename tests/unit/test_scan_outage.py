"""`is_systemic_scan_outage` (D-037): the single outage predicate `run_scan` (standalone) and
`run_pipeline` both classify a run by. Pure function, no DB — behavior must match exactly what
was previously duplicated inline at `runner.py:163` and `coordinator.py:249`: attempted boards
> 0 AND complete == 0 AND unchanged == 0."""

from boardwatch.scan.coordinator import is_systemic_scan_outage


def test_true_when_every_board_attempted_neither_completed_nor_unchanged() -> None:
    assert is_systemic_scan_outage(attempted=5, complete=0, unchanged=0) is True


def test_false_when_nothing_was_attempted() -> None:
    """An empty watch list is an honest empty day, not an outage."""
    assert is_systemic_scan_outage(attempted=0, complete=0, unchanged=0) is False


def test_false_when_any_board_completed() -> None:
    assert is_systemic_scan_outage(attempted=5, complete=1, unchanged=0) is False


def test_false_when_any_board_was_unchanged() -> None:
    """Unchanged is a healthy outcome (nothing new to fetch), not a dead board."""
    assert is_systemic_scan_outage(attempted=5, complete=0, unchanged=1) is False


def test_false_when_boards_split_between_complete_and_unchanged() -> None:
    """A normal healthy scan — some boards complete, some unchanged, none of either at zero —
    is definitively not an outage. Distinct from the single-clause cases above: both `complete`
    and `unchanged` are nonzero here, not just one of the two."""
    assert is_systemic_scan_outage(attempted=5, complete=2, unchanged=3) is False
