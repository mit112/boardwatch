"""The funnel's `dedup` stage: instrumented, never folded, and cheap enough to keep.

Three properties, each of which the artifact loses if it collapses:

* not-measured stays distinguishable from zero, and the two not-measured REASONS stay
  distinguishable from each other;
* an audit-only kind's redundancy is an upper bound and is never summed into the suppression
  drop (D-327);
* restricting the sweep's inputs to the postings that can actually collide changes the peak
  memory and NOT the answer.
"""

from __future__ import annotations

from sqlalchemy import update

from boardwatch.core.dedup import resolve_duplicates
from boardwatch.reports.run_funnel import _dedup_stage
from boardwatch.store.identity_queries import load_identities, load_identity_inputs
from boardwatch.store.run_funnel_queries import (
    _colliding_open_posting_ids,
    sweep_duplicates,
)
from boardwatch.store.tables import postings


def _retitle(engine, posting_id: int, title: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == posting_id)
            .values(title=title, normalized_title=title.casefold())
        )


def _sweep(seed):
    with seed.engine.connect() as conn:
        return sweep_duplicates(conn)


def test_the_stage_counts_the_corpus_and_names_the_suppression(seed_dedup, backfill_identities):
    """Two identical postings: 2 in, 1 out, 1 named drop. The state the stage never reported."""
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)

    stage = _dedup_stage(_sweep(seed))

    assert stage.instrumented is True
    assert (stage.entered, stage.advanced) == (2, 1)
    assert [(d.reason, d.count) for d in stage.drops] == [("suppressed_duplicate", 1)]
    assert stage.reconciled is True


def test_an_incomplete_backfill_reports_unmeasured_rather_than_zero_duplicates(
    seed_dedup, backfill_identities
):
    """The state right after an IDENTITY_ALGORITHM_VERSION bump.

    Zero here would assert "we grouped the corpus and found no duplicates", which is the
    opposite claim to "we could not group it".
    """
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed, [seed.posting_ids[0]])

    stage = _dedup_stage(_sweep(seed))

    assert stage.instrumented is False
    assert (stage.entered, stage.advanced, stage.dropped) == (None, None, 0)
    assert stage.reconciled is None
    assert "INCOMPLETE" in stage.note


def test_a_sweep_that_never_ran_is_distinguishable_from_an_incomplete_one():
    """Both report null, and they must not report the SAME reason for it."""
    stage = _dedup_stage(None)
    assert stage.instrumented is False
    assert "did not run" in stage.note
    assert "INCOMPLETE" not in stage.note


def test_the_audit_only_bound_is_reported_beside_the_drop_and_never_inside_it(
    seed_dedup, backfill_identities
):
    """D-327's rule, at the one place a bound could get folded into a count.

    Two postings that share company/title/locations but NOT a body: `company_title_location`
    sees the collision, `exact_quad` does not, and nothing is suppressed. The bound must
    appear and must not move `dropped`.
    """
    seed = seed_dedup(count=2, identical=True)
    with seed.engine.begin() as conn:
        conn.execute(
            update(postings)
            .where(postings.c.id == seed.posting_ids[0])
            .values(body_text="A completely different body.", content_hash="hh-different")
        )
    backfill_identities(seed)

    stage = _dedup_stage(_sweep(seed))

    assert stage.dropped == 0
    assert stage.dedup_detail is not None
    assert stage.dedup_detail["candidate_redundant_company_title_location"] == 1
    assert stage.dedup_detail["suppressing_redundant"] == 0
    # A kind that CAN collide and did not gets a measured 0; `exact_provider`, which cannot
    # collide at all, is absent rather than reported as a structural 0.
    assert stage.dedup_detail["candidate_redundant_content_hash_only"] == 0
    assert "candidate_redundant_exact_provider" not in stage.dedup_detail


def test_the_bound_reaches_the_machine_readable_half(seed_dedup, backfill_identities):
    """The Markdown half is pinned in `test_run_funnel.py`, where the renderer helper lives."""
    from boardwatch.reports.run_funnel import _stage_json

    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    stage = _dedup_stage(_sweep(seed))

    payload = _stage_json(stage)
    assert payload["dedup_detail"] == stage.dedup_detail
    assert payload["instrumented"] is True


def test_the_restricted_sweep_finds_exactly_what_a_whole_corpus_sweep_would(
    seed_dedup, backfill_identities
):
    """The body_text saving must be free.

    `resolve_duplicates` drops every identity group with fewer than two members, so a posting
    that shares no suppressing key with another can neither be suppressed nor survive
    anything. Loading only the colliding postings is therefore an identity, not an
    approximation — and this is the test that says so: the reference side loads the WHOLE
    corpus, bodies and all, exactly as the sweep used to.

    The corpus is deliberately mixed — two colliding, one alone — so an implementation that
    loaded everything and one that loaded only the pair give different INPUTS and must still
    give the same ANSWER.
    """
    seed = seed_dedup(count=3, identical=True)
    _retitle(seed.engine, seed.posting_ids[0], "Something Else Entirely")
    backfill_identities(seed)

    with seed.engine.connect() as conn:
        colliding = sorted(_colliding_open_posting_ids(conn))
        reference = resolve_duplicates(load_identity_inputs(conn), load_identities(conn))
        sweep = sweep_duplicates(conn)

    assert colliding == sorted(seed.posting_ids[1:])
    assert seed.posting_ids[0] not in colliding
    assert sweep.entered == 3
    assert sweep.suppressed == len(reference) == 1


def test_the_colliding_set_is_driven_by_the_catalog_not_by_a_literal_kind(
    seed_dedup, backfill_identities, monkeypatch
):
    """Enabling a second suppressing kind is a one-line catalog edit.

    A hardcoded `exact_quad` here would narrow the sweep's input below what
    `resolve_duplicates` iterates, and suppressions would quietly stop happening — in the
    direction that reads as a healthy corpus. Emptying the catalog is the cheapest way to
    show the constant is actually read: against a literal, these two postings still come back.
    """
    seed = seed_dedup(count=2, identical=True)
    backfill_identities(seed)
    monkeypatch.setattr("boardwatch.store.run_funnel_queries.SUPPRESSING_KINDS", ())

    with seed.engine.connect() as conn:
        assert _colliding_open_posting_ids(conn) == []
