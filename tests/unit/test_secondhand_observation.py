"""D-414(a): a lower-fidelity observation must not overwrite fields it never observed.

`scan/apply.py`'s D25 rule refreshes every provider-sourced column on every positive observation
regardless of `content_hash`. That is right for a provider reading the employer's own board and
wrong for an aggregator lane whose hit converged onto that provider's
`(company_id, provider_posting_id)`: the lane never looked at `remote_policy`, `department` or
`salary_*`, and the location it did read is its own index of the posting. With
`location_filter_mode = "hard"` the overwrite is a deletion path -- a posting recorded remote,
re-rendered as one metro, is hard-vetoed in the SAME run, because the lane stage runs after the
scan and before the ranker.

The neutrality guard below is the other half and is the reason the mechanism is a DECLARATION
rather than a rank on the lane: a board scan must still write exactly what it writes today.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, get_args

import pytest
from sqlalchemy import Engine, insert, select, update

from boardwatch.core.models import BoardSnapshot, RawPosting, SecondhandField
from boardwatch.core.posting_identity import IdentityInputs, compute_identities
from boardwatch.scan.apply import _SECONDHAND_COLUMNS, _mutable_fields, apply_board
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import insert_run

ALL_SECONDHAND: frozenset[SecondhandField] = frozenset(get_args(SecondhandField))

# The provider's own reading of the posting, and the aggregator's weaker one of the SAME posting.
# Every field differs, so a column that is not asserted below is a column this file forgot.
PROVIDER = dict(
    provider_posting_id="p1",
    title="Senior Backend Engineer",
    url="https://boards.greenhouse.io/acme/jobs/p1",
    locations=["Remote - US"],
    department="Engineering",
    remote_policy="remote",
    posted_at=datetime(2026, 8, 1, 12, 0),
    updated_at=datetime(2026, 8, 2, 12, 0),
    body_text="The employer's own job description.",
    raw_json={"greenhouse": {"id": "p1"}},
    salary_min=150000.0,
    salary_max=200000.0,
    salary_currency="USD",
    salary_period="year",
)
AGGREGATOR = dict(
    provider_posting_id="p1",
    title="Backend Engineer II",
    url="https://www.indeed.com/viewjob?jk=deadbeef",
    locations=["Austin, TX"],
    body_text="The aggregator's rendering of the same job description.",
    posted_at=datetime(2026, 8, 20, 12, 0),
    raw_json={"job": {"key": "deadbeef"}},
)


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    eng = get_engine(tmp_path)
    ensure_schema(eng)
    return eng


@pytest.fixture()
def company_id(engine: Engine) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )


def _apply(engine: Engine, company_id: int, raw: RawPosting, *, status: str = "partial") -> None:
    apply_board(
        engine,
        BoardSnapshot(
            status=status,  # type: ignore[arg-type]
            postings=[raw],
            url="https://boards.greenhouse.io/acme",
        ),
        company_id,
        insert_run(engine),
    )


def _posting(engine: Engine) -> Any:
    with engine.connect() as conn:
        return conn.execute(select(tables.postings)).one()


def _age_the_row(engine: Engine) -> datetime:
    """Push the row into the state a missing-then-relisted posting is actually in."""
    stale = datetime(2020, 1, 1, 0, 0)
    with engine.begin() as conn:
        conn.execute(
            update(tables.postings).values(
                last_seen_at=stale, consecutive_missing=1, death_strikes=2
            )
        )
    return stale


def test_a_provider_observation_still_refreshes_every_mutable_column(
    engine: Engine, company_id: int
) -> None:
    """VERDICT-NEUTRALITY. A board scan writes exactly what it wrote before D-414(a).

    The declaration defaults to EMPTY, so nothing on the six-provider path changes. Asserted
    column by column against a second observation in which every value differs.
    """
    _apply(engine, company_id, RawPosting(**PROVIDER))  # type: ignore[arg-type]
    second = dict(PROVIDER) | dict(
        title="Staff Backend Engineer",
        url="https://boards.greenhouse.io/acme/jobs/p1?utm=board",
        locations=["Remote - Canada"],
        department="Platform",
        remote_policy="hybrid",
        posted_at=datetime(2026, 8, 3, 12, 0),
        updated_at=datetime(2026, 8, 4, 12, 0),
        body_text="A revised job description.",
        raw_json={"greenhouse": {"id": "p1", "v": 2}},
        salary_min=160000.0,
        salary_max=210000.0,
        salary_currency="CAD",
        salary_period="month",
    )
    _apply(engine, company_id, RawPosting(**second), status="complete")  # type: ignore[arg-type]

    row = _posting(engine)
    assert row.title == "Staff Backend Engineer"
    assert row.normalized_title == "staff backend engineer"
    assert row.url == "https://boards.greenhouse.io/acme/jobs/p1?utm=board"
    assert row.locations_json == ["Remote - Canada"]
    assert row.remote_policy == "hybrid"
    assert row.department == "Platform"
    assert row.posted_at == datetime(2026, 8, 3, 12, 0)
    assert row.updated_at == datetime(2026, 8, 4, 12, 0)
    assert float(row.salary_min) == 160000.0
    assert float(row.salary_max) == 210000.0
    assert row.salary_currency == "CAD"
    assert row.salary_period == "month"
    assert row.raw_json == {"greenhouse": {"id": "p1", "v": 2}}  # decoded dict, never a string
    assert row.body_text == "A revised job description."


def test_a_secondhand_observation_keeps_the_provider_reading_of_every_declared_column(
    engine: Engine, company_id: int
) -> None:
    """The defect itself. `Remote - US` must survive a hit that renders it as `Austin, TX`."""
    _apply(engine, company_id, RawPosting(**PROVIDER))  # type: ignore[arg-type]
    _apply(engine, company_id, RawPosting(**AGGREGATOR, secondhand=ALL_SECONDHAND))  # type: ignore[arg-type]

    row = _posting(engine)
    assert row.locations_json == ["Remote - US"]
    assert row.remote_policy == "remote"
    assert row.title == "Senior Backend Engineer"
    assert row.normalized_title == "senior backend engineer"
    assert row.url == "https://boards.greenhouse.io/acme/jobs/p1"
    assert row.department == "Engineering"
    assert row.posted_at == datetime(2026, 8, 1, 12, 0)
    assert row.updated_at == datetime(2026, 8, 2, 12, 0)
    assert float(row.salary_min) == 150000.0
    assert float(row.salary_max) == 200000.0
    assert row.salary_currency == "USD"
    assert row.salary_period == "year"
    assert row.raw_json == {"greenhouse": {"id": "p1"}}


def test_a_secondhand_observation_still_records_liveness_and_the_new_body(
    engine: Engine, company_id: int
) -> None:
    """Not refreshing structured fields is not the same as not observing the posting.

    A secondhand hit is first-hand evidence of two things -- this posting is on a board RIGHT NOW,
    and here is a JD body -- and both must land. Without this guard, "drop the whole update for a
    secondhand observation" would satisfy the test above while quietly disarming the liveness
    reset that stops a stale strike closing a live posting.
    """
    _apply(engine, company_id, RawPosting(**PROVIDER))  # type: ignore[arg-type]
    stale = _age_the_row(engine)
    before = _posting(engine).content_hash
    _apply(engine, company_id, RawPosting(**AGGREGATOR, secondhand=ALL_SECONDHAND))  # type: ignore[arg-type]

    row = _posting(engine)
    assert row.last_seen_at > stale
    assert row.consecutive_missing == 0
    assert row.death_strikes == 0
    assert row.content_hash != before
    assert row.body_text == "The aggregator's rendering of the same job description."
    with engine.connect() as conn:
        versions = conn.execute(
            select(tables.posting_versions.c.capture_reason).order_by(
                tables.posting_versions.c.id
            )
        ).scalars().all()
    assert list(versions) == ["new", "revised"]


def test_the_insert_path_writes_everything_a_secondhand_observation_carries(
    engine: Engine, company_id: int
) -> None:
    """A row this lane CREATES has no prior observation to preserve.

    Dropping the declared columns here would replace values the lane genuinely holds with schema
    defaults -- a loss, not a preservation -- and `locations_json` would go NULL on every posting
    the lane is the only source for, which is most of the reach the lane exists to buy.
    """
    _apply(engine, company_id, RawPosting(**AGGREGATOR, secondhand=ALL_SECONDHAND))  # type: ignore[arg-type]

    row = _posting(engine)
    assert row.title == "Backend Engineer II"
    assert row.normalized_title == "backend engineer ii"
    assert row.url == "https://www.indeed.com/viewjob?jk=deadbeef"
    assert row.locations_json == ["Austin, TX"]
    assert row.posted_at == datetime(2026, 8, 20, 12, 0)
    assert row.raw_json == {"job": {"key": "deadbeef"}}


def test_a_secondhand_update_keys_the_identity_on_what_the_row_holds(
    engine: Engine, company_id: int
) -> None:
    """An identity naming a value no row holds suppresses against evidence that exists nowhere.

    `write_identities` rewrites a posting's rows on every observation, so the identity has to be
    computed from the persisted title/locations, not from the observation that declined to write
    them.
    """
    _apply(engine, company_id, RawPosting(**PROVIDER))  # type: ignore[arg-type]
    _apply(engine, company_id, RawPosting(**AGGREGATOR, secondhand=ALL_SECONDHAND))  # type: ignore[arg-type]

    row = _posting(engine)
    with engine.connect() as conn:
        stored = {
            r.kind: r.identity_key
            for r in conn.execute(select(tables.posting_identities)).all()
        }

    def expect(title: str, locations: list[str]) -> dict[str, str]:
        return {
            i.kind: i.identity_key
            for i in compute_identities(
                IdentityInputs(
                    posting_id=int(row.id),
                    company_id=company_id,
                    company_name="Acme",
                    provider_posting_id="p1",
                    title=title,
                    locations=locations,
                    content_hash=str(row.content_hash),
                    body_text=str(row.body_text),
                    url=str(row.url),
                    first_seen_at=row.first_seen_at,
                )
            )
        }

    persisted = expect("Senior Backend Engineer", ["Remote - US"])
    observed = expect("Backend Engineer II", ["Austin, TX"])
    assert persisted["company_title_location"] != observed["company_title_location"]
    assert stored == persisted


def test_every_column_the_writer_refreshes_is_classified_exactly_once(
    engine: Engine, company_id: int
) -> None:
    """A column added to `_mutable_fields` must be declarable, or it is silently unprotected.

    The literal below is the contract, restated here rather than read back off the writer: an
    assertion of `_mutable_fields` against itself passes however the writer changes.
    """
    written = set(_mutable_fields(RawPosting(**PROVIDER), datetime(2026, 9, 1)))  # type: ignore[arg-type]
    assert written == {
        "title", "normalized_title", "url", "locations_json", "remote_policy", "department",
        "posted_at", "updated_at", "salary_min", "salary_max", "salary_currency",
        "salary_period", "raw_json", "last_seen_at",
    }
    assert set(_SECONDHAND_COLUMNS) == set(get_args(SecondhandField))
    classified = [column for columns in _SECONDHAND_COLUMNS.values() for column in columns]
    assert len(classified) == len(set(classified))  # no column owned by two declarations
    # `last_seen_at` is the one exclusion, and it is deliberate: it is the observation's OWN
    # claim, never the provider's, so no declaration may withhold it.
    assert set(classified) == written - {"last_seen_at"}
