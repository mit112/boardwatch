"""Shared seeding for the P6 dedup tests (Tasks 5-8).

At the tree root rather than under tests/unit/ because tests/cli/test_identities_cmd.py
needs the same corpus.
"""

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings, runs

# ---------------------------------------------------------------------------------------
# Make rich agree that captured test output is not a terminal.
#
# Executed at conftest IMPORT time, deliberately, NOT in a fixture: `Console.__init__`
# resolves `_color_system` eagerly, and this program builds module-level consoles
# (`cli/eligibility_cmd.py:66`, `cli/top_cmd.py:50`, ...) at import. A fixture runs too late
# to change what those already baked in.
#
# Nothing here is a tty, but rich's `is_terminal` is True whenever `FORCE_COLOR` is set to
# anything non-empty or `TTY_COMPATIBLE=1` — and a CI runner may set either. That one
# property gates TWO unrelated behaviours, so a runner supplying it breaks assertions two
# different ways:
#
# * Width. `Console.size` returns a hard-coded (80, 25) when `is_dumb_terminal`
#   (`is_terminal` AND `TERM` in ("dumb", "unknown")), and that branch sits ABOVE the
#   `COLUMNS` lookup, silently overriding it. Long cells fold across lines and substring
#   assertions over them fail. This is why
#   `test_abstain_names_rules_that_have_never_been_detected` failed on ubuntu/3.12 alone
#   while passing on the eight other matrix jobs and locally.
# * Colour. With a colour system resolved, `ReprHighlighter` — on by default, and NOT
#   disabled by `markup=False` — wraps leading integers in escape codes. That breaks plain
#   substring assertions and makes `--json` output unparseable.
#
# `is_terminal` is what gets normalised, because it is the single root of both. Pinning only
# `TERM` fixes width and CAUSES the colour failures; that was a first attempt at this and it
# went red under `TERM=xterm FORCE_COLOR=1`. `TERM` is pinned too, as defence for anything
# that makes `is_terminal` true by another route (an explicit `force_terminal`).
#
# No test in the repo asserts on ANSI output, so nothing wants the suppressed behaviour.
#
# `COLUMNS` and `LINES` are popped for a SECOND, independent reason, and popping them is what
# makes a per-test `monkeypatch.setenv("COLUMNS", ...)` mean anything at all. Since rich 15.0.0
# `Console.__init__` resolves width EAGERLY — it reads `COLUMNS` itself and stores the result in
# `self._width` — and `Console.size` then returns `self._width` verbatim, never re-reading the
# environment. So a console built at import under an ambient `COLUMNS` is frozen at that width
# for the life of the process, and every later `setenv` is a no-op. Popping here, before the
# module-level consoles exist, leaves `_width` None, which is the only state in which
# `Console.size`'s live `COLUMNS` lookup is reachable.
#
# This is not hypothetical: `COLUMNS=80 uv run pytest -k abstain` reproduces the ubuntu/3.12 CI
# failure byte-for-byte, because the console freezes at 80 and the 35-character
# `work_auth:eu_authorization_required` folds inside a 25-character table column.
#
# `GITHUB_ACTIONS` and `PY_COLORS` are popped for a THIRD reason, and they are not rich's at all
# — they are typer's. `typer/rich_utils.py` bakes a module constant at IMPORT time:
#
#     FORCE_TERMINAL = True if getenv("GITHUB_ACTIONS") or getenv("FORCE_COLOR")
#                      or getenv("PY_COLORS") else None
#
# and passes it as `force_terminal=` to the console it builds for every `--help` render. So on
# any GitHub Actions runner, help output is styled no matter what rich would have decided, and
# `ReprHighlighter` splits an option name across escape codes — which is why
# `assert "--new" in result.stdout` failed on all three ubuntu jobs while the flag rendered
# perfectly. Popping only rich's two vars left typer's third trigger live: the normalisation was
# two-thirds complete. `GITHUB_ACTIONS=true uv run pytest -k top_help_lists` reproduces it
# locally, byte-for-byte, and is the check to run before trusting this block.
#
# Nothing in `src/` reads `GITHUB_ACTIONS`, so popping it takes no behaviour away; a dozen test
# modules already `monkeypatch.delenv` it one fixture at a time for this same reason.
# ---------------------------------------------------------------------------------------
os.environ.pop("FORCE_COLOR", None)
os.environ.pop("TTY_COMPATIBLE", None)
os.environ.pop("GITHUB_ACTIONS", None)
os.environ.pop("PY_COLORS", None)
os.environ.pop("COLUMNS", None)
os.environ.pop("LINES", None)
os.environ["TERM"] = "xterm"


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


@pytest.fixture(autouse=True)
def _never_reach_the_real_data_dir(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point `BOARDWATCH_DATA_DIR` at a scratch dir for EVERY test. Autouse, no opt-out.

    This exists because the suite migrated Mit's production database. `load_settings()` falls
    back to `default_data_dir()` when no `data_dir` is passed, and `default_data_dir()` reads
    this variable or else returns the real user data dir. Several fixtures — `dedup_env` below
    among them — set only `BOARDWATCH_CONFIG_DIR`, so any CLI test reaching `load_settings()`
    without `--data-dir` resolved to the live ~1.4 GB store and ran `ensure_schema` against it.

    What that costs is not a dirty temp file. `ensure_schema` runs alembic to HEAD, so a branch
    adding a migration silently migrates the production store the first time its tests run — and
    the unattended daily driver then executes `main`'s tree, which has no such revision, and dies
    with `Can't locate revision`. That is D-279 exactly, and it recurred on 2026-08-23 with
    `p_lane_companies`. Gate P3 counts CONSECUTIVE clean scheduled ticks, so one such failure
    costs a day and resets the streak.

    A redirect rather than a hard failure: a test that wanted the default now gets an empty
    store. Any fixture that sets the variable itself still wins — it runs after this one and its
    `monkeypatch.setenv` overwrites this.

    **This closes the env-var route, not every route.** `load_settings` prefers a `data_dir` key
    in the real `config.toml` over this variable (`settings.py`: `data_dir or file_data_dir or
    default_data_dir()`), and this fixture deliberately does not pin `BOARDWATCH_CONFIG_DIR`, so
    a machine whose config pins `data_dir` would still resolve to that path. Nothing in the
    codebase ever WRITES that key and Mit's config does not carry one, so the hole is not open
    today — but do not read this fixture as a proof that no test can reach a real store.

    Deliberately NOT extended to `BOARDWATCH_CONFIG_DIR`. That variable has the same shape of
    hazard (D-281: a run isolated only by `DATA_DIR` still reads the live `resume.yaml` and
    career-profile bundle), but many tests read real packaged config on purpose, so pinning it
    here would be a much larger behavioural change than this fix should carry. It remains a
    known gap.
    """
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path_factory.mktemp("bw-data")))


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
