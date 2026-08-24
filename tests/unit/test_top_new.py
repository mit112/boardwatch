"""--new restricts the shortlist to postings with a `new` event past the digest cursor.

The interaction with eligibility hiding matters: hiding happens BEFORE the limit
(D-P2-11), and --new must narrow the candidate set without reordering or re-widening it.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import insert
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.clock import utcnow
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.events import append_event
from boardwatch.store.queries import insert_run, save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings

runner = CliRunner()

# The company slug must NOT collide with seeded_events' (greenhouse, acme): `init`
# upserts greenhouse:acme-p5, then the fixture's plain INSERT of greenhouse:acme is a
# different row, so the two can coexist (the plan's "acme" collided and the seed
# crashed with an IntegrityError).
PROFILE_INPUT = "3\nacme-p5\nBackend engineer: Python, Go, PostgreSQL.\n\n\n\nn\nn\n"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


def _run(data_dir: Path, args: list[str], stdin: str | None = None):
    return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=stdin)


def test_new_shows_only_postings_with_a_new_event_past_the_cursor(
    env: Path, seeded_events
) -> None:
    assert _run(env, ["init"], PROFILE_INPUT).exit_code == 0
    seeded_events(env)
    result = _run(env, ["top", "--new"])
    assert result.exit_code == 0
    # alpha and beta carry `new`; gamma (reopened) and delta (revised) do not.
    assert "alpha" in result.stdout
    assert "beta" in result.stdout
    assert "gamma" not in result.stdout
    assert "delta" not in result.stdout
    assert "boardwatch show" in result.stdout
    assert "boardwatch track add" in result.stdout


def test_new_is_empty_after_a_digest_consumes_the_window(env: Path, seeded_events) -> None:
    assert _run(env, ["init"], PROFILE_INPUT).exit_code == 0
    seeded_events(env)
    assert _run(env, ["digest"]).exit_code == 0
    result = _run(env, ["top", "--new"])
    assert result.exit_code == 0
    assert "nothing new" in result.stdout


def test_without_new_the_full_shortlist_is_unchanged(env: Path, seeded_events) -> None:
    assert _run(env, ["init"], PROFILE_INPUT).exit_code == 0
    seeded_events(env)
    result = _run(env, ["top"])
    assert result.exit_code == 0
    for title in ("alpha", "beta", "gamma", "delta"):
        assert title in result.stdout


def test_new_respects_the_limit(env: Path, seeded_events) -> None:
    assert _run(env, ["init"], PROFILE_INPUT).exit_code == 0
    seeded_events(env)
    result = _run(env, ["top", "1", "--new"])
    assert result.exit_code == 0
    shown = [t for t in ("alpha", "beta") if t in result.stdout]
    assert len(shown) == 1


# ---------------------------------------------------------------------------
# A5: hide-before-limit must hold for --new too. The four tests above would pass
# against a limit-before-hide implementation (alpha/beta tie and neither is
# ineligible), so this test seeds two postings with deterministically unequal
# scores, persists the higher-scoring one as ineligible, and asserts the eligible
# one survives `top 1 --new`.
# ---------------------------------------------------------------------------

DEGREE_BODY = "We are hiring a backend engineer. A Bachelor's degree is required."
PLAIN_BODY = "Python and Go services with PostgreSQL."


def _seed_profile(engine) -> None:
    ensure_schema(engine)
    with engine.begin() as conn:
        save_profile(
            conn, text="Backend engineer.", target_titles=[], exclude_titles=[],
            locations=[], remote_only=False, skills=[], taxonomy_version="t",
            resume_max_pages=1,
        )


def _seed_two_with_new_events(data_dir: Path) -> tuple[int, int]:
    """(recent_id, older_id): two open postings, each with a `new` event past the cursor.

    posted_at is the ONLY scoring signal (the profile has no skills, targets or
    locations), so the recent posting deterministically outranks the older one:
    recency 1.0 vs exp(-ln2 * 30/14) at the default 14-day half-life.
    """
    engine = get_engine(data_dir)
    ensure_schema(engine)
    run_id = insert_run(engine)
    now = utcnow()
    recent_id: int | None = None
    older_id: int | None = None
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="Acme A5", provider="greenhouse", slug="acme-a5",
                    source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )
        for title, body, posted_at, recent in (
            ("Recent Role", DEGREE_BODY, now, True),
            ("Older Role", PLAIN_BODY, now - timedelta(days=30), False),
        ):
            job_id = int(
                conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0]
            )
            posting_id = int(
                conn.execute(
                    insert(postings).values(
                        company_id=company_id, job_id=job_id,
                        provider_posting_id=f"pp-{title.lower()}", title=title,
                        normalized_title=title.lower(), url=f"https://example.test/{title.lower()}",
                        locations_json=["Remote"], remote_policy="remote",
                        posted_at=posted_at, first_seen_at=now, last_seen_at=now,
                        status="open", consecutive_missing=0, content_hash=f"hh-{title.lower()}",
                        body_text=body,
                    )
                ).inserted_primary_key[0]
            )
            conn.execute(
                insert(posting_versions).values(
                    posting_id=posting_id, content_hash=f"hh-{title.lower()}",
                    body_text=body, captured_at=now, capture_reason="new",
                )
            )
            append_event(conn, posting_id, "new", run_id)
            if recent:
                recent_id = posting_id
            else:
                older_id = posting_id
    assert recent_id is not None and older_id is not None
    return recent_id, older_id


def test_new_hides_ineligible_before_the_limit(env: Path) -> None:
    """A5: --new narrows the candidate set, but hiding still happens BEFORE the limit."""
    engine = get_engine(env)
    _seed_profile(engine)
    recent_id, older_id = _seed_two_with_new_events(env)
    assert recent_id != older_id
    # Persist the higher-scoring (recent) posting as ineligible and the lower one as
    # eligible through the real engine + store, exactly what `eligibility run` does.
    assert _run(env, ["eligibility", "facts", "set", "highest_degree", "none"]).exit_code == 0
    assert _run(env, ["eligibility", "policy", "set", "degree", "blocker"]).exit_code == 0
    assert _run(env, ["eligibility", "run"]).exit_code == 0
    # top 1 --new: the #1-ranked posting is ineligible; hide-before-limit must still
    # surface the eligible posting below it rather than returning an empty shortlist.
    result = _run(env, ["top", "1", "--new"])
    assert result.exit_code == 0
    assert "Older Role" in result.stdout
    assert "Recent Role" not in result.stdout
    assert "hidden as ineligible" in result.stdout
    # Explicit ordering across two visible rows: --include-ineligible shows both in
    # score order, higher (recent) first, lower (older) second. `--include-handled` because the
    # `top 1 --new` above recorded "Older Role" as `seen` (P6 slice 2), which would otherwise
    # hide it here and make the ordering assertion vacuous.
    both = _run(env, ["top", "2", "--new", "--include-ineligible", "--include-handled"])
    assert both.exit_code == 0
    assert "Recent Role" in both.stdout
    assert "Older Role" in both.stdout
    assert both.stdout.index("Recent Role") < both.stdout.index("Older Role")
