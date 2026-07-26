from sqlalchemy import func, select

from boardwatch.scan.apply import apply_board
from boardwatch.store import tables


def test_new_posting_creates_and_anchors_a_job(engine, case, company_id, run_id):
    apply_board(engine, case.snapshot_for(case.jobs()[:1]), company_id, run_id)
    with engine.connect() as conn:
        posting = conn.execute(select(tables.postings)).one()
        jobs = conn.execute(select(func.count()).select_from(tables.jobs)).scalar_one()
    assert posting.job_id is not None
    assert jobs == 1


def test_two_occurrences_get_distinct_jobs(engine, case, company_id, run_id):
    base = case.jobs()[0]
    both = [base, case.clone_with_id(base, 987654)]  # identical body, different provider id
    apply_board(engine, case.snapshot_for(both), company_id, run_id)
    with engine.connect() as conn:
        postings = conn.execute(select(func.count()).select_from(tables.postings)).scalar_one()
        jobs = conn.execute(select(func.count()).select_from(tables.jobs)).scalar_one()
    assert postings == 2
    assert jobs == 2  # D10/D28: annotation layer never merges identities (test-f corollary)
