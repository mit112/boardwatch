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
    text,
)

from boardwatch.core.identity_kinds import IDENTITY_KIND_NAMES
from boardwatch.core.ledger import DISPOSITIONS, PERMANENT_DISPOSITIONS, REASON_NAMES

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
    # 'lane' is a company an aggregator lane discovered: neither shipped in the registry nor
    # typed by the user (D-285). Lane rows are inserted unwatched, so they never enter the
    # scan corpus or the coverage corpus.
    CheckConstraint("source IN ('registry', 'user', 'lane')", name="source_enum"),
    CheckConstraint(
        "last_health IN ('ok', 'empty', 'dead', 'error', 'unreachable')", name="last_health_enum"
    ),
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
    # D-325. Consecutive `refetch_gone` liveness probes against this posting's OWN url, for the
    # postings whose company is `watched = 0` and which the board scanner therefore cannot
    # produce any absence signal for (D-314). Kept apart from `consecutive_missing` on purpose:
    # that column counts complete-board absences, and one counter fed by two different signals
    # could close a posting on one absence plus one 404 with no report able to say which.
    Column("death_strikes", Integer, nullable=False, default=0),
    # When the death probe last asked. NULL = never asked, which sorts first in the
    # least-recently-probed order so the sweep works the corpus front to back.
    Column("last_death_probe_at", DateTime, nullable=True),
    Column("content_hash", Text, nullable=False),
    Column("body_text", Text, nullable=False),
    Column("raw_json", JSON, nullable=True),
    Column("salary_min", Numeric, nullable=True),
    Column("salary_max", Numeric, nullable=True),
    Column("salary_currency", Text, nullable=True),
    Column("salary_period", Text, nullable=True),
    # Canonical-job annotation link (D28). Real FK; NOT-NULL enforced by trigger
    # (SQLite ALTER cannot add a NOT NULL column without a rebuild).
    Column("job_id", Integer, ForeignKey("jobs.id"), nullable=True),
    UniqueConstraint("company_id", "provider_posting_id"),
    Index("ix_postings_status_posted_at", "status", "posted_at"),
    Index("ix_postings_content_hash", "content_hash"),
    Index("ix_postings_job_id", "job_id"),
    CheckConstraint(
        "remote_policy IN ('remote', 'hybrid', 'onsite', 'unknown')", name="remote_policy_enum"
    ),
    CheckConstraint("status IN ('open', 'closed')", name="status_enum"),
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("created_at", DateTime, nullable=False),
)

job_grouping_events = Table(
    "job_grouping_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("posting_id", Integer, ForeignKey("postings.id"), nullable=False),
    Column("from_job_id", Integer, ForeignKey("jobs.id"), nullable=True),
    Column("to_job_id", Integer, ForeignKey("jobs.id"), nullable=False),
    Column("method", Text, nullable=False),
    Column("algorithm_version", Text, nullable=True),
    Column("evidence_json", JSON, nullable=True),
    Column("created_at", DateTime, nullable=False),
    Index("ix_job_grouping_events_posting_id", "posting_id", "id"),
    sqlite_autoincrement=True,
)

posting_versions = Table(
    "posting_versions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("posting_id", Integer, ForeignKey("postings.id"), nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("body_text", Text, nullable=False),
    Column("captured_at", DateTime, nullable=False),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=True),
    Column("capture_reason", Text, nullable=False),
    Index("ix_posting_versions_posting_captured", "posting_id", "captured_at", "id"),
    CheckConstraint(
        "capture_reason IN ('new', 'revised', 'backfill_original', 'backfill_from_revised_event')",
        name="capture_reason_enum",
    ),
)

posting_version_sources = Table(
    "posting_version_sources",
    metadata,
    Column("posting_version_id", Integer, ForeignKey("posting_versions.id"), primary_key=True),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=True),
    Column("source_url", Text, nullable=False),
    Column("source_record_id", Text, nullable=False),
    Column("observed_at", DateTime, nullable=False),
    Column("payload_hash", Text, nullable=True),
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
    # Coverage instrument (D-271). Nullable: NULL means the board stated no total, which is
    # not the same claim as zero.
    Column("board_reported_total", Integer, nullable=True),
    Column("board_enumerated", Integer, nullable=True),
    Column("detail_deferred", Integer, nullable=True),
    Column("board_total_censored", Integer, nullable=True),
    # Which subsystem wrote this row (D-285). A lane touching an already-watched board writes a
    # SECOND row for the same (company_id, run_id); coverage joins one BoardCoverage per row, so
    # without this the company is counted twice. Defaulted 'board': every pre-existing row is one.
    Column("scan_kind", Text, nullable=False, server_default="board"),
    CheckConstraint(
        "status IN ('complete', 'partial', 'failed', 'unchanged')", name="status_enum"
    ),
    CheckConstraint("scan_kind IN ('board', 'lane')", name="scan_kind_enum"),
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
    Column("resume_max_pages", Integer, nullable=False, server_default="1"),
    # D-246. NOT NULL with a server default: `None` and "any" would otherwise be two hash
    # inputs for one behaviour, and `hashing.canonical` keeps an explicit null distinct from
    # a missing key. Closed vocabulary enforced in Python at the write site (ProfileInput),
    # not by a CHECK — retrofitting one to SQLite costs a full table rebuild.
    Column("target_seniority_band", Text, nullable=False, server_default="any"),
    Column("eligibility_facts_json", JSON, nullable=True),
    Column("eligibility_policy_json", JSON, nullable=True),
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
    # The rest of ScanSummary's four-way split (D-341). Nullable and NOT defaulted to 0: NULL
    # means a run predating this column, or one whose scan never ran, which absent≠zero keeps
    # distinct from a scan that genuinely found zero partial/unchanged/failed boards.
    Column("boards_partial", Integer, nullable=True),
    Column("boards_unchanged", Integer, nullable=True),
    Column("boards_failed", Integer, nullable=True),
    # The standing eligible corpus this run measured, lifted out of the funnel artifact so a
    # cross-run query can reach it (D-371). `corpus_candidates` is eligible + uncertain — the
    # deliverable verdicts — folded here because this is a rate numerator for the
    # corpus-regression detector, not a report; the funnel keeps the verdict split unfolded.
    # Nullable and NOT defaulted to 0, for the same reason as the board split above and with
    # sharper teeth: a defaulted 0 would make every pre-instrumentation run read as a
    # MEASURED empty corpus, which is the exact alarm state the detector watches for.
    Column("corpus_open", Integer, nullable=True),
    Column("corpus_evaluated", Integer, nullable=True),
    Column("corpus_candidates", Integer, nullable=True),
    Column("postings_seen", Integer, nullable=True),
    Column("new_count", Integer, nullable=True),
    Column("closed_count", Integer, nullable=True),
    Column("reopened_count", Integer, nullable=True),
    Column("errors_json", JSON, nullable=True),
    # Closed catalog: running | ok | failed. Enforced in Python at the write site
    # (RunStatus), not by a CHECK constraint, because adding one to an existing SQLite
    # table costs a full rebuild and this column has no backfill to protect.
    Column("status", Text, nullable=False, server_default="running"),
)

eligibility_inputs = Table(
    "eligibility_inputs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("posting_version_id", Integer, ForeignKey("posting_versions.id"), nullable=False),
    Column("profile_hash", Text, nullable=False),
    Column("profile_snapshot_json", JSON, nullable=False),
    Column("rules_hash", Text, nullable=False),
    Column("rules_snapshot_json", JSON, nullable=False),
    Column("input_fingerprint", Text, nullable=False),
    Column("created_at", DateTime, nullable=False),
    UniqueConstraint("input_fingerprint"),
    # Serves the correlated `evaluated` anti-join in eligibility/preflight.py, which every
    # `boardwatch top` runs before it prints anything. Without it the only usable index is
    # `uq_eligibility_deterministic` on the OTHER table, so SQLite re-scans that index and
    # rowid-probes into this one once PER open posting. Measured on a copy of a live
    # 24,073-posting store: 141.54 s, against 0.14 s with this index. Column order matches
    # the subquery's predicates — correlated equality on posting_version_id first, then the
    # two identity hashes.
    Index("ix_eligibility_inputs_version_identity",
          "posting_version_id", "profile_hash", "rules_hash"),
)

eligibility_evaluations = Table(
    "eligibility_evaluations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("input_id", Integer, ForeignKey("eligibility_inputs.id"), nullable=False),
    Column("engine_kind", Text, nullable=False),
    Column("engine_version", Text, nullable=False),
    Column("provider", Text, nullable=True),
    Column("model", Text, nullable=True),
    Column("prompt_version", Text, nullable=True),
    Column("idempotency_key", Text, nullable=True),
    Column("verdict", Text, nullable=False),
    Column("score", Numeric, nullable=True),
    Column("raw_output_json", JSON, nullable=True),
    Column("created_at", DateTime, nullable=False),
    # NULL = written before run attribution existed; never 0, never "run produced nothing".
    # Append-only table, so this is set at INSERT and can never be backfilled.
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=True),
    UniqueConstraint("idempotency_key"),
    Index("ix_eligibility_evaluations_input_created", "input_id", "created_at", "id"),
    # Deterministic idempotency (D30): partial unique index, declared here ONLY so the
    # schema-drift check (test_migrations_match_metadata) sees parity with the migration,
    # which is the sole DDL-executing source (op.execute, not Alembic autogenerate/create_all
    # — see p0_eligibility.py). UniqueConstraint cannot express a partial predicate; Index can.
    Index("uq_eligibility_deterministic", "input_id", "engine_version", unique=True,
          sqlite_where=text("engine_kind = 'deterministic'")),
    CheckConstraint("engine_kind IN ('deterministic', 'llm')", name="engine_kind_enum"),
    CheckConstraint("verdict IN ('eligible', 'ineligible', 'uncertain')", name="verdict_enum"),
    CheckConstraint("score IS NULL OR (score >= 0 AND score <= 1)", name="score_range"),
)

eligibility_requirements = Table(
    "eligibility_requirements",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("evaluation_id", Integer, ForeignKey("eligibility_evaluations.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("rule_id", Text, nullable=True),
    Column("requiredness", Text, nullable=False),
    Column("requirement_text", Text, nullable=False),
    Column("jd_locator_json", JSON, nullable=False),
    Column("disposition", Text, nullable=False),
    Column("rationale", Text, nullable=True),
    UniqueConstraint("evaluation_id", "ordinal"),
    CheckConstraint("ordinal >= 0", name="ordinal_nonneg"),
    CheckConstraint("requiredness IN ('required', 'preferred', 'bonus')", name="requiredness_enum"),
    CheckConstraint("disposition IN ('met', 'unmet', 'unknown')", name="disposition_enum"),
)

eligibility_support = Table(
    "eligibility_support",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("requirement_id", Integer, ForeignKey("eligibility_requirements.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("profile_locator_json", JSON, nullable=False),
    Column("evidence_quote", Text, nullable=False),
    Column("support_kind", Text, nullable=False),
    UniqueConstraint("requirement_id", "ordinal"),
    CheckConstraint("ordinal >= 0", name="ordinal_nonneg"),
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

applications = Table(
    "applications",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("job_id", Integer, ForeignKey("jobs.id"), nullable=False),
    Column("posting_version_id", Integer, ForeignKey("posting_versions.id"), nullable=True),
    Column("attempt_no", Integer, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    Column("submitted_at", DateTime, nullable=True),
    UniqueConstraint("job_id", "attempt_no"),
    CheckConstraint(
        "status IN ('interested', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn')",
        name="status_enum",
    ),
)

application_events = Table(
    "application_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("application_id", Integer, ForeignKey("applications.id"), nullable=False),
    Column("event_type", Text, nullable=False),
    Column("from_status", Text, nullable=True),
    Column("to_status", Text, nullable=True),
    Column("occurred_at", DateTime, nullable=False),
    Column("recorded_at", DateTime, nullable=False),
    Column("source", Text, nullable=False),
    Column("note", Text, nullable=True),
    Column("detail_json", JSON, nullable=True),
    Index("ix_application_events_application_id", "application_id", "id"),
    sqlite_autoincrement=True,
)

artifacts = Table(
    "artifacts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("job_id", Integer, ForeignKey("jobs.id"), nullable=True),
    Column("posting_version_id", Integer, ForeignKey("posting_versions.id"), nullable=True),
    Column("application_id", Integer, ForeignKey("applications.id"), nullable=True),
    Column("kind", Text, nullable=False),
    Column("uri", Text, nullable=False),
    Column("content_hash", Text, nullable=True),
    Column("generator", Text, nullable=True),
    Column("generator_version", Text, nullable=True),
    Column("media_type", Text, nullable=True),
    Column("byte_size", Integer, nullable=True),
    Column("meta_json", JSON, nullable=True),
    Column("created_at", DateTime, nullable=False),
    # NULL = written before run attribution existed; never 0, never "run produced nothing".
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=True),
    Index("ix_artifacts_job_id", "job_id"),
)

artifact_derivations = Table(
    "artifact_derivations",
    metadata,
    Column("artifact_id", Integer, ForeignKey("artifacts.id"), primary_key=True),
    Column("parent_artifact_id", Integer, ForeignKey("artifacts.id"), primary_key=True),
    Column("relation", Text, primary_key=True),
    Column("created_at", DateTime, nullable=False),
)

# The kind catalog is closed: an out-of-catalog value is a failure, never a new bucket.
# Enforced twice on purpose — a typed UnknownIdentityKind at the computation site, and
# this CHECK at the store, so a direct INSERT cannot invent one either.
_IDENTITY_KIND_LIST = ", ".join(f"'{name}'" for name in IDENTITY_KIND_NAMES)

posting_identities = Table(
    "posting_identities",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("posting_id", Integer, ForeignKey("postings.id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("identity_key", Text, nullable=False),
    Column("algorithm_version", Text, nullable=False),
    Column("created_at", DateTime, nullable=False),
    UniqueConstraint("posting_id", "kind", "algorithm_version"),
    CheckConstraint(f"kind IN ({_IDENTITY_KIND_LIST})", name="identity_kind_enum"),
    Index("ix_posting_identities_key", "kind", "identity_key"),
)

# Both catalogs are closed, and both are enforced twice: typed at the write site
# (core/ledger.py's UnknownDisposition / UnknownDispositionReason) and again here, so a direct
# INSERT cannot invent a bucket either.
_DISPOSITION_LIST = ", ".join(f"'{name}'" for name in DISPOSITIONS)
_REASON_LIST = ", ".join(f"'{name}'" for name in REASON_NAMES)
_PERMANENT_LIST = ", ".join(f"'{name}'" for name in sorted(PERMANENT_DISPOSITIONS))

job_dispositions = Table(
    "job_dispositions",
    metadata,
    # One row per job, upserted — the spec asks for monotonic UPSERTS, and an append-only log
    # cannot be upserted (P6 slice 2 design §2.1). The append-only trail lives in
    # job_grouping_events, which is the half that mutates a key another table reads.
    Column("job_id", Integer, ForeignKey("jobs.id"), primary_key=True),
    Column("disposition", Text, nullable=False),
    Column("reason", Text, nullable=False),
    # NOT NULL exactly for the permanent tier; NULL exactly for `seen`. Of the three CHECKs below,
    # the permanence one is the spec's "built/skipped permanent and seen TTL'd" plus "a
    # policy-version stamp on permanent dispositions", expressed where a caller cannot forget it.
    Column("policy_version", Text, nullable=True),
    Column("expires_at", DateTime, nullable=True),
    # Set by the drain instead of deleting the row, so draining a bucket does not erase it.
    Column("reopened_at", DateTime, nullable=True),
    Column("first_decided_at", DateTime, nullable=False),
    Column("decided_at", DateTime, nullable=False),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=True),
    CheckConstraint(f"disposition IN ({_DISPOSITION_LIST})", name="disposition_enum"),
    CheckConstraint(f"reason IN ({_REASON_LIST})", name="disposition_reason_enum"),
    # Both tiers stated explicitly. A single biconditional
    # `(disposition IN permanent) = (policy_version IS NOT NULL AND expires_at IS NULL)` looks
    # equivalent and is not: it admits `(seen, NULL, NULL)` — a `seen` row with NO TTL, which
    # suppresses forever and which `stale_dispositions` cannot even list, because that read keys on
    # a non-NULL policy_version — and `(seen, stamp, TTL)`. Do not "simplify" this back; the store
    # tests will catch it, but the reason is not obvious from the predicate.
    CheckConstraint(
        f"(disposition IN ({_PERMANENT_LIST})"
        " AND policy_version IS NOT NULL AND expires_at IS NULL)"
        f" OR (disposition NOT IN ({_PERMANENT_LIST})"
        " AND policy_version IS NULL AND expires_at IS NOT NULL)",
        name="permanence_wellformed",
    ),
    Index("ix_job_dispositions_expires_at", "expires_at"),
)
