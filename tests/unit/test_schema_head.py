from boardwatch.store.db import schema_revision


def test_head_is_the_quarantined_bodies_revision() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `p_quarantined_bodies` adds the `quarantined_bodies` table — one row per posting VERSION
    withheld from the rules because its body is an aggregator's rendered page rather than the
    employer's own text (D-406). Keyed on the immutable version, so a quarantine cannot be
    silently invalidated by a later scan rewriting `postings.body_text` underneath it, and
    drained by setting `reopened_at` rather than deleting, exactly as `job_dispositions` is.
    It follows `p_lane_seeds`, which creates `lane_seeds` — the durable handoff from a lane that
    DISCOVERS a posting URL it cannot resolve to a lane that can, which has to be durable because
    tier-D vendors are per-tenant and the two lanes do not run in the same stage pass (D-413).
    That in turn follows `p_runs_corpus_counts`, which added `runs.corpus_open`,
    `runs.corpus_evaluated` and `runs.corpus_candidates` (all INTEGER NULL) so the standing
    eligible corpus each run measured lives in the store rather than only in that run's funnel
    artifact, which is what lets a cross-run detector see an eligibility collapse (D-371).
    """
    assert schema_revision() == "p_quarantined_bodies"
