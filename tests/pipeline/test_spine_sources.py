from sqlalchemy import select

from boardwatch.scan.apply import apply_board
from boardwatch.store import tables
from boardwatch.store.sources import get_version_source


def test_scan_records_a_source_for_each_version(engine, case, company_id, run_id):
    apply_board(engine, case.snapshot_for(case.jobs()[:1]), company_id, run_id)
    with engine.connect() as conn:
        version = conn.execute(select(tables.posting_versions)).one()
        src = get_version_source(conn, version.id)
    assert src is not None
    assert src.source_url == case.board_url()             # the canonical board URL
    assert src.payload_hash == version.content_hash       # ties the source to the exact body
    assert src.source_record_id                            # the provider posting id, non-empty
