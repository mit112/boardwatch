"""The `requirement_terms` memo behind the queue's live coverage column.

`GET /api/queue` recomputes coverage for every row on every render. Measured against the live
corpus — 557 delivered bodies, 3.38 M characters — the parse alone is 3.59 ms per body, ~1.9 s for
a queue of 540, growing with the corpus. Every render asks the same question and gets the same
answer, because `posting_versions` is append-only (the `posting_versions_no_update` /
`posting_versions_no_delete` triggers), so a `posting_version_id` fixes its `body_text` forever.

**The call counts are the assertions here; the clock is a smoke check.** Every test below that
matters monkeypatches `api.requirement_terms` with a counting wrapper and asserts an exact number
of real parses. That is deterministic on any machine, and it is the only shape that can tell a
working memo from a `dict` that is written to and never read: both return correct payloads and both
are fast enough on a two-row fixture. The one timing test asserts a ratio and SKIPS rather than
fails when the machine is too noisy to distinguish the passes, because a flaky timing test is worse
than no timing test.

Three invalidation tests exist because the memo's identity has three parts, and each is asserted in
the only way that discriminates:

* **The taxonomy version** — under an override that leaves every pattern alone and changes only the
  version. The payload is byte-identical across the change, so the recount cannot be explained by
  "the answers moved"; the only thing that can explain it is the version.
* **The master résumé** — asserted in both directions in one test: an edit that changes a canonical
  skill discards the memo, and an edit that changes none keeps it AND yields the identical payload.
  The second half is the proof that keeping it is sound rather than a leak of staleness.
* **The store** — implicit in every test, since each gets its own `tmp_path` data dir. A version id
  is unique inside one store only, and the suite builds a fresh store per test in one process.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, insert

from boardwatch.core.settings import load_settings
from boardwatch.delivery import api
from boardwatch.delivery.api import _TERM_CACHE, ApiContext, queue_payload
from boardwatch.extract.taxonomy import (
    Taxonomy,
    bundled_taxonomy_text,
    load_taxonomy,
)
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import CurrentVersion
from boardwatch.store.tables import artifacts, companies, jobs, posting_versions, postings
from boardwatch.tailor.coverage import (
    coverage_report,
    coverage_to_dict,
    requirement_terms,
    resume_fact_skills,
)
from boardwatch.tailor.load import load_resume_bytes

NOW = datetime(2026, 8, 26, 12, 0, 0)

# Three bodies whose recognised term sets are pairwise DISJOINT, so a memo that answered one from
# another's entry is visible in the payload and not only in a count. None carries a qualifications
# header, which is deliberate: that is the whole-body fallback path, and it is the expensive one
# the live corpus's 3.59 ms/body average is made of.
BODY_PY = "We work in Python and Django every day and review each other's code carefully."
BODY_RUST = "We work in Rust and Kubernetes every day and review each other's code carefully."
BODY_JS = "We work in JavaScript and React every day and review each other's code carefully."

# The master résumé, authored here rather than taken from `scaffold_template()` so that the three
# variants differ in exactly one controlled way each. `_A` carries the canonical skills Python and
# Rust; `_FEWER` drops Rust (a different fingerprint); `_REWORDED` changes bytes the taxonomy does
# not recognise (the same fingerprint).
RESUME_A = """\
header:
  - "Test Owner"
  - "owner@example.com"
education:
  - "BSc Computer Science — Example University — 2020"
skill_groups:
  - label: "Languages"
    items: ["Python", "Rust"]
entries:
  - entry_id: "one"
    heading: "Engineer — Example Co — 2021"
    bullets:
      - bullet_id: "one-1"
        text: "Shipped internal tooling used by the whole team"
"""
RESUME_FEWER = RESUME_A.replace('["Python", "Rust"]', '["Python"]')
RESUME_REWORDED = RESUME_A.replace(
    "Shipped internal tooling used by the whole team",
    "Shipped the internal tooling that the whole team relies on",
)

# ------------------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _scratch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BOARDWATCH_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture(autouse=True)
def _clean_memo() -> Iterator[None]:
    """The memo is process-global, so it is emptied on BOTH sides of every test here.

    The store component of the cache identity already makes a cross-store hit impossible, but a
    call count that relied on `tmp_path` being unique would be asserting the fixture rather than
    the memo. Cleared before, so nothing another module cached can answer a question asked here;
    cleared after, so nothing cached here can answer another module's.
    """
    _TERM_CACHE.clear()
    yield
    _TERM_CACHE.clear()


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path / "data")
    ensure_schema(eng)
    return eng


@pytest.fixture()
def ctx(tmp_path: Path) -> ApiContext:
    out_root = tmp_path / "out"
    queue_root = tmp_path / "queue"
    out_root.mkdir()
    queue_root.mkdir()
    return ApiContext(
        settings=load_settings(),
        out_root=out_root.resolve(),
        queue_root=queue_root.resolve(),
        owner_name="Test Owner",
        platform="darwin",
    )


@dataclass
class Parses:
    """How many JD bodies were really parsed. The instrument of this whole file."""

    n: int = 0


@pytest.fixture()
def parses(monkeypatch: pytest.MonkeyPatch) -> Parses:
    """Count real `requirement_terms` calls, delegating to the shipped one.

    Patched on `api`, which is where the memo looks the name up, and delegating rather than
    stubbing so that every payload assertion in this file is made against the real coverage
    numbers. A stub would make "the payload is unchanged" a statement about the stub.
    """
    counter = Parses()
    real = api.requirement_terms

    def counted(jd_body_text: str, taxonomy: Taxonomy) -> tuple[frozenset[str], str]:
        counter.n += 1
        return real(jd_body_text, taxonomy)

    monkeypatch.setattr(api, "requirement_terms", counted)
    return counter


# -------------------------------------------------------------------------------------- seeding


def _deliver(conn: Connection, key: str, *, body: str) -> int:
    """One delivered, unapplied lead: company, job, posting, frozen version, tailored artifact.

    Returns its `posting_id`. Shaped after `test_web_server.py`'s helper of the same name, minus
    the parts no test here reads (PDFs, run ids, eligibility rows).
    """
    company_id = int(
        conn.execute(
            insert(companies).values(
                name=f"Acme {key}",
                provider="greenhouse",
                slug=f"acme-{key}",
                source="user",
                watched=True,
            )
        ).inserted_primary_key[0]
    )
    job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    posting_id = int(
        conn.execute(
            insert(postings).values(
                company_id=company_id,
                job_id=job_id,
                provider_posting_id=key,
                title="Software Engineer",
                normalized_title="software engineer",
                url="https://boards.test/apply",
                locations_json=["Boston, MA"],
                remote_policy="remote",
                posted_at=NOW - timedelta(days=3),
                first_seen_at=NOW,
                last_seen_at=NOW,
                status="open",
                consecutive_missing=0,
                content_hash=f"hash-{key}",
                body_text=body,
            )
        ).inserted_primary_key[0]
    )
    version_id = int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id,
                content_hash=f"v-{key}",
                body_text=body,
                captured_at=NOW,
                capture_reason="new",
            )
        ).inserted_primary_key[0]
    )
    conn.execute(
        insert(artifacts).values(
            posting_version_id=version_id,
            kind="resume_tailored",
            uri=f"/out/{key}/tailored-{posting_id}.typ",
            generator="boardwatch.tailor",
            media_type="text/x-tex",
            meta_json={"pdf_uri": None},
            created_at=NOW,
            run_id=None,
        )
    )
    return posting_id


def _write_resume(ctx: ApiContext, text: str) -> None:
    path = ctx.settings.config_dir / "resume.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _render(engine: Engine, ctx: ApiContext) -> dict[str, Any]:
    with engine.connect() as conn:
        return queue_payload(conn, ctx)


def _rows_by_id(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {row["posting_id"]: row for row in payload["rows"]}


# ------------------------------------------------------------------------------- the memo itself


def test_a_second_render_reparses_nothing_and_returns_the_identical_payload(
    engine: Engine, ctx: ApiContext, parses: Parses
) -> None:
    """The load-bearing test. Two bodies, two renders, exactly two parses.

    Both halves have to be here. `parses.n == 0` on the second render is the only assertion that
    fails against a memo that stores nothing (that version would report 4), and equality of the
    payloads is the only assertion that fails against a memo that serves the wrong entry (that
    version would report 2 and be wrong). Neither catches the other's bug.
    """
    _write_resume(ctx, RESUME_A)
    with engine.begin() as conn:
        _deliver(conn, "py", body=BODY_PY)
        _deliver(conn, "rust", body=BODY_RUST)

    cold = _render(engine, ctx)
    assert parses.n == 2

    warm = _render(engine, ctx)
    assert parses.n == 2, "the second render parsed a body it had already parsed"
    assert warm == cold

    # Not vacuously equal: the coverage really was measured on both renders.
    rows = _rows_by_id(warm)
    assert [row["coverage"] for row in rows.values()] == [0.5, 0.5]


def test_the_served_coverage_matches_an_independent_parse_of_the_same_body(
    engine: Engine, ctx: ApiContext
) -> None:
    """Counted through a different path than the one that produced it.

    The expectation is rebuilt in the test from `tailor.coverage` directly — the un-memoized
    functions, over the body this test wrote — rather than from a second call to `queue_payload`.
    A memo that returned a plausible-looking but wrong term set passes a self-comparison and fails
    here.
    """
    _write_resume(ctx, RESUME_A)
    with engine.begin() as conn:
        py = _deliver(conn, "py", body=BODY_PY)
        rust = _deliver(conn, "rust", body=BODY_RUST)

    taxonomy = load_taxonomy(ctx.settings.config_dir)
    master = load_resume_bytes(
        RESUME_A.encode("utf-8"), origin=ctx.settings.config_dir / "resume.yaml"
    )
    skills = resume_fact_skills(master, taxonomy)

    rows = _rows_by_id(_render(engine, ctx))
    for posting_id, body in ((py, BODY_PY), (rust, BODY_RUST)):
        terms, source = requirement_terms(body, taxonomy)
        expected = coverage_to_dict(coverage_report(terms, skills, source))
        assert rows[posting_id]["coverage_detail"] == expected

    # And the two bodies really do disagree, so the loop above is not comparing one answer twice.
    assert rows[py]["coverage_detail"]["covered"] == ["Python"]
    assert rows[py]["coverage_detail"]["missing"] == ["Django"]
    assert rows[rust]["coverage_detail"]["covered"] == ["Rust"]
    assert rows[rust]["coverage_detail"]["missing"] == ["Kubernetes"]


def test_identical_bodies_under_different_version_ids_are_each_correct(
    engine: Engine, ctx: ApiContext, parses: Parses
) -> None:
    """Entries are keyed on `posting_version_id`, and two versions may share a body verbatim.

    The same JD posted by two companies is ordinary — an outsourced template, a reposting. Both
    rows must carry that body's coverage, and the third row's DIFFERENT body must not be answered
    from either of theirs, which is what a key that collided would do.
    """
    _write_resume(ctx, RESUME_A)
    with engine.begin() as conn:
        first = _deliver(conn, "twin-a", body=BODY_PY)
        second = _deliver(conn, "twin-b", body=BODY_PY)
        other = _deliver(conn, "other", body=BODY_RUST)

    rows = _rows_by_id(_render(engine, ctx))
    assert rows[first]["coverage_detail"] == rows[second]["coverage_detail"]
    assert rows[first]["coverage_detail"]["covered"] == ["Python"]
    assert rows[other]["coverage_detail"]["covered"] == ["Rust"]

    # All three are resident afterwards, twins included: a memo that folded the twins into one
    # entry would still be correct, but one that dropped an entry would re-parse here.
    before = parses.n
    _render(engine, ctx)
    assert parses.n == before


def test_a_queue_render_warms_the_memo_for_the_detail_render(
    engine: Engine, ctx: ApiContext, parses: Parses
) -> None:
    """One memo per process, not per endpoint.

    Opening the queue and then clicking a lead is the normal gesture, and `/api/queue/<id>` runs
    the same `_live_facts`. A cache hanging off the request, or off `ApiContext`, would parse the
    body twice for that one gesture.
    """
    _write_resume(ctx, RESUME_A)
    with engine.begin() as conn:
        posting_id = _deliver(conn, "py", body=BODY_PY)

    _render(engine, ctx)
    assert parses.n == 1

    with engine.connect() as conn:
        detail = api.detail_payload(conn, ctx, posting_id)
    assert detail is not None
    assert parses.n == 1
    assert detail["row"]["coverage"] == 0.5


# ---------------------------------------------------------------------------------- invalidation


def test_a_new_taxonomy_version_discards_the_memo_even_when_the_terms_are_unchanged(
    engine: Engine, ctx: ApiContext, parses: Parses
) -> None:
    """The version is what invalidates, not a change in the answers.

    The override is the bundled taxonomy plus one extra top-level key. `_version_of` hashes the
    whole parsed document, so the version moves; no pattern changes, so every extracted term stays
    the same. The payload is therefore identical across the change and CANNOT explain the reparse
    — only the version can. An implementation that compared term sets, or that never invalidated
    at all, reports 2 on the third render instead of 4.
    """
    _write_resume(ctx, RESUME_A)
    with engine.begin() as conn:
        _deliver(conn, "py", body=BODY_PY)
        _deliver(conn, "rust", body=BODY_RUST)

    before_version = load_taxonomy(ctx.settings.config_dir).version
    cold = _render(engine, ctx)
    assert parses.n == 2
    _render(engine, ctx)
    assert parses.n == 2

    override = ctx.settings.config_dir / "taxonomy.yaml"
    override.write_text(
        bundled_taxonomy_text() + '\nnote: "a key the version hashes but no pattern reads"\n',
        encoding="utf-8",
    )
    # The premise of this test, asserted rather than assumed: the version really did move.
    assert load_taxonomy(ctx.settings.config_dir).version != before_version

    after = _render(engine, ctx)
    assert parses.n == 4, "a new taxonomy version served terms parsed under the old one"
    assert after == cold


def test_a_changed_master_resume_discards_the_memo_and_an_unrecognised_edit_does_not(
    engine: Engine, ctx: ApiContext, parses: Parses
) -> None:
    """Both directions, because only the pair pins the behaviour.

    The résumé's fingerprint is over its CANONICAL SKILL SET — the résumé-side input coverage
    actually consumes — not its bytes. So dropping Rust rolls the generation, and rewording a
    bullet the taxonomy does not read does not. The second half is asserted together with an
    identical payload, which is what makes keeping the memo demonstrably sound rather than stale:
    if nothing the measurement reads has moved, neither has the measurement.
    """
    _write_resume(ctx, RESUME_A)
    with engine.begin() as conn:
        _deliver(conn, "rust", body=BODY_RUST)

    baseline = _render(engine, ctx)
    assert parses.n == 1
    assert baseline["rows"][0]["coverage_detail"]["covered"] == ["Rust"]

    # An edit the taxonomy cannot see: same skills, different bytes, memo retained.
    _write_resume(ctx, RESUME_REWORDED)
    assert _render(engine, ctx) == baseline
    assert parses.n == 1, "a résumé edit that changes no canonical skill threw the memo away"

    # An edit that removes a canonical skill: the generation rolls and the numbers move with it.
    _write_resume(ctx, RESUME_FEWER)
    changed = _render(engine, ctx)
    assert parses.n == 2, "a changed master résumé served terms from the previous generation"
    assert changed["rows"][0]["coverage_detail"]["covered"] == []
    assert changed["rows"][0]["coverage"] == 0.0


# --------------------------------------------------------------------------------------- the cap


def _version(version_id: int, body: str) -> CurrentVersion:
    return CurrentVersion(
        posting_version_id=version_id, posting_id=version_id, body_text=body, captured_at=NOW
    )


def test_the_cap_evicts_the_least_recently_used_and_keeps_a_recent_entry(
    parses: Parses,
) -> None:
    """Bounded, and bounded by RECENCY of use rather than of insertion.

    Driven on its own two-entry instance so the eviction is reached in four calls instead of five
    thousand. Entry 1 is inserted first and then TOUCHED, so a plain FIFO bound evicts it and an
    LRU bound evicts 2 — the assertions distinguish those, which a test that only overflowed the
    cap could not. Every recomputed value is checked against its own body, because an eviction bug
    that returned the wrong body's terms would otherwise read as a clean miss.
    """
    cache = api._TermCache(max_entries=2)
    taxonomy = load_taxonomy(Path("/nonexistent"))
    identity = ("/store", taxonomy.version, "resume-digest")
    one, two, three = _version(1, BODY_PY), _version(2, BODY_RUST), _version(3, BODY_JS)
    py, rust, js = (
        frozenset({"Python", "Django"}),
        frozenset({"Rust", "Kubernetes"}),
        frozenset({"JavaScript", "React"}),
    )

    assert cache.terms(identity, taxonomy, one)[0] == py
    assert cache.terms(identity, taxonomy, two)[0] == rust
    assert parses.n == 2

    # Touch 1, making 2 the least recently used, then admit 3 to force one eviction.
    assert cache.terms(identity, taxonomy, one)[0] == py
    assert parses.n == 2
    assert cache.terms(identity, taxonomy, three)[0] == js
    assert parses.n == 3

    # 2 was the least recently used, so it is the one that went.
    assert cache.terms(identity, taxonomy, two)[0] == rust
    assert parses.n == 4, "the least recently used entry survived an eviction it should not have"
    # 3 is recent and resident.
    assert cache.terms(identity, taxonomy, three)[0] == js
    assert parses.n == 4
    # Re-admitting 2 evicted 1, which by then carried the oldest use.
    assert cache.terms(identity, taxonomy, one)[0] == py
    assert parses.n == 5


# ------------------------------------------------------------------------------ the clock (smoke)


def _synthetic_body(index: int) -> str:
    """A JD-shaped body of about the size the live corpus averages (~5 KB) and about its cost.

    No qualifications header, deliberately: that is the whole-body fallback branch of
    `requirement_terms`, which runs every taxonomy pattern over the entire text and is where the
    live corpus's 3.59 ms per body comes from. A body with a header parses a short span instead,
    costs ~0.06 ms, and would make this test's clock unreadable.
    """
    prose = (
        "We are a growing engineering team building distributed systems that serve millions of "
        "requests every day. You will collaborate with product, design and data partners to ship "
        "user-facing features end to end, from the first sketch through rollout and measurement. "
        "We care about clear writing, small reviewable changes and a bias toward shipping. "
    ) * 14
    return f"Software Engineer, Platform ({index})\n\n{prose}\nWe use Python, Docker and React.\n"


def test_the_second_pass_over_two_hundred_bodies_is_far_faster_than_the_first() -> None:
    """A smoke check on the clock, subordinate to the call counts above.

    Skipped rather than failed when the cold pass is too quick to time: a machine under enough
    load to make these two numbers indistinguishable would produce a red build that says nothing
    about the memo, and the deterministic assertion of the same fact is `parses.n == 0` above.
    """
    taxonomy = load_taxonomy(Path("/nonexistent"))
    cache = api._TermCache()
    identity = ("/store", taxonomy.version, "resume-digest")
    versions = [_version(i, _synthetic_body(i)) for i in range(1, 201)]

    start = time.perf_counter()
    for version in versions:
        cache.terms(identity, taxonomy, version)
    cold_ms = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    for version in versions:
        cache.terms(identity, taxonomy, version)
    warm_ms = (time.perf_counter() - start) * 1000

    if cold_ms < 50:
        pytest.skip(f"cold pass was only {cold_ms:.1f} ms; too fast to time a ratio against")
    assert warm_ms * 10 < cold_ms, f"cold {cold_ms:.1f} ms vs warm {warm_ms:.1f} ms"
