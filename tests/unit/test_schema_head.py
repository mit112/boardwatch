from boardwatch.store.db import schema_revision


def test_head_is_the_board_scans_lane_revision() -> None:
    """Pinned deliberately: a new migration must state its new head here, not inherit it.

    Bumping this line is the acknowledgement that the head moved.
    `p_form_questions` creates `posting_form_questions`, one row per posting version whose
    Greenhouse application form has been fetched (T91): the fetched `questions[]` payload and
    when it was read. Keyed on the VERSION because a revised requisition is a new subject
    everywhere else in this store and its form may have been revised with it; it stores the
    payload and never the match, so the closed catalog in `delivery/form_questions.py` can gain a
    surface and take effect on the next reconcile with no board re-asked. A CREATE TABLE with one
    FK to `posting_versions` and nothing referencing it, so no rebuild and no child to orphan.
    It follows `p_body_precondition_checks`, which records every posting version the lane-body
    precondition has judged, PASS or FAIL, keyed on the detector's FINGERPRINT — without a durable
    record of a successful check, `eligibility/preflight.py::_pending` could never re-reach a
    body it had already evaluated, and the marker catalog would be decorative.
    """
    # T186 B1 added `p_target_countries` (the `target_countries` profile column) on top of it,
    # and T199 `p_board_scans_lane` (the lane that wrote a `board_scans` row) on top of that.
    assert schema_revision() == "p_board_scans_lane"
