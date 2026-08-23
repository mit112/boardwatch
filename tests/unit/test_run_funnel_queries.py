"""The store half of the per-run funnel (P0 item 1).

These are the tests that can catch a wrong JOIN. The pure builder cannot: hand it bad counts
and it will reconcile them faithfully. Each test below pins one scoping decision that, if
dropped, would silently inflate or deflate the funnel on real data rather than raise.

Seeded through `record_evaluation` and `record_artifact`, the production write paths, so the
rows are shaped the way real ones are.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, insert

from boardwatch.core.clock import utcnow
from boardwatch.store.artifacts import record_artifact
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.eligibility import RequirementItem, record_evaluation
from boardwatch.store.run_funnel_queries import (
    count_applied_for_postings,
    count_by_source,
    count_candidate_judged_this_run,
    count_corpus,
    count_stub_postings,
    count_stub_postings_by_company,
    count_tailored_artifacts,
    count_unattributed_evaluations,
    lead_provenance,
)
from boardwatch.store.tables import applications, companies, jobs, posting_versions, postings, runs

NOW = utcnow()
KIND, VERSION = "deterministic", "v1"
PROFILE, RULES = "ph", "rh"


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


def _run(conn: Connection) -> int:
    return int(
        conn.execute(insert(runs).values(started_at=NOW, boards_attempted=0)).inserted_primary_key[0]
    )


def _posting(
    conn: Connection, slug: str, *, status: str = "open", source: str = "user",
    body_text: str = "b",
) -> int:
    cid = int(conn.execute(insert(companies).values(
        name="Acme", provider="greenhouse", slug=f"board-{slug}", source=source, watched=True,
    )).inserted_primary_key[0])
    jid = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    return int(conn.execute(insert(postings).values(
        company_id=cid, job_id=jid, provider_posting_id=slug, title="Eng",
        normalized_title="eng", first_seen_at=NOW, last_seen_at=NOW, status=status,
        consecutive_missing=0, content_hash=slug, body_text=body_text,
    )).inserted_primary_key[0])


def _version(conn: Connection, posting_id: int, tag: str) -> int:
    return int(conn.execute(insert(posting_versions).values(
        posting_id=posting_id, content_hash=tag, body_text="b", captured_at=NOW,
        run_id=None, capture_reason="new",
    )).inserted_primary_key[0])


def _judge(
    conn: Connection,
    version_id: int,
    *,
    verdict: str = "eligible",
    run_id: int | None,
    engine_kind: str = KIND,
    profile: str = PROFILE,
    fingerprint: str | None = None,
) -> int:
    return record_evaluation(
        conn,
        posting_version_id=version_id,
        profile_hash=profile, profile_snapshot={}, rules_hash=RULES, rules_snapshot={},
        input_fingerprint=fingerprint or f"fp-{version_id}-{profile}",
        engine_kind=engine_kind,  # type: ignore[arg-type]
        engine_version=VERSION,
        verdict=verdict,  # type: ignore[arg-type]
        score=None,
        requirements=[RequirementItem(
            requiredness="required", requirement_text="t", jd_locator={"span": [0, 1]},
            disposition="unknown", rule_id="work_auth:x", support=[],
        )],
        run_id=run_id,
    )


def _corpus(engine: Engine, run_id: int):
    with engine.connect() as conn:
        return count_corpus(
            conn, profile_hash=PROFILE, rules_hash=RULES,
            engine_kind=KIND, engine_version=VERSION, run_id=run_id,
        )


def test_the_corpus_partitions_into_judged_and_unjudged(engine: Engine) -> None:
    """Every open posting is either judged under the current identity or it is not.

    This pins the BUCKET VALUES on a well-formed corpus. It deliberately does NOT claim to
    prove the sweep is independent of `open - evaluated` — on a corpus that partitions
    correctly the two are indistinguishable, so read alone this would be an X == X shape.
    `test_a_double_judged_posting_breaks_the_partition_instead_of_hiding_it` is what pins
    independence, and it needs a corpus that cannot partition to do it.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        _judge(conn, _version(conn, _posting(conn, "a"), "a"), run_id=run_id)
        _posting(conn, "b")  # open, never judged

    counts = _corpus(engine, run_id)
    assert counts.open_postings == 2
    assert counts.evaluated == 1
    assert counts.no_current_evaluation == 1
    assert counts.corpus_reconciles


def test_a_double_judged_posting_breaks_the_partition_instead_of_hiding_it(
    engine: Engine,
) -> None:
    """`no_current_evaluation` is an independent NOT EXISTS sweep, NOT `open - evaluated`.

    This is the test that pins that claim, and only a corpus that genuinely fails to
    partition can pin it. One open posting carries TWO current-identity deterministic
    evaluations — possible because `uq_eligibility_deterministic` keys on `input_id`, so two
    input rows differing only by `input_fingerprint` slip past it. That is a real anomaly:
    it means the fingerprint derivation has broken.

    With the independent sweep: 1 open, 2 evaluated, 0 unjudged — 1 != 2 + 0, so the funnel
    reports a corpus that does not reconcile, which is the truth.

    With `no_current_evaluation = open_postings - evaluated` it would be -1, and 1 == 2 + -1
    balances perfectly. The anomaly would be invisible and `corpus_reconciles` could never
    return False for any input at all.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        version_id = _version(conn, _posting(conn, "a"), "a")
        _judge(conn, version_id, run_id=run_id, fingerprint="fp-one")
        _judge(conn, version_id, run_id=run_id, fingerprint="fp-two")

    counts = _corpus(engine, run_id)
    assert counts.open_postings == 1
    assert counts.evaluated == 2, "the second evaluation was deduped; the anomaly is not set up"
    assert counts.no_current_evaluation == 0
    assert counts.corpus_reconciles is False, (
        "a corpus that cannot possibly partition reported as reconciled — "
        "no_current_evaluation is being derived by subtraction"
    )


def test_an_llm_evaluation_does_not_inflate_the_corpus(engine: Engine) -> None:
    """`uq_eligibility_deterministic` is a PARTIAL index — `WHERE engine_kind =
    'deterministic'` — so the LLM lane is NOT deduped by it.

    Without the engine_kind filter, one posting carrying both a deterministic and an LLM
    evaluation would count twice, making `evaluated` exceed `open_postings` and every
    downstream percentage wrong. That is a silent inflation on real data, not a crash.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        version_id = _version(conn, _posting(conn, "a"), "a")
        _judge(conn, version_id, run_id=run_id)
        _judge(conn, version_id, run_id=run_id, engine_kind="llm", fingerprint="fp-llm")

    counts = _corpus(engine, run_id)
    assert counts.open_postings == 1
    assert counts.evaluated == 1, "the LLM lane was counted as a second evaluation"
    assert counts.corpus_reconciles


def test_a_posting_whose_newest_version_is_unjudged_is_not_counted_as_judged(
    engine: Engine,
) -> None:
    """A revised posting must re-enter the funnel.

    Its OLD version carries a verdict; its CURRENT one does not. Without the `newer`
    correlated EXISTS the stale verdict would keep the posting out of the pending pool
    forever, and the funnel would report a revised JD as already handled.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        posting_id = _posting(conn, "a")
        _judge(conn, _version(conn, posting_id, "old"), run_id=run_id)
        _version(conn, posting_id, "new")  # newer capture, never judged

    counts = _corpus(engine, run_id)
    assert counts.evaluated == 0, "a stale verdict on an old version was read as current"
    assert counts.no_current_evaluation == 1


def test_a_closed_posting_is_outside_the_corpus_entirely(engine: Engine) -> None:
    """The funnel's head is OPEN postings. A closed one must not appear in any bucket —
    neither as evaluated nor as unjudged work still owed."""
    with engine.begin() as conn:
        run_id = _run(conn)
        _judge(conn, _version(conn, _posting(conn, "a", status="closed"), "a"), run_id=run_id)

    counts = _corpus(engine, run_id)
    assert counts.open_postings == 0
    assert counts.evaluated == 0
    assert counts.no_current_evaluation == 0


def test_a_verdict_under_a_different_profile_does_not_count_as_current(engine: Engine) -> None:
    """A corrected fact re-keys the ledger: the whole corpus becomes pending again.

    Scoping only by engine_version would report the old profile's verdicts as this profile's,
    which is exactly the staleness D-P2-14 exists to prevent.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        _judge(conn, _version(conn, _posting(conn, "a"), "a"), run_id=run_id, profile="other")

    counts = _corpus(engine, run_id)
    assert counts.evaluated == 0
    assert counts.no_current_evaluation == 1


def test_attribution_splits_this_run_prior_runs_and_null_into_three(engine: Engine) -> None:
    """D-016's stage, and D-019's bucket.

    Without run_id, "judged during this run" and "already on file" are the same number. And
    a NULL run_id must land in its OWN bucket: folding it into `cache_hit_prior_run` would
    erase the only evidence that the unattributable population is not growing.
    """
    with engine.begin() as conn:
        this_run, prior_run = _run(conn), _run(conn)
        _judge(conn, _version(conn, _posting(conn, "a"), "a"), run_id=this_run)
        _judge(conn, _version(conn, _posting(conn, "b"), "b"), run_id=prior_run)
        _judge(conn, _version(conn, _posting(conn, "c"), "c"), run_id=None)

    counts = _corpus(engine, this_run)
    assert counts.judged_this_run == 1
    assert counts.cache_hit_prior_run == 1
    assert counts.cache_hit_unattributed == 1


def test_verdicts_are_grouped_without_being_collapsed(engine: Engine) -> None:
    """`uncertain` is the keystone invariant's ABSTAIN. It must survive the query as its own
    verdict, since there is no `abstain` verdict for it to become."""
    with engine.begin() as conn:
        run_id = _run(conn)
        for tag, verdict in (("a", "eligible"), ("b", "ineligible"), ("c", "uncertain")):
            _judge(conn, _version(conn, _posting(conn, tag), tag), verdict=verdict, run_id=run_id)

    counts = _corpus(engine, run_id)
    assert counts.by_verdict == {"eligible": 1, "ineligible": 1, "uncertain": 1}


def test_the_unattributable_population_counts_only_null_run_ids(engine: Engine) -> None:
    """D-019's invariant is checked by watching this number fail to grow, so it must count
    NULLs across the whole store and nothing else."""
    with engine.begin() as conn:
        run_id = _run(conn)
        _judge(conn, _version(conn, _posting(conn, "a"), "a"), run_id=None)
        _judge(conn, _version(conn, _posting(conn, "b"), "b"), run_id=run_id)

    with engine.connect() as conn:
        assert count_unattributed_evaluations(conn) == 1


def test_a_tailored_row_without_a_compiled_pdf_is_not_counted_as_a_pdf(engine: Engine) -> None:
    """D-006's silent degrade. `artifacts.uri` holds the `.tex` path either way.

    A row count would report a lead with no PDF as delivered; whether the PDF compiled lives
    only in `meta_json.typst_pdf_built`. Two rows, one PDF — a COUNT(*) would say two.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        for tag, built in (("a", True), ("b", False)):
            version_id = _version(conn, _posting(conn, tag), tag)
            record_artifact(
                conn, kind="resume_tailored", uri=f"/out/{tag}.tex",
                posting_version_id=version_id, content_hash=tag,
                generator="boardwatch.tailor", generator_version="1",
                media_type="text/x-tex", meta={"typst_pdf_built": built}, run_id=run_id,
            )

    with engine.connect() as conn:
        counts = count_tailored_artifacts(conn, run_id)
    assert counts.rows == 2
    assert counts.with_pdf == 1, "a résumé with no compiled PDF was counted as a delivered lead"


def test_tailored_artifacts_are_scoped_to_the_run(engine: Engine) -> None:
    """A per-run artifact that counted every run's rows would grow monotonically and its
    cross-check against the pipeline would fail on the second run forever."""
    with engine.begin() as conn:
        this_run, other_run = _run(conn), _run(conn)
        for tag, rid in (("a", this_run), ("b", other_run)):
            version_id = _version(conn, _posting(conn, tag), tag)
            record_artifact(
                conn, kind="resume_tailored", uri=f"/out/{tag}.tex",
                posting_version_id=version_id, content_hash=tag,
                generator="boardwatch.tailor", generator_version="1",
                media_type="text/x-tex", meta={"typst_pdf_built": True}, run_id=rid,
            )

    with engine.connect() as conn:
        assert count_tailored_artifacts(conn, this_run).rows == 1


def test_lead_provenance_names_the_board_and_whether_it_was_user_added(engine: Engine) -> None:
    """Gate P0: *which source produced each lead*, answerable from the artifact alone."""
    with engine.begin() as conn:
        posting_id = _posting(conn, "a", source="registry")

    with engine.connect() as conn:
        found = lead_provenance(conn, [posting_id])
    assert found[posting_id].provider == "greenhouse"
    assert found[posting_id].board_slug == "board-a"
    assert found[posting_id].company_source == "registry"


def _track(conn: Connection, posting_id: int, status: str) -> None:
    job_id = int(conn.execute(postings.select().where(postings.c.id == posting_id)).one().job_id)
    conn.execute(insert(applications).values(
        job_id=job_id, attempt_no=1, status=status,
        created_at=NOW, updated_at=NOW, submitted_at=NOW,
    ))


def test_applied_survives_the_posting_being_closed(engine: Engine) -> None:
    """An application hangs off the canonical job, not off a posting.

    So it must still be counted once its posting has CLOSED — which is the normal end state
    of a posting you applied to. Scoping the job lookup to open postings would make the
    applied count fall back to zero exactly as roles get filled.
    """
    with engine.begin() as conn:
        closed = _posting(conn, "a", status="closed")
        _track(conn, closed, "applied")
        untracked = _posting(conn, "b")

    with engine.connect() as conn:
        assert count_applied_for_postings(conn, [closed, untracked]) == 1


def test_merely_being_interested_is_not_being_applied(engine: Engine) -> None:
    """`create_application` defaults to `interested`, which means a lead was tracked and
    nothing more.

    Counting it would report a posting nobody applied to as a conversion, in the one stage of
    the funnel that claims to measure conversion. `withdrawn` is excluded too: it cannot
    distinguish withdrawing an application from withdrawing interest before applying.
    """
    with engine.begin() as conn:
        interested = _posting(conn, "a")
        _track(conn, interested, "interested")
        withdrawn = _posting(conn, "b")
        _track(conn, withdrawn, "withdrawn")
        applied = _posting(conn, "c")
        _track(conn, applied, "interviewing")

    with engine.connect() as conn:
        found = count_applied_for_postings(conn, [interested, withdrawn, applied])
    assert found == 1, "a tracked-but-not-applied lead was counted as applied"


# --------------------------------------------------------------------------------------
# Per-source outcomes (P0 item 3)
# --------------------------------------------------------------------------------------


def _board(conn: Connection, slug: str, *, source: str = "user", provider: str = "greenhouse") -> int:
    return int(conn.execute(insert(companies).values(
        name=slug, provider=provider, slug=slug, source=source, watched=True,
    )).inserted_primary_key[0])


def _posting_on(
    conn: Connection, company_id: int, tag: str, *, status: str = "open", body_text: str = "b",
) -> int:
    """A posting on an EXISTING board, so several can share one company row."""
    job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    return int(conn.execute(insert(postings).values(
        company_id=company_id, job_id=job_id, provider_posting_id=tag, title="Eng",
        normalized_title="eng", first_seen_at=NOW, last_seen_at=NOW, status=status,
        consecutive_missing=0, content_hash=tag, body_text=body_text,
    )).inserted_primary_key[0])


def _by_source(engine: Engine, run_id: int, posting_ids: list[int] | None = None):
    with engine.connect() as conn:
        return count_by_source(
            conn, identity=(PROFILE, RULES), engine_kind=KIND, engine_version=VERSION,
            run_id=run_id, posting_ids=posting_ids or [],
        )


def test_open_postings_are_attributed_to_the_board_that_owns_them(engine: Engine) -> None:
    """Two boards, unequal inventories. A wrong join would give both the same denominator."""
    with engine.begin() as conn:
        run_id = _run(conn)
        big, small = _board(conn, "big"), _board(conn, "small", source="registry")
        for tag in ("b1", "b2", "b3"):
            _posting_on(conn, big, tag)
        _posting_on(conn, small, "s1")

    rows = {item.board: item for item in _by_source(engine, run_id)}
    assert rows["greenhouse:big"].open_postings == 3
    assert rows["greenhouse:small"].open_postings == 1
    assert rows["greenhouse:small"].company_source == "registry"


def test_a_closed_posting_is_outside_the_per_source_denominator(engine: Engine) -> None:
    """`open_postings` must match the funnel's head, which counts OPEN postings only."""
    with engine.begin() as conn:
        run_id = _run(conn)
        board = _board(conn, "acme")
        _posting_on(conn, board, "open1")
        _posting_on(conn, board, "closed1", status="closed")

    assert _by_source(engine, run_id)[0].open_postings == 1


def test_unique_and_assisted_are_none_rather_than_zero(engine: Engine) -> None:
    """Both are dedup-attribution quantities and dedup is P6.

    0 asserts "no source ever arrived second" — the naive attribution job-apps records as
    having nearly cost it a working adapter. None says the truth: not measured.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        _posting_on(conn, _board(conn, "acme"), "p1")

    row = _by_source(engine, run_id)[0]
    assert row.unique is None
    assert row.assisted is None


def test_only_the_eligible_verdict_counts_towards_a_board(engine: Engine) -> None:
    """`eligible` is a verdict filter, not a count of judged postings."""
    with engine.begin() as conn:
        run_id = _run(conn)
        board = _board(conn, "acme")
        for tag, verdict in (("y", "eligible"), ("n", "ineligible"), ("u", "uncertain")):
            _judge(conn, _version(conn, _posting_on(conn, board, tag), tag),
                   verdict=verdict, run_id=run_id)

    row = _by_source(engine, run_id)[0]
    assert row.open_postings == 3
    assert row.eligible == 1


def test_a_verdict_under_another_profile_is_not_attributed_to_the_board(engine: Engine) -> None:
    """The identity scoping must hold per board too, or every board inflates on a re-profile."""
    with engine.begin() as conn:
        run_id = _run(conn)
        board = _board(conn, "acme")
        _judge(conn, _version(conn, _posting_on(conn, board, "p1"), "p1"),
               verdict="eligible", run_id=run_id, profile="other-profile")

    assert _by_source(engine, run_id)[0].eligible == 0


def test_no_profile_reports_every_board_as_zero_eligible_rather_than_failing(engine: Engine) -> None:
    """A fresh install has no identity. The denominator is still real, so the table still says so."""
    with engine.begin() as conn:
        run_id = _run(conn)
        _posting_on(conn, _board(conn, "acme"), "p1")

    with engine.connect() as conn:
        rows = count_by_source(
            conn, identity=None, engine_kind=KIND, engine_version=VERSION,
            run_id=run_id, posting_ids=[],
        )
    assert rows[0].open_postings == 1
    assert rows[0].eligible == 0


def test_a_lead_is_attributed_to_its_board_through_the_posting_version(engine: Engine) -> None:
    """`artifacts` carries no posting_id, only posting_version_id.

    So the board a lead came from is reachable ONLY through its version. Getting this join
    wrong is how Gate P0's "which source produced each lead" silently stops being answerable.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        winner, quiet = _board(conn, "winner"), _board(conn, "quiet")
        _posting_on(conn, quiet, "q1")
        version_id = _version(conn, _posting_on(conn, winner, "w1"), "w1")
        record_artifact(
            conn, kind="resume_tailored", uri="/out/w1.tex", posting_version_id=version_id,
            content_hash="w1", generator="boardwatch.tailor", generator_version="1",
            media_type="text/x-tex", meta={"typst_pdf_built": True}, run_id=run_id,
        )

    rows = {item.board: item for item in _by_source(engine, run_id)}
    assert rows["greenhouse:winner"].leads == 1
    assert rows["greenhouse:quiet"].leads == 0


def test_a_lead_from_a_previous_run_is_not_credited_to_this_one(engine: Engine) -> None:
    """Per-run means per-run; otherwise every board's lead count grows monotonically."""
    with engine.begin() as conn:
        this_run, other_run = _run(conn), _run(conn)
        board = _board(conn, "acme")
        for tag, rid in (("a", this_run), ("b", other_run)):
            record_artifact(
                conn, kind="resume_tailored", uri=f"/out/{tag}.tex",
                posting_version_id=_version(conn, _posting_on(conn, board, tag), tag),
                content_hash=tag, generator="boardwatch.tailor", generator_version="1",
                media_type="text/x-tex", meta={"typst_pdf_built": True}, run_id=rid,
            )

    assert _by_source(engine, this_run)[0].leads == 1


def test_a_board_whose_lead_posting_closed_still_appears(engine: Engine) -> None:
    """A posting can close mid-run. Keying the table off open postings alone would drop the
    board that produced a lead — and a missing lead reads as a smaller funnel."""
    with engine.begin() as conn:
        run_id = _run(conn)
        board = _board(conn, "closer")
        version_id = _version(conn, _posting_on(conn, board, "c1", status="closed"), "c1")
        record_artifact(
            conn, kind="resume_tailored", uri="/out/c1.tex", posting_version_id=version_id,
            content_hash="c1", generator="boardwatch.tailor", generator_version="1",
            media_type="text/x-tex", meta={"typst_pdf_built": True}, run_id=run_id,
        )

    rows = _by_source(engine, run_id)
    assert [item.board for item in rows] == ["greenhouse:closer"]
    assert rows[0].open_postings == 0
    assert rows[0].leads == 1


def test_applied_is_attributed_per_board_with_the_same_status_filter(engine: Engine) -> None:
    """Must agree with count_applied_for_postings on what a submission is: `interested` is not."""
    with engine.begin() as conn:
        run_id = _run(conn)
        board = _board(conn, "acme")
        did = _posting_on(conn, board, "did")
        _track(conn, did, "applied")
        merely = _posting_on(conn, board, "merely")
        _track(conn, merely, "interested")

    rows = _by_source(engine, run_id, posting_ids=[did, merely])
    assert rows[0].applied == 1


def test_boards_that_produced_a_lead_sort_above_boards_that_did_not(engine: Engine) -> None:
    """118 boards have open postings on the real store. The ones that produced a lead are the
    reason the table exists, so they must not be buried."""
    with engine.begin() as conn:
        run_id = _run(conn)
        # `huge` FIRST, so its company id is lower. `company_ids` is a set of small ints and
        # iterates in id order, so with `loud` inserted first this test passed even with the
        # sort deleted entirely.
        huge, loud = _board(conn, "huge"), _board(conn, "loud")
        for index in range(5):
            _posting_on(conn, huge, f"h{index}")
        version_id = _version(conn, _posting_on(conn, loud, "l1"), "l1")
        record_artifact(
            conn, kind="resume_tailored", uri="/out/l1.tex", posting_version_id=version_id,
            content_hash="l1", generator="boardwatch.tailor", generator_version="1",
            media_type="text/x-tex", meta={"typst_pdf_built": True}, run_id=run_id,
        )

    assert [item.board for item in _by_source(engine, run_id)] == [
        "greenhouse:loud", "greenhouse:huge",
    ]


# --------------------------------------------------------------------------------------
# P3 item 5 (B5) — the zero-output guard's predicate
# --------------------------------------------------------------------------------------


def _candidate_judged_this_run(engine: Engine, run_id: int) -> int:
    with engine.connect() as conn:
        return count_candidate_judged_this_run(
            conn, profile_hash=PROFILE, rules_hash=RULES,
            engine_kind=KIND, engine_version=VERSION, run_id=run_id,
        )


def test_an_eligible_posting_judged_by_this_run_counts(engine: Engine) -> None:
    with engine.begin() as conn:
        run_id = _run(conn)
        _judge(conn, _version(conn, _posting(conn, "a"), "a"), verdict="eligible", run_id=run_id)

    assert _candidate_judged_this_run(engine, run_id) == 1


def test_an_uncertain_posting_judged_by_this_run_counts(engine: Engine) -> None:
    """`uncertain` can become a lead too, where `ineligible` cannot — so a run that
    judged new uncertain work yet produced 0 leads is the same silent empty day. This also
    guards D-250: a body that fires no family now abstains to `uncertain`, and must still count
    as candidate work rather than escaping the zero-output guard by relabeling."""
    with engine.begin() as conn:
        run_id = _run(conn)
        _judge(conn, _version(conn, _posting(conn, "a"), "a"), verdict="uncertain", run_id=run_id)

    assert _candidate_judged_this_run(engine, run_id) == 1


def test_an_eligible_posting_judged_by_a_prior_run_is_a_steady_state_cache_hit_not_counted(
    engine: Engine,
) -> None:
    """The review's flagged false alarm: a cache-hit-only steady-state day must read as 0 new
    candidate work for THIS run, even though candidate postings exist in the store."""
    with engine.begin() as conn:
        prior_run, this_run = _run(conn), _run(conn)
        _judge(conn, _version(conn, _posting(conn, "a"), "a"), verdict="eligible", run_id=prior_run)

    assert _candidate_judged_this_run(engine, this_run) == 0


def test_an_ineligible_posting_judged_by_this_run_is_not_counted(engine: Engine) -> None:
    """The guard's predicate is `(eligible OR uncertain) AND judged_this_run`, not merely
    judged_this_run — `ineligible` is hidden from the ranker, so fresh work that resulted in an
    `ineligible` verdict is not a candidate lead and is not the failure mode being caught."""
    with engine.begin() as conn:
        run_id = _run(conn)
        _judge(
            conn, _version(conn, _posting(conn, "a"), "a"), verdict="ineligible", run_id=run_id,
        )

    assert _candidate_judged_this_run(engine, run_id) == 0


def test_count_stub_postings_counts_only_open_empty_bodies(engine: Engine) -> None:
    """A stub is an OPEN posting whose JD body is empty after trimming. A whitespace-only body
    is a stub; a closed empty posting is not counted, and a real body is not a stub."""
    with engine.begin() as conn:
        _posting(conn, "real", body_text="a full job description")
        _posting(conn, "empty", body_text="")
        _posting(conn, "whitespace", body_text="   \n\t")
        _posting(conn, "closed-empty", status="closed", body_text="")
    with engine.connect() as conn:
        assert count_stub_postings(conn) == 2


# --------------------------------------------------------------------------------------
# Per-source stub attribution (spec §4.4)
# --------------------------------------------------------------------------------------


def test_per_company_stub_counts_sum_to_the_corpus_count(engine: Engine) -> None:
    """Counted through a different path than the corpus number, per CLAUDE.md."""
    with engine.begin() as conn:
        big = _board(conn, "big")
        small = _board(conn, "small")
        _posting_on(conn, big, "b1", body_text="")
        _posting_on(conn, big, "b2", body_text="\t\n")
        _posting_on(conn, big, "b3", body_text="a full job description")
        _posting_on(conn, small, "s1", body_text="   ")
    with engine.connect() as conn:
        per_company = count_stub_postings_by_company(conn)
        assert sum(per_company.values()) == count_stub_postings(conn)


def test_a_company_with_no_stubs_reports_zero_not_absent(engine: Engine) -> None:
    """It is instrumented, so 0 is honest. Absence would read as 'not measured'."""
    with engine.begin() as conn:
        stubby = _board(conn, "stubby")
        clean = _board(conn, "clean")
        _posting_on(conn, stubby, "s1", body_text="")
        _posting_on(conn, clean, "c1", body_text="a full job description")
    with engine.connect() as conn:
        per_company = count_stub_postings_by_company(conn)
    assert per_company[clean] == 0


def test_a_closed_empty_posting_is_not_a_stub_for_its_company(engine: Engine) -> None:
    """The per-company twin of `test_count_stub_postings_counts_only_open_empty_bodies`.

    Asserted against a LITERAL, deliberately not against `count_stub_postings`: that
    function filters on `status == "open"` too, so comparing the two moves both sides
    together and cannot see the clause go missing. Without this, a board that closed 300
    empty postings reports more stubs than it has open postings — contradicting the field's
    own definition — with nothing red.
    """
    with engine.begin() as conn:
        board = _board(conn, "closing")
        _posting_on(conn, board, "open-stub", body_text="")
        _posting_on(conn, board, "closed-stub", status="closed", body_text="")
        _posting_on(conn, board, "closed-real", status="closed", body_text="a full jd")
    with engine.connect() as conn:
        assert count_stub_postings_by_company(conn) == {board: 1}


def test_a_whitespace_only_body_of_tabs_and_newlines_counts_as_a_stub(engine: Engine) -> None:
    """SQLite's one-arg trim strips spaces ONLY; tabs and newlines must be in the strip set."""
    with engine.begin() as conn:
        _posting(conn, "x", body_text="\t\n  ")
    with engine.connect() as conn:
        assert sum(count_stub_postings_by_company(conn).values()) == 1
