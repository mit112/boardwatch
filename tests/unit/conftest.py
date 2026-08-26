"""Shared seeding for the P5 tests: one company, six postings, six events."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert

from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.events import append_event
from boardwatch.store.queries import insert_run
from boardwatch.store.tables import companies, jobs, posting_versions, postings

# Naive UTC, matching boardwatch.core.clock.utcnow() (A2).
NOW = datetime(2026, 7, 30, 12, 0, 0)

# The JD body every seeded posting carries. The `Python` mention is LOAD-BEARING: the titles
# below are single words, which the role gate reads as `uncertain`, so a body that recognises
# no taxonomy term at all would put every posting in the zero-signal quarantine and the
# ranking tests that consume this fixture would assert against an empty shortlist.
BODY = "We are hiring a {title} engineer. Python experience required."

# Ordered: posting ids and event ids both follow this sequence.
EVENTS = (
    ("alpha", "new"), ("beta", "new"), ("gamma", "reopened"),
    ("delta", "revised"), ("epsilon", "closed"), ("zeta", "closed"),
)


@dataclass(frozen=True)
class Seed:
    engine: Engine
    posting_ids: dict[str, int]
    event_ids: dict[str, int]

    @property
    def max_event_id(self) -> int:
        return max(self.event_ids.values())


@pytest.fixture()
def seeded_events() -> Callable[[Path], Seed]:
    def seed(data_dir: Path) -> Seed:
        engine = get_engine(data_dir)
        ensure_schema(engine)
        run_id = insert_run(engine)
        posting_ids: dict[str, int] = {}
        event_ids: dict[str, int] = {}
        with engine.begin() as conn:
            company_id = int(
                conn.execute(
                    insert(companies).values(
                        name="Acme", provider="greenhouse", slug="acme",
                        source="user", watched=True,
                    )
                ).inserted_primary_key[0]
            )
            for title, kind in EVENTS:
                job_id = int(
                    conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0]
                )
                posting_id = int(
                    conn.execute(
                        insert(postings).values(
                            company_id=company_id, job_id=job_id,
                            provider_posting_id=f"p-{title}", title=title,
                            normalized_title=title, url=f"https://example.test/{title}",
                            locations_json=["Remote"], remote_policy="remote",
                            first_seen_at=NOW, last_seen_at=NOW,
                            status="closed" if kind == "closed" else "open",
                            closed_at=NOW if kind == "closed" else None,
                            consecutive_missing=0, content_hash=f"h-{title}",
                            body_text=BODY.format(title=title),
                        )
                    ).inserted_primary_key[0]
                )
                conn.execute(
                    insert(posting_versions).values(
                        posting_id=posting_id, content_hash=f"h-{title}",
                        body_text=BODY.format(title=title),
                        captured_at=NOW, capture_reason="new",
                    )
                )
                posting_ids[title] = posting_id
                event_ids[title] = append_event(conn, posting_id, kind, run_id)
        return Seed(engine=engine, posting_ids=posting_ids, event_ids=event_ids)

    return seed
