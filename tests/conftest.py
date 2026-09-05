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

from boardwatch.store.db import FAST_SCHEMA_ENV, ensure_schema, get_engine
from boardwatch.store.queries import save_profile
from boardwatch.store.tables import companies, jobs, posting_versions, postings, runs
from boardwatch.tailor.render.latex import resolve_template

# ---------------------------------------------------------------------------------------
# A real, tectonic-compileable `resume_template.tex` (the bundled default, minus its
# placeholder identity) for any fixture standing in for a properly configured user's config
# dir.
#
# T2 made `resolve_template` fail closed on a config dir that is missing this file rather
# than silently falling back to the bundled placeholder header/education ("Your Name",
# "you@example.com", "555 555 5555", "Example University", "Example Field") — and
# `_validate_template`'s placeholder-phrase catalog then refuses a config-dir template that
# is an unedited copy of the bundled one. Neither `boardwatch init` nor `tailor init` writes
# this file, so every fixture that builds its own config dir and then reaches a real render
# needs one written explicitly, exactly as a properly set-up user's config dir would carry.
#
# Centralised here rather than re-derived per module: it was the same six-line literal in
# four test modules before this fixed it once.
TEST_RESUME_TEMPLATE = (
    resolve_template(None)
    .replace("Your Name", "Test Person")
    .replace("you@example.com", "test@example.org")
    .replace("555 555 5555", "555 555 0000")
    .replace("Example University", "Test University")
    .replace("Example Field", "Test Field")
)


def write_test_resume_template(config_dir: Path) -> None:
    """Write `TEST_RESUME_TEMPLATE` to `{config_dir}/resume_template.tex`, unless a template
    that is not the bundled placeholder is already there. Idempotent so it composes with a
    caller that may have written its own template earlier in the same fixture (or wants to opt
    out by writing first).

    The placeholder exception is T31: `boardwatch init` now SEEDS the bundled template into the
    config dir, so a fixture that builds a properly configured user (`init` + `tailor init` +
    this) finds a file already present and would otherwise be left holding the unedited
    placeholder identity — which `_validate_template` then refuses, exactly as it should for a
    real user who has not edited it yet. A test user IS edited, so the seed is overwritten and a
    caller's own template still wins.
    """
    target = config_dir / "resume_template.tex"
    if target.is_file() and target.read_text(encoding="utf-8") != resolve_template(None):
        return
    target.write_text(TEST_RESUME_TEMPLATE, encoding="utf-8")


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

    Also pins `BOARDWATCH_CONFIG_DIR` to its own empty scratch dir, no opt-out, closing the same
    shape of hazard one root over (D-281: a run isolated only by `DATA_DIR` still reads the live
    `resume.yaml` and career-profile bundle) — this was tracked here as a known gap until T17.
    Packaged defaults (the bundled `rules.yaml` and friends) are still read from the package when
    the config dir lacks a file, so tests that read real packaged config on purpose are
    unaffected. What breaks is a test that silently read Mit's live `resume.yaml`, career-profile
    bundle, or `resume_template.tex`; the fix in each case is a fixture that builds a properly
    configured user (`boardwatch init` + `tailor init` + `write_test_resume_template`), never an
    opt-out from this pin.

    Pinning the config dir also closes the `data_dir`-in-`config.toml` hole for free
    (`settings.py`: `load_settings` prefers a `data_dir` key in `config.toml` over
    `BOARDWATCH_DATA_DIR`) — the scratch config dir this fixture hands out has no `config.toml`,
    so that key can never be present.
    """
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path_factory.mktemp("bw-data")))
    # T16. `ensure_schema` replays the 27-migration chain on every fresh store the suite builds,
    # at ~93 ms each. With the switch on it replays the DDL that same chain produces instead,
    # at ~2.9 ms, and the resulting schema is byte-identical — triggers, indexes and the alembic
    # stamp included (`test_the_fast_schema_path_produces_the_same_schema_as_the_migration_chain`).
    #
    # Set HERE and nowhere else: no CLI path reads this variable, and `ensure_schema` additionally
    # refuses the shortcut on any database that is not completely empty, so a real store migrates
    # whatever the environment says.
    monkeypatch.setenv(FAST_SCHEMA_ENV, "1")
    # T17. The config dir, pinned the same way and for the same reason, closing the gap this
    # fixture's docstring named and left open: a run isolated only by the data dir still reads the
    # live `resume.yaml`, career-profile bundle and `resume_template.tex`. Packaged defaults are
    # read from the PACKAGE when the config dir lacks a file, so tests that read real packaged
    # config on purpose are unaffected. This also closes the `data_dir`-in-`config.toml` hole for
    # free — an empty scratch dir has no `config.toml` for `load_settings` to prefer.
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path_factory.mktemp("bw-config")))


@pytest.fixture(autouse=True)
def _never_reach_the_real_queue_root(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point the run hook's delivery-queue root at a scratch dir for EVERY test. No opt-out.

    The same hazard as `_never_reach_the_real_data_dir`, one root over: `pipeline/runner.py` syncs
    the delivery queue at the end of every run, and `DEFAULT_QUEUE_ROOT` is `~/boardwatch-queue`.
    Thirteen test modules call `run_pipeline`, so without this the suite writes lead folders for
    fake companies into the owner's real queue — measured, not hypothetical — and, once the owner
    has drained a lead into `_applied/`, `reconcile_queue` reads the *test's* empty store and moves
    that folder back out. A test run would silently un-apply real applications.

    Patched by name on the CONSUMER, `pipeline.runner`, because that is where the hook resolves the
    root; patching `delivery.queue`'s definition would not reach the binding the hook reads. Any
    test that wants its own root still wins — it patches the same name after this fixture has run.

    The import is deferred for the reason `backfill_identities` gives below: this module is
    imported at collection time for every test in the repo, so a module-scope import here would
    couple repo-wide collection to `pipeline.runner` importing cleanly.
    """
    from boardwatch.pipeline import runner

    monkeypatch.setattr(runner, "DEFAULT_QUEUE_ROOT", tmp_path_factory.mktemp("bw-queue"))


@pytest.fixture(autouse=True)
def _isolated_host_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test its own `HostPacing` registry. No opt-out.

    T41 (D-475) moved per-host locks and last-request timestamps off the `Fetcher` instance
    onto a registry shared by every `Fetcher` in the PROCESS — the whole point being that two
    instances built by the same process pace a shared host together. Left un-isolated, that
    sharing bleeds across tests too: the suite builds ~47 `Fetcher`s directly, and a fake host
    spelling reused by two test modules (`https://ok.example/x` appears in several) would carry
    the first test's last-request timestamp into the second, adding up to a real `time.sleep` of
    up to `per_host_delay_seconds` per shared fake host per test. Swapping in a fresh registry
    before each test is the isolation `_never_reach_the_real_data_dir` gives the store, one root
    over, for the same reason: production sharing must not become test-to-test sharing.

    The import is deferred for the reason `_never_reach_the_real_queue_root` gives above: this
    module is imported at collection time for every test in the repo.
    """
    from boardwatch.core import politeness

    monkeypatch.setattr(politeness, "_PROCESS_PACING", politeness.HostPacing())


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
