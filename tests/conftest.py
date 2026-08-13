"""Shared seeding for the P6 dedup tests (Tasks 5-8).

At the tree root rather than under tests/unit/ because tests/cli/test_identities_cmd.py
needs the same corpus.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings, runs


@pytest.fixture(autouse=True)
def _non_dumb_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin `TERM` so rich resolves console width from `COLUMNS`, not from a dumb-terminal
    fallback.

    `Console.size` returns a hard-coded (80, 25) when `is_dumb_terminal` — `TERM` in
    ("dumb", "unknown") AND `is_terminal` — and that branch sits ABOVE the `COLUMNS`
    lookup, so it silently overrides it. `is_terminal` is true whenever `FORCE_COLOR` or
    `TTY_COMPATIBLE=1` is set, which a CI runner may do even though nothing is a tty. A
    runner supplying both therefore renders every table at 80 columns regardless of what
    a test asked for, folding long cells across lines and breaking any substring
    assertion over them. This is why `test_abstain_names_rules_that_have_never_been_detected`
    failed on ubuntu/3.12 alone while passing on the eight other matrix jobs and locally.

    Autouse and repo-wide because the exposure is not specific to that test: every
    assertion over rich-rendered CLI output inherits it.
    """
    monkeypatch.setenv("TERM", "xterm")


# ---------------------------------------------------------------------------------------
# P6 dedup seeding (Tasks 5-8).
#
# `identical=True` is the exact_quad shape: same company, title, locations, content_hash and
# body_text, differing ONLY in provider_posting_id (the (company_id, provider_posting_id)
# unique key forbids sharing that). This is the one thing the plan's dedup tests all rest on,
# so it is centralised rather than re-derived per module.
#
# `first_seen_at` DESCENDS with the offset, so `posting_ids[-1]` is the earliest-seen row and
# `posting_ids[0]` is the lowest id. That inversion is deliberate. Survivor election is
# "earliest first_seen_at, with posting_id as the tiebreak" (design §5.1); if the fixture let
# both orderings agree, an implementation that elected purely by posting_id would pick the
# same winner and no test could tell the two apart. Here they disagree, so it is detectable.
# ---------------------------------------------------------------------------------------

P6_NOW = datetime(2026, 8, 1, 12, 0, 0)


@dataclass(frozen=True)
class DedupSeed:
    engine: Engine
    data_dir: Path
    company_id: int
    posting_ids: tuple[int, ...]
    run_id: int
    now: datetime


@pytest.fixture()
def dedup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Config dir == data dir, so a CLI-driven `eligibility run` and the engine under test
    read the same facts and policy. Split, `eligibility facts set` writes somewhere the
    ranker never looks and the ineligible fixtures silently do nothing."""
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return tmp_path / "data"


@pytest.fixture()
def seed_dedup(dedup_env: Path) -> Callable[..., DedupSeed]:
    def seed(*, count: int = 1, identical: bool = True, body: str | None = None) -> DedupSeed:
        engine = get_engine(dedup_env)
        ensure_schema(engine)
        posting_ids: list[int] = []
        with engine.begin() as conn:
            # rank_open_postings requires a profile row; exclude_titles is empty on purpose so
            # nothing here is hard-filtered before it reaches the dedup step under test.
            save_profile(
                conn,
                text="Backend engineer.",
                target_titles=[],
                exclude_titles=[],
                locations=[],
                remote_only=False,
                skills=[],
                taxonomy_version="t",
                resume_max_pages=1,
            )
            # count_by_source (Task 8) requires a real run_id.
            run_id = int(
                conn.execute(
                    insert(runs).values(started_at=P6_NOW, boards_attempted=0)
                ).inserted_primary_key[0]
            )
            company_id = int(
                conn.execute(
                    insert(companies).values(
                        name="Acme",
                        provider="greenhouse",
                        slug="acme-dedup",
                        source="user",
                        watched=True,
                    )
                ).inserted_primary_key[0]
            )
            for offset in range(count):
                title = "Backend Engineer" if identical else f"Backend Engineer {offset}"
                text = body if body is not None else "We are hiring a backend engineer."
                content_hash = "hh-same" if identical else f"hh-{offset}"
                job_id = int(
                    conn.execute(insert(jobs).values(created_at=P6_NOW)).inserted_primary_key[0]
                )
                posting_id = int(
                    conn.execute(
                        insert(postings).values(
                            company_id=company_id,
                            job_id=job_id,
                            provider_posting_id=f"pp-{offset}",
                            title=title,
                            normalized_title=title.casefold(),
                            url=f"https://boards.greenhouse.io/acme/jobs/{offset}",
                            # A real list, not a JSON string: locations_json is a JSON column
                            # and a SELECT hands back a list. The Task 6 round-trip test
                            # depends on this being non-empty.
                            locations_json=["Remote"],
                            remote_policy="remote",
                            posted_at=P6_NOW - timedelta(days=offset),
                            # Descending: the LAST posting is the earliest-seen. See above.
                            first_seen_at=P6_NOW - timedelta(days=offset),
                            last_seen_at=P6_NOW,
                            status="open",
                            consecutive_missing=0,
                            content_hash=content_hash,
                            body_text=text,
                        )
                    ).inserted_primary_key[0]
                )
                conn.execute(
                    insert(posting_versions).values(
                        posting_id=posting_id,
                        content_hash=content_hash,
                        body_text=text,
                        captured_at=P6_NOW,
                        capture_reason="new",
                    )
                )
                posting_ids.append(posting_id)
        return DedupSeed(
            engine=engine,
            data_dir=dedup_env,
            company_id=company_id,
            posting_ids=tuple(posting_ids),
            run_id=run_id,
            now=P6_NOW,
        )

    return seed


@pytest.fixture()
def backfill_identities() -> Callable[..., int]:
    """Compute and store identities for a seeded corpus, the way `identities backfill` does.

    `posting_ids=None` covers everything; passing a subset is the ONLY way to produce the
    partial-coverage corpus that Tasks 7 and 8 use to pin the completeness gate.
    """

    def backfill(seed: DedupSeed, posting_ids: Sequence[int] | None = None) -> int:
        # The imports are inside the function on purpose. tests/conftest.py is imported at
        # collection time for EVERY test in the repo, so a module-level import of a module
        # added by a later task would break collection repo-wide at the previous commit and
        # at any bisect point between them.
        from boardwatch.core.posting_identity import compute_identities
        from boardwatch.store.identity_queries import load_identity_inputs, write_identities

        written = 0
        with seed.engine.begin() as conn:
            for row in load_identity_inputs(conn, posting_ids):
                written += write_identities(
                    conn, row.posting_id, compute_identities(row), now=seed.now
                )
        return written

    return backfill
