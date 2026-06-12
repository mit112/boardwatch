"""Schema v1: 9 SQLAlchemy Core tables with named constraints (D18, D20).

Every table has an integer PK (except posting_events which uses autoincrement for
monotonic id space per D18, and app_state/http_cache which use text PKs).  All
CHECK constraints are named for stable Alembic autogenerate diffs.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
)

# Convention: naming convention is set at the MetaData level so Alembic
# autogenerate produces stable, predictable constraint names.
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

companies = Table(
    "companies",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("provider", Text, nullable=False),
    Column("slug", Text, nullable=False),
    Column("tags_json", JSON, nullable=True),
    Column("source", Text, nullable=False),
    Column("watched", Boolean, nullable=False, default=False),
    Column("last_health", Text, nullable=True),
    Column("last_ok_at", DateTime, nullable=True),
    UniqueConstraint("provider", "slug"),
    CheckConstraint("source IN ('registry', 'user')", name="source_enum"),
    CheckConstraint("last_health IN ('ok', 'empty', 'dead', 'error')", name="last_health_enum"),
)

postings = Table(
    "postings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("company_id", Integer, ForeignKey("companies.id"), nullable=False),
    Column("provider_posting_id", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("normalized_title", Text, nullable=False),
    Column("url", Text, nullable=True),
    Column("locations_json", JSON, nullable=True),
    Column("remote_policy", Text, nullable=False, default="unknown"),
    Column("department", Text, nullable=True),
    Column("posted_at", DateTime, nullable=True),
    Column("updated_at", DateTime, nullable=True),
    Column("first_seen_at", DateTime, nullable=False),
    Column("last_seen_at", DateTime, nullable=False),
    Column("status", Text, nullable=False, default="open"),
    Column("closed_at", DateTime, nullable=True),
    Column("consecutive_missing", Integer, nullable=False, default=0),
    Column("content_hash", Text, nullable=False),
    Column("body_text", Text, nullable=False),
    Column("raw_json", JSON, nullable=True),
    Column("salary_min", Numeric, nullable=True),
    Column("salary_max", Numeric, nullable=True),
    Column("salary_currency", Text, nullable=True),
    Column("salary_period", Text, nullable=True),
    UniqueConstraint("company_id", "provider_posting_id"),
    Index("ix_postings_status_posted_at", "status", "posted_at"),
    Index("ix_postings_content_hash", "content_hash"),
    CheckConstraint(
        "remote_policy IN ('remote', 'hybrid', 'onsite', 'unknown')", name="remote_policy_enum"
    ),
    CheckConstraint("status IN ('open', 'closed')", name="status_enum"),
)

board_scans = Table(
    "board_scans",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=False),
    Column("company_id", Integer, ForeignKey("companies.id"), nullable=False),
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime, nullable=False),
    Column("status", Text, nullable=False),
    Column("postings_listed", Integer, nullable=False, default=0),
    Column("error", Text, nullable=True),
    CheckConstraint(
        "status IN ('complete', 'partial', 'failed', 'unchanged')", name="status_enum"
    ),
)

posting_events = Table(
    "posting_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("posting_id", Integer, ForeignKey("postings.id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=False),
    Column("created_at", DateTime, nullable=False),
    CheckConstraint("kind IN ('new', 'reopened', 'closed', 'revised')", name="kind_enum"),
    sqlite_autoincrement=True,  # D18: the monotonic cursor space — ids are never reused
)

extractions = Table(
    "extractions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("posting_id", Integer, ForeignKey("postings.id"), nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("engine_version", Text, nullable=False),
    Column("json", JSON, nullable=False),
    Column("created_at", DateTime, nullable=False),
    UniqueConstraint("posting_id", "content_hash", "kind", "engine_version"),
    CheckConstraint("kind IN ('taxonomy')", name="kind_enum"),
)

profile = Table(
    "profile",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("text", Text, nullable=False),
    Column("skills_json", JSON, nullable=True),
    Column("taxonomy_version", Text, nullable=True),
    Column("target_titles_json", JSON, nullable=True),
    Column("exclude_titles_json", JSON, nullable=True),
    Column("locations_json", JSON, nullable=True),
    Column("remote_only", Boolean, nullable=False, default=False),
    Column("updated_at", DateTime, nullable=False),
    CheckConstraint("id = 1", name="singleton"),
)

runs = Table(
    "runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime, nullable=True),
    Column("boards_attempted", Integer, nullable=False, default=0),
    Column("boards_complete", Integer, nullable=True),
    Column("postings_seen", Integer, nullable=True),
    Column("new_count", Integer, nullable=True),
    Column("closed_count", Integer, nullable=True),
    Column("reopened_count", Integer, nullable=True),
    Column("errors_json", JSON, nullable=True),
)

app_state = Table(
    "app_state",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=True),
)

http_cache = Table(
    "http_cache",
    metadata,
    Column("url", Text, primary_key=True),
    Column("etag", Text, nullable=True),
    Column("last_modified", Text, nullable=True),
    Column("fetched_at", DateTime, nullable=False),
    Column("status", Integer, nullable=False),
)
