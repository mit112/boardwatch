import copy

from sqlalchemy import func, select

from boardwatch.scan.apply import apply_board
from boardwatch.store import tables


def _version_count(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(tables.posting_versions)).scalar_one()


def test_new_posting_captures_one_version(engine, case, company_id, run_id):
    apply_board(engine, case.snapshot_for(case.jobs()[:1]), company_id, run_id)
    assert _version_count(engine) == 1
    with engine.connect() as conn:
        reason = conn.execute(select(tables.posting_versions.c.capture_reason)).scalar_one()
    assert reason == "new"


def test_body_revision_appends_a_version(engine, case, company_id, run_id):
    job = case.jobs()[0]
    apply_board(engine, case.snapshot_for([job]), company_id, run_id)
    revised = case.set_body(copy.deepcopy(job), "an entirely different body")
    apply_board(engine, case.snapshot_for([revised]), company_id, run_id)
    assert _version_count(engine) == 2


def test_metadata_only_change_appends_no_version(engine, case, company_id, run_id):
    job = case.set_metadata(case.jobs()[0], variant=1)
    apply_board(engine, case.snapshot_for([job]), company_id, run_id)
    changed = case.set_metadata(copy.deepcopy(job), variant=2)  # metadata differs, body identical
    apply_board(engine, case.snapshot_for([changed]), company_id, run_id)
    assert _version_count(engine) == 1  # D25: metadata-only => no `revised` => no new version
