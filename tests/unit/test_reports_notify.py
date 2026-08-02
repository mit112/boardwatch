"""Pure selection tests for boardwatch.reports.notify (P5, Task 3).

select_new_matches must be a pure read over current DB state: it must never run
preflight, eligibility, or an LLM (`scan && notify` has to stay cheap). These tests
seed postings/events directly through the store (mirroring
tests/unit/conftest.py's seeded_events pattern) and drive eligibility through the
real facts/policy/run_eligibility path so persisted verdicts are genuine, never
mocked.

Note on the title-match test: passes_hard_filters does NOT gate on target_titles —
title_match is a scoring signal only (rank/heuristic.py), and the only hard-filter
veto on a title is an exact-substring, case-folded exclude_titles match. So
"a non-matching title is filtered out" is exercised here via exclude_titles, which
is the real mechanism, rather than a bare target-title mismatch.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, insert

from boardwatch.core.settings import Settings
from boardwatch.eligibility.facts import Facts, Policy, facts_payload
from boardwatch.eligibility.preflight import run_eligibility
from boardwatch.rank.heuristic import profile_view_from_row
from boardwatch.reports.notify import select_new_matches
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.events import append_event
from boardwatch.store.queries import get_profile, insert_run, save_eligibility, save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = datetime(2026, 7, 30, 12, 0, 0)

DEGREE_BODY = "We are hiring a backend engineer. A Bachelor's degree is required."
PLAIN_BODY = "Python and Go services with PostgreSQL."


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "cfg")


def _engine(settings: Settings) -> Engine:
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    return engine


def _seed_profile(
    engine: Engine, *, target_titles: tuple[str, ...] = (), exclude_titles: tuple[str, ...] = ()
) -> None:
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=list(target_titles),
            exclude_titles=list(exclude_titles), locations=[], remote_only=False,
            skills=[], taxonomy_version="t",
        )


def _seed_posting(
    engine: Engine, *, title: str, slug: str, kind: str = "new", body: str = "We are hiring.",
) -> tuple[int, int]:
    """Insert one company+job+posting+posting_version+event; return (posting_id, event_id)."""
    run_id = insert_run(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name=slug, provider="greenhouse", slug=slug, source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{slug}",
                    title=title, normalized_title=title.lower(),
                    url=f"https://example.test/{slug}",
                    locations_json=["Remote"], remote_policy="remote",
                    posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW,
                    status="open", consecutive_missing=0, content_hash=f"h-{slug}",
                    body_text=body,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=f"h-{slug}", body_text=body,
                captured_at=NOW, capture_reason="new",
            )
        )
        event_id = append_event(conn, posting_id, kind, run_id)
    return posting_id, event_id


def test_select_new_matches_only_new_and_matching(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    _seed_profile(engine, target_titles=("Engineer",), exclude_titles=("Sales",))
    _, event_a = _seed_posting(engine, title="Backend Engineer", slug="a")
    _, event_b = _seed_posting(engine, title="Sales Lead", slug="b")
    with engine.connect() as conn:
        profile = profile_view_from_row(get_profile(conn))
        result = select_new_matches(conn, 0, profile, settings)
    titles = [i.title for i in result.items]
    assert "Backend Engineer" in titles  # not excluded
    assert "Sales Lead" not in titles  # exclude_titles veto (real hard filter)
    # max_event_id advances over the whole `new`-kind window, even for the excluded posting.
    assert result.max_event_id == max(event_a, event_b)


def test_empty_window_returns_floor(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    _seed_profile(engine)
    _, event_id = _seed_posting(engine, title="Backend Engineer", slug="a")
    floor = event_id + 100  # deliberately past every real event id
    with engine.connect() as conn:
        profile = profile_view_from_row(get_profile(conn))
        result = select_new_matches(conn, floor, profile, settings)
    assert result.items == ()
    assert result.max_event_id == floor  # never rewinds below the supplied cursor


def test_ineligible_hidden_unevaluated_kept(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    _seed_profile(engine)
    facts = Facts(highest_degree="none")
    policy = Policy(families={"degree": "blocker"})
    with engine.begin() as conn:
        save_eligibility(
            conn, facts_json=facts_payload(facts), policy_json=policy.model_dump(mode="json")
        )
    ineligible_id, _ = _seed_posting(
        engine, title="Ineligible Role", slug="ineligible", body=DEGREE_BODY
    )
    # Evaluate now, while only the ineligible posting exists.
    stats = run_eligibility(engine, settings)
    assert stats.evaluated == 1
    # Seeded AFTER the run: no evaluation exists for it yet, so its verdict is None.
    unevaluated_id, _ = _seed_posting(
        engine, title="Unevaluated Role", slug="unevaluated", body=PLAIN_BODY
    )
    with engine.connect() as conn:
        profile = profile_view_from_row(get_profile(conn))
        result = select_new_matches(conn, 0, profile, settings)
    by_id = {i.posting_id: i for i in result.items}
    assert ineligible_id not in by_id  # persisted ineligible -> hidden
    assert unevaluated_id in by_id  # unevaluated (None) -> kept
    assert by_id[unevaluated_id].verdict is None


def test_reopened_revised_excluded(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    _seed_profile(engine)
    _seed_posting(engine, title="New Role", slug="new-role", kind="new")
    _seed_posting(engine, title="Reopened Role", slug="reopened-role", kind="reopened")
    _seed_posting(engine, title="Revised Role", slug="revised-role", kind="revised")
    with engine.connect() as conn:
        profile = profile_view_from_row(get_profile(conn))
        result = select_new_matches(conn, 0, profile, settings)
    titles = [i.title for i in result.items]
    assert "New Role" in titles
    assert "Reopened Role" not in titles
    assert "Revised Role" not in titles


def test_nonnew_only_window_advances_max_floor(tmp_path: Path) -> None:
    """A window containing ONLY non-`new` events (no `new` at all) must still advance
    max_event_id past since_event_id, otherwise the cursor never moves and these
    events get re-scanned forever (indefinitely stale high-water mark)."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    _seed_profile(engine)
    # Seed one `new` event first to establish the cursor floor, then seed ONLY
    # non-`new` events (reopened, revised) past that floor.
    _, seed_event_id = _seed_posting(engine, title="Seed Role", slug="seed", kind="new")
    _, reopened_event_id = _seed_posting(engine, title="Reopened Role", slug="reopened-only", kind="reopened")
    _, revised_event_id = _seed_posting(engine, title="Revised Role", slug="revised-only", kind="revised")
    with engine.connect() as conn:
        profile = profile_view_from_row(get_profile(conn))
        result = select_new_matches(conn, seed_event_id, profile, settings)
    assert result.is_empty
    assert result.max_event_id == max(reopened_event_id, revised_event_id)
    assert result.max_event_id > seed_event_id


def test_items_sorted_by_score_descending(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = _engine(settings)
    # target_titles favors an exact match; a very different title scores much lower
    # on title_match, giving a robust (non-tied) score separation.
    _seed_profile(engine, target_titles=("Backend Engineer",))
    _seed_posting(engine, title="Backend Engineer", slug="high-score")
    _seed_posting(engine, title="Marketing Intern", slug="low-score")
    with engine.connect() as conn:
        profile = profile_view_from_row(get_profile(conn))
        result = select_new_matches(conn, 0, profile, settings)
    assert len(result.items) == 2
    scores = [i.score for i in result.items]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[1]
    assert result.items[0].title == "Backend Engineer"


def test_selection_agrees_with_top_on_ineligible_hiding(tmp_path: Path) -> None:
    """select_new_matches and rank_open_postings (which backs `top`) must agree on
    which posting is hidden as ineligible for the same DB state (Step 4 note)."""
    from boardwatch.cli.top_cmd import rank_open_postings

    settings = _settings(tmp_path)
    engine = _engine(settings)
    _seed_profile(engine)
    facts = Facts(highest_degree="none")
    policy = Policy(families={"degree": "blocker"})
    with engine.begin() as conn:
        save_eligibility(
            conn, facts_json=facts_payload(facts), policy_json=policy.model_dump(mode="json")
        )
    ineligible_id, _ = _seed_posting(
        engine, title="Ineligible Role", slug="ineligible-top", body=DEGREE_BODY
    )
    eligible_id, _ = _seed_posting(
        engine, title="Eligible Role", slug="eligible-top", body=PLAIN_BODY
    )
    run_eligibility(engine, settings)  # same DB state for both reads below

    with engine.connect() as conn:
        profile = profile_view_from_row(get_profile(conn))
        notify_result = select_new_matches(conn, 0, profile, settings)
    notify_ids = {i.posting_id for i in notify_result.items}

    top_results = rank_open_postings(engine, settings, limit=10, only_new=True)
    top_ids = {p.posting_id for p in top_results.visible}

    assert ineligible_id not in notify_ids
    assert ineligible_id not in top_ids
    assert eligible_id in notify_ids
    assert eligible_id in top_ids
