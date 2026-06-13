from pathlib import Path

import pytest
from provider_cases import ALL_CASES, ProviderCase
from sqlalchemy import Engine, insert

from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


@pytest.fixture(params=ALL_CASES, ids=[c.name for c in ALL_CASES])
def case(request: pytest.FixtureRequest) -> ProviderCase:
    return request.param


@pytest.fixture()
def company_id(engine: Engine, case: ProviderCase) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            insert(tables.companies).values(
                name="Acme", provider=case.name, slug=case.slug, source="user", watched=True
            )
        )
        return int(result.inserted_primary_key[0])


@pytest.fixture()
def run_id(engine: Engine) -> int:
    from boardwatch.store.queries import insert_run

    return insert_run(engine)
