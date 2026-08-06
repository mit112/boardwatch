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
    count_corpus,
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


def _posting(conn: Connection, slug: str, *, status: str = "open", source: str = "user") -> int:
    cid = int(conn.execute(insert(companies).values(
        name="Acme", provider="greenhouse", slug=f"board-{slug}", source=source, watched=True,
    )).inserted_primary_key[0])
    jid = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
    return int(conn.execute(insert(postings).values(
        company_id=cid, job_id=jid, provider_posting_id=slug, title="Eng",
        normalized_title="eng", first_seen_at=NOW, last_seen_at=NOW, status=status,
        consecutive_missing=0, content_hash=slug, body_text="b",
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

    `no_current_evaluation` is its own NOT EXISTS sweep rather than `open - evaluated`, so
    this identity is a genuine assertion about two independent queries agreeing.
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
    assert counts.attribution_reconciles


def test_verdicts_are_grouped_without_being_collapsed(engine: Engine) -> None:
    """`uncertain` is the keystone invariant's ABSTAIN. It must survive the query as its own
    verdict, since there is no `abstain` verdict for it to become."""
    with engine.begin() as conn:
        run_id = _run(conn)
        for tag, verdict in (("a", "eligible"), ("b", "ineligible"), ("c", "uncertain")):
            _judge(conn, _version(conn, _posting(conn, tag), tag), verdict=verdict, run_id=run_id)

    counts = _corpus(engine, run_id)
    assert counts.by_verdict == {"eligible": 1, "ineligible": 1, "uncertain": 1}
    assert counts.verdict_reconciles


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
    """D-006's silent degrade. `artifacts.uri` holds the `.typ` path either way.

    A row count would report a lead with no PDF as delivered; whether the PDF compiled lives
    only in `meta_json.typst_pdf_built`. Two rows, one PDF — a COUNT(*) would say two.
    """
    with engine.begin() as conn:
        run_id = _run(conn)
        for tag, built in (("a", True), ("b", False)):
            version_id = _version(conn, _posting(conn, tag), tag)
            record_artifact(
                conn, kind="resume_tailored", uri=f"/out/{tag}.typ",
                posting_version_id=version_id, content_hash=tag,
                generator="boardwatch.tailor", generator_version="1",
                media_type="text/x-typst", meta={"typst_pdf_built": built}, run_id=run_id,
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
                conn, kind="resume_tailored", uri=f"/out/{tag}.typ",
                posting_version_id=version_id, content_hash=tag,
                generator="boardwatch.tailor", generator_version="1",
                media_type="text/x-typst", meta={"typst_pdf_built": True}, run_id=rid,
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


def test_applied_is_counted_through_the_job_anchor(engine: Engine) -> None:
    """An application hangs off the canonical job, not off a posting, so a tracked
    application survives its posting being revised or closed."""
    with engine.begin() as conn:
        posting_id = _posting(conn, "a")
        job_id = int(conn.execute(
            postings.select().where(postings.c.id == posting_id)
        ).one().job_id)
        conn.execute(insert(applications).values(
            job_id=job_id, attempt_no=1, status="applied",
            created_at=NOW, updated_at=NOW, submitted_at=NOW,
        ))
        untracked = _posting(conn, "b")

    with engine.connect() as conn:
        assert count_applied_for_postings(conn, [posting_id, untracked]) == 1
        assert count_applied_for_postings(conn, []) == 0
