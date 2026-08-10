"""The identity table's shape (design §1.2, §7)."""

from datetime import datetime

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from boardwatch.core.identity_kinds import IDENTITY_ALGORITHM_VERSION, IDENTITY_KIND_NAMES
from boardwatch.store.tables import posting_identities


def _row(engine, posting_id: int, **over):
    values = {
        "posting_id": posting_id,
        "kind": "exact_quad",
        "identity_key": "k" * 64,
        "algorithm_version": IDENTITY_ALGORITHM_VERSION,
        "created_at": datetime(2026, 8, 9),
    }
    values.update(over)
    with engine.begin() as conn:
        conn.execute(insert(posting_identities).values(**values))


def test_kind_is_constrained_to_the_closed_catalog(seed_dedup):
    seed = seed_dedup()
    with pytest.raises(IntegrityError):
        _row(seed.engine, seed.posting_ids[0], kind="fuzzy_title_match")


def test_every_catalog_kind_is_accepted(seed_dedup):
    seed = seed_dedup()
    for i, kind in enumerate(IDENTITY_KIND_NAMES):
        _row(seed.engine, seed.posting_ids[0], kind=kind, identity_key=f"{i:064d}")
    with seed.engine.connect() as conn:
        assert len(conn.execute(select(posting_identities)).all()) == len(IDENTITY_KIND_NAMES)


def test_one_row_per_posting_kind_and_version(seed_dedup):
    seed = seed_dedup()
    _row(seed.engine, seed.posting_ids[0])
    with pytest.raises(IntegrityError):
        _row(seed.engine, seed.posting_ids[0], identity_key="z" * 64)


def test_a_version_bump_writes_beside_history_rather_than_mutating_it(seed_dedup):
    """The second version must be one that can never BE the current one.

    This previously hard-coded `"p6.2"` as the stand-in for "some other version", which
    silently became the real `IDENTITY_ALGORITHM_VERSION` at the next bump — both rows then
    landed on the same (posting_id, kind, version) and the UNIQUE constraint fired, failing a
    test that has nothing to do with what broke. A historical sentinel cannot collide with a
    future release, so this no longer depends on the constant's current value.
    """
    historical = "p0.0-never-a-real-version"
    assert historical != IDENTITY_ALGORITHM_VERSION
    seed = seed_dedup()
    _row(seed.engine, seed.posting_ids[0])
    _row(seed.engine, seed.posting_ids[0], algorithm_version=historical, identity_key="z" * 64)
    with seed.engine.connect() as conn:
        assert len(conn.execute(select(posting_identities)).all()) == 2


def test_posting_id_is_a_real_foreign_key(seed_dedup):
    seed = seed_dedup()
    with pytest.raises(IntegrityError):
        _row(seed.engine, 999_999)
