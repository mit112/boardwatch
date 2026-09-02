from boardwatch.store.db import schema_revision


def test_head_is_the_lane_seeds_revision() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `p_lane_seeds` creates `lane_seeds`, the durable handoff from a lane that DISCOVERS a
    posting URL it cannot resolve to a lane that can. Tier-D vendors are per-tenant with no
    cross-tenant search, so those are different lanes and they do not run in the same stage
    pass (D-413) -- the handoff cannot be a value passed between them. A CREATE TABLE with two
    FKs to `runs` and nothing referencing it, so no rebuild and no child to orphan. It follows
    `p_runs_corpus_counts`, which adds `runs.corpus_open`, `runs.corpus_evaluated` and
    `runs.corpus_candidates` (all INTEGER NULL) so the standing eligible corpus each run
    measured lives in the store rather than only in that run's funnel artifact, which is what
    lets a cross-run detector see an eligibility collapse (D-371). It follows
    `p_runs_board_split`, which added `runs.boards_partial`, `runs.boards_unchanged` and
    `runs.boards_failed` (all INTEGER NULL) so the store carries ScanSummary's full four-way
    board split, not only complete/attempted (D-341's other half, D-342). All six are additive
    with no table rebuild.
    """
    assert schema_revision() == "p_lane_seeds"
