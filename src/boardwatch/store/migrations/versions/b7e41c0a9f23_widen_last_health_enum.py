"""widen last_health_enum to include unreachable (D27)

Revision ID: b7e41c0a9f23
Revises: 8df3b3809bba
Create Date: 2026-06-12
"""

import sqlalchemy as sa
from alembic import op

revision = "b7e41c0a9f23"
down_revision = "8df3b3809bba"
branch_labels = None
depends_on = None

# The CheckConstraint is BUILT with the bare token (the convention renders it); but
# batch drop/create must reference the RENDERED name, because the copy_from table's
# constraint resolves to ck_companies_last_health_enum — a bare-token drop raises
# "No such constraint" (Codex plan findings r1+r3, verified by reproduction).
TOKEN = "last_health_enum"            # used when BUILDING the copy_from constraint
RENDERED = "ck_companies_last_health_enum"  # used in drop_constraint / create_check_constraint
FOUR = "last_health IN ('ok', 'empty', 'dead', 'error')"
FIVE = "last_health IN ('ok', 'empty', 'dead', 'error', 'unreachable')"
_NAMING = {  # MUST equal tables.py's MetaData convention so the copy_from CK renders identically
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _companies(check_sql: str) -> sa.Table:
    """Reflection-free companies definition carrying check_sql, handed to
    batch_alter_table as copy_from (plan deviation 1). It carries the shipped
    naming convention, and BUILDS the CK with the bare TOKEN so the convention
    renders it to ck_companies_last_health_enum — matching what drop/create target."""
    meta = sa.MetaData(naming_convention=_NAMING)
    return sa.Table(
        "companies",
        meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column("tags_json", sa.JSON, nullable=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("watched", sa.Boolean, nullable=False),
        sa.Column("last_health", sa.Text, nullable=True),
        sa.Column("last_ok_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("provider", "slug"),
        sa.CheckConstraint("source IN ('registry', 'user')", name="source_enum"),
        sa.CheckConstraint(check_sql, name=TOKEN),  # token -> convention renders the full name
    )


def upgrade() -> None:
    with op.batch_alter_table(
        "companies", copy_from=_companies(FOUR), recreate="always"
    ) as batch_op:
        # op.f() marks the name as ALREADY-FINAL so the convention is not applied again
        # (a bare RENDERED would re-prefix to ck_companies_ck_companies_last_health_enum)
        batch_op.drop_constraint(op.f(RENDERED), type_="check")
        batch_op.create_check_constraint(op.f(RENDERED), FIVE)


def downgrade() -> None:
    # conservative data policy (round 6): unreachable and error both mean "probe failed";
    # last_ok_at is untouched. Remap BEFORE narrowing so no row violates the old CHECK.
    op.execute("UPDATE companies SET last_health = 'error' WHERE last_health = 'unreachable'")
    with op.batch_alter_table(
        "companies", copy_from=_companies(FIVE), recreate="always"
    ) as batch_op:
        batch_op.drop_constraint(op.f(RENDERED), type_="check")
        batch_op.create_check_constraint(op.f(RENDERED), FOUR)
