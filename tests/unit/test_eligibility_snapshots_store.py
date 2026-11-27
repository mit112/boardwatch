"""T363: the writer stores each snapshot once and `eligibility_inputs` carries only the hashes."""

from pathlib import Path

from sqlalchemy import insert, text

from boardwatch.core.clock import utcnow
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.eligibility import _get_or_create_input
from boardwatch.store.posting_blobs import insert_posting
from boardwatch.store.tables import (
    companies,
    eligibility_inputs,
    jobs,
    posting_versions,
)

#: What the JSON column type writes for these dicts (json.dumps defaults), spelled out.
PROFILE = {"b": 1, "a": [1, 2]}
PROFILE_BYTES = '{"b": 1, "a": [1, 2]}'
RULES = {"catalog_version": "v", "rules": []}
RULES_BYTES = '{"catalog_version": "v", "rules": []}'


def _version(conn) -> int:  # type: ignore[no-untyped-def]
    now = utcnow()
    company_id = int(conn.execute(insert(companies).values(
        name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
    )).inserted_primary_key[0])
    job_id = int(conn.execute(insert(jobs).values(created_at=now)).inserted_primary_key[0])
    posting_id = int(insert_posting(conn,
        company_id=company_id, job_id=job_id, provider_posting_id="p-1", title="Eng",
        normalized_title="eng", first_seen_at=now, last_seen_at=now, status="open",
        consecutive_missing=0, content_hash="h1", body_text="b",
    ))
    return int(conn.execute(insert(posting_versions).values(
        posting_id=posting_id, content_hash="h1", body_text="b", captured_at=now,
        run_id=None, capture_reason="new",
    )).inserted_primary_key[0])


def test_inputs_sharing_a_snapshot_store_it_once(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    with engine.begin() as conn:
        version = _version(conn)
        ids = [
            _get_or_create_input(
                conn, posting_version_id=version, profile_hash="ph", profile_snapshot=PROFILE,
                rules_hash="rh", rules_snapshot=RULES, input_fingerprint=f"fp{n}")
            for n in range(3)
        ]
        # Same fingerprint again: the input is reused and nothing is added anywhere.
        again = _get_or_create_input(
            conn, posting_version_id=version, profile_hash="ph", profile_snapshot=PROFILE,
            rules_hash="rh", rules_snapshot=RULES, input_fingerprint="fp0")
    assert again == ids[0] and len(set(ids)) == 3

    with engine.connect() as conn:
        snapshots = sorted(tuple(r) for r in conn.execute(text(
            "SELECT kind, hash, CAST(snapshot_json AS TEXT) FROM eligibility_snapshots")))
        columns = [c.name for c in eligibility_inputs.columns]
        stored_columns = [r[1] for r in conn.execute(text("PRAGMA table_info(eligibility_inputs)"))]
    assert snapshots == [("profile", "ph", PROFILE_BYTES), ("rules", "rh", RULES_BYTES)]
    assert "profile_snapshot_json" not in columns + stored_columns
    assert "rules_snapshot_json" not in columns + stored_columns


def test_a_changed_snapshot_gets_its_own_row_and_the_first_copy_stays(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    other = {"b": 2, "a": [1, 2]}
    reordered = {"a": [1, 2], "b": 1}  # equal as JSON, different stored bytes
    with engine.begin() as conn:
        version = _version(conn)
        for fingerprint, profile_hash, snapshot in (
            ("f1", "ph", PROFILE), ("f2", "ph2", other), ("f3", "ph", reordered),
        ):
            _get_or_create_input(
                conn, posting_version_id=version, profile_hash=profile_hash,
                profile_snapshot=snapshot, rules_hash="rh", rules_snapshot=RULES,
                input_fingerprint=fingerprint)
    with engine.connect() as conn:
        stored = dict(conn.execute(text(
            "SELECT hash, CAST(snapshot_json AS TEXT) FROM eligibility_snapshots "
            "WHERE kind = 'profile'")).all())
    assert stored == {"ph": PROFILE_BYTES, "ph2": '{"b": 2, "a": [1, 2]}'}
