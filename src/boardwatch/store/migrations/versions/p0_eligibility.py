"""P0 spine: persisted, evidence-linked eligibility AUDIT ledger (D30, reconciles D17).

Immutable and keyed by ALL inputs the verdict depended on — the posting_version, the
profile snapshot, and the rules snapshot (eligibility is profile-dependent; a key that
omits the profile would return a stale verdict after a profile edit). Deterministic runs
are idempotent (partial unique); LLM reruns are recorded, not suppressed. Requirements
and support address immutable locators so the audit trail is genuinely evidence-linked.
Not a mutable score cache — there is no invalidation surface. Evaluator is P2.
"""
import sqlalchemy as sa
from alembic import op

revision = "p0_eligibility"
down_revision = "p0_version_sources"
branch_labels = None
depends_on = None

_LEDGERS = ("eligibility_inputs", "eligibility_evaluations", "eligibility_requirements",
            "eligibility_support")


def upgrade() -> None:
    op.create_table(
        "eligibility_inputs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("posting_version_id", sa.Integer(), nullable=False),
        sa.Column("profile_hash", sa.Text(), nullable=False),
        sa.Column("profile_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("rules_hash", sa.Text(), nullable=False),
        sa.Column("rules_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("input_fingerprint", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["posting_version_id"], ["posting_versions.id"],
                                name=op.f("fk_eligibility_inputs_posting_version_id_posting_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eligibility_inputs")),
        sa.UniqueConstraint("input_fingerprint", name=op.f("uq_eligibility_inputs_input_fingerprint")),
    )
    op.create_table(
        "eligibility_evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("input_id", sa.Integer(), nullable=False),
        sa.Column("engine_kind", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("score", sa.Numeric(), nullable=True),
        sa.Column("raw_output_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("engine_kind IN ('deterministic', 'llm')",
                           name=op.f("ck_eligibility_evaluations_engine_kind_enum")),
        sa.CheckConstraint("verdict IN ('eligible', 'ineligible', 'uncertain')",
                           name=op.f("ck_eligibility_evaluations_verdict_enum")),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 1)",
                           name=op.f("ck_eligibility_evaluations_score_range")),
        sa.ForeignKeyConstraint(["input_id"], ["eligibility_inputs.id"],
                                name=op.f("fk_eligibility_evaluations_input_id_eligibility_inputs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eligibility_evaluations")),
        sa.UniqueConstraint("idempotency_key",
                            name=op.f("uq_eligibility_evaluations_idempotency_key")),
    )
    op.create_index("ix_eligibility_evaluations_input_created", "eligibility_evaluations",
                    ["input_id", "created_at", "id"])
    # Deterministic idempotency: a partial unique index (SQLAlchemy UniqueConstraint can't).
    op.execute("CREATE UNIQUE INDEX uq_eligibility_deterministic "
               "ON eligibility_evaluations(input_id, engine_version) "
               "WHERE engine_kind = 'deterministic'")
    op.create_table(
        "eligibility_requirements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=True),
        sa.Column("requiredness", sa.Text(), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("jd_locator_json", sa.JSON(), nullable=False),
        sa.Column("disposition", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_eligibility_requirements_ordinal_nonneg")),
        sa.CheckConstraint("requiredness IN ('required', 'preferred', 'bonus')",
                           name=op.f("ck_eligibility_requirements_requiredness_enum")),
        sa.CheckConstraint("disposition IN ('met', 'unmet', 'unknown')",
                           name=op.f("ck_eligibility_requirements_disposition_enum")),
        sa.ForeignKeyConstraint(["evaluation_id"], ["eligibility_evaluations.id"],
                                name=op.f("fk_eligibility_requirements_evaluation_id_eligibility_evaluations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eligibility_requirements")),
        sa.UniqueConstraint("evaluation_id", "ordinal",
                            name=op.f("uq_eligibility_requirements_evaluation_id_ordinal")),
    )
    op.create_table(
        "eligibility_support",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("profile_locator_json", sa.JSON(), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("support_kind", sa.Text(), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_eligibility_support_ordinal_nonneg")),
        sa.ForeignKeyConstraint(["requirement_id"], ["eligibility_requirements.id"],
                                name=op.f("fk_eligibility_support_requirement_id_eligibility_requirements")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eligibility_support")),
        sa.UniqueConstraint("requirement_id", "ordinal",
                            name=op.f("uq_eligibility_support_requirement_id_ordinal")),
    )
    for t in _LEDGERS:
        op.execute(f"CREATE TRIGGER {t}_no_update BEFORE UPDATE ON {t} "
                   f"BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END")
        op.execute(f"CREATE TRIGGER {t}_no_delete BEFORE DELETE ON {t} "
                   f"BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END")


def downgrade() -> None:
    for t in _LEDGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_delete")
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_update")
    op.drop_table("eligibility_support")
    op.drop_table("eligibility_requirements")
    op.execute("DROP INDEX IF EXISTS uq_eligibility_deterministic")
    op.drop_index("ix_eligibility_evaluations_input_created", table_name="eligibility_evaluations")
    op.drop_table("eligibility_evaluations")
    op.drop_table("eligibility_inputs")
