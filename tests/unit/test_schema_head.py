from boardwatch.store.db import schema_revision


def test_head_is_the_body_precondition_checks_revision() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `p_body_precondition_checks` records every posting version the lane-body precondition has
    judged, PASS or FAIL, keyed on the detector's FINGERPRINT. It exists for the passes: without
    a durable record of a successful check, `eligibility/preflight.py::_pending` — which keys on
    profile, rules and engine version, none of which move when a marker is edited — could never
    re-reach a body it had already evaluated, and the marker catalog would be decorative.
    It follows `p_quarantined_bodies`, which added the quarantine itself and which now stacks
    on `p_lane_seeds`: one row per posting
    version withheld from the rules because its body is an aggregator's rendered page rather
    than the employer's own text (D-406), drained by setting `reopened_at` rather than deleting,
    exactly as `job_dispositions` is.
    """
    assert schema_revision() == "p_body_precondition_checks"
