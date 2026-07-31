"""summarize_events reads a half-open window (since, max] over the append-only ledger.

Closed postings are a count, not a list: D18's digest renders "New / Reopened / Updated /
Closed-count", because a closing is not something the user can act on.
"""

from pathlib import Path

from boardwatch.reports.digest import summarize_events


def test_full_window_groups_by_kind_and_counts_closures(tmp_path: Path, seeded_events) -> None:
    seed = seeded_events(tmp_path)
    with seed.engine.connect() as conn:
        summary = summarize_events(conn, 0)
    assert [e.title for e in summary.new] == ["alpha", "beta"]
    assert [e.title for e in summary.reopened] == ["gamma"]
    assert [e.title for e in summary.revised] == ["delta"]
    assert summary.closed_count == 2
    assert summary.since_event_id == 0
    assert not summary.is_empty


def test_window_is_half_open_so_the_cursor_row_is_excluded(
    tmp_path: Path, seeded_events
) -> None:
    seed = seeded_events(tmp_path)
    with seed.engine.connect() as conn:
        summary = summarize_events(conn, seed.event_ids["beta"])
    assert [e.title for e in summary.new] == []
    assert [e.title for e in summary.reopened] == ["gamma"]
    assert summary.max_event_id == seed.event_ids["zeta"]


def test_empty_window_reports_the_cursor_as_the_max(tmp_path: Path, seeded_events) -> None:
    """With nothing new, max_event_id must not regress below the cursor."""
    seed = seeded_events(tmp_path)
    with seed.engine.connect() as conn:
        summary = summarize_events(conn, seed.event_ids["zeta"])
    assert summary.is_empty
    assert summary.closed_count == 0
    assert summary.max_event_id == seed.event_ids["zeta"]


def test_entries_carry_the_company_name(tmp_path: Path, seeded_events) -> None:
    seed = seeded_events(tmp_path)
    with seed.engine.connect() as conn:
        summary = summarize_events(conn, 0)
    assert {e.company for e in summary.new} == {"Acme"}
