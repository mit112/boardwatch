"""D-285: lane-discovered companies get their own `source`, and lane scans their own kind.

Two changes, one revision, because they are one decision: a lane may write into `companies`
and `board_scans`, and both rows must stay distinguishable from what a board scan wrote.

1. `companies.source` widens from `('registry','user')` to `('registry','user','lane')`. A
   lane-discovered company was neither shipped in the registry nor typed by the user, and
   reusing `'registry'` was rejected — it would make the shipped registry unauditable.
   Widening a CHECK needs a table rebuild on SQLite, so this is `batch_alter_table` with an
   explicit `copy_from`, the path b7e41c0a9f23 established.

2. `board_scans.scan_kind` TEXT NOT NULL DEFAULT 'board', CHECK IN ('board','lane'). Without
   it a lane touching an already-watched board writes a SECOND `board_scans` row for the same
   `(company_id, run_id)`, and `coverage_queries.load_board_coverage` emits one `BoardCoverage`
   per joined row — so the company appears twice and `corpus_boards` inflates. The default is
   correct for every existing row: everything already in the table was written by a board scan.
   ALTER TABLE ADD COLUMN cannot carry a CHECK on SQLite, so this rides the same rebuild.
"""

import sqlalchemy as sa
from alembic import op

revision = "p_lane_companies"
down_revision = "p_board_coverage"
branch_labels = None
depends_on = None

# As in b7e41c0a9f23: the CK is BUILT with the bare token so the naming convention renders it,
# but drop/create must reference the RENDERED name or SQLite raises "No such constraint".
SOURCE_TOKEN = "source_enum"
SOURCE_RENDERED = "ck_companies_source_enum"
SOURCE_TWO = "source IN ('registry', 'user')"
SOURCE_THREE = "source IN ('registry', 'user', 'lane')"

SCAN_KIND_TOKEN = "scan_kind_enum"
SCAN_KIND_RENDERED = "ck_board_scans_scan_kind_enum"
SCAN_KIND_CHECK = "scan_kind IN ('board', 'lane')"

# `board_scans` already carries a CK named `status_enum`; the rebuild must re-declare it or the
# copy would silently drop it.
BOARD_STATUS_CHECK = "status IN ('complete', 'partial', 'failed', 'unchanged')"

_NAMING = {  # MUST equal tables.py's MetaData convention so copy_from's CKs render identically
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _companies(source_check: str) -> sa.Table:
    """Reflection-free `companies` as it stands at p_board_coverage, handed to
    batch_alter_table as copy_from. No column has been added since b7e41c0a9f23."""
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
        sa.CheckConstraint(source_check, name=SOURCE_TOKEN),
        sa.CheckConstraint(
            "last_health IN ('ok', 'empty', 'dead', 'error', 'unreachable')",
            name="last_health_enum",
        ),
    )


def _board_scans(*, with_scan_kind: bool) -> sa.Table:
    """Reflection-free `board_scans`, with or without the new column — the `False` form is the
    pre-migration table (copy_from on upgrade), the `True` form the post-migration one."""
    meta = sa.MetaData(naming_convention=_NAMING)
    columns: list[sa.Column] = [
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("postings_listed", sa.Integer, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("board_reported_total", sa.Integer, nullable=True),
        sa.Column("board_enumerated", sa.Integer, nullable=True),
        sa.Column("detail_deferred", sa.Integer, nullable=True),
        sa.Column("board_total_censored", sa.Integer, nullable=True),
    ]
    constraints: list[sa.SchemaItem] = [
        sa.CheckConstraint(BOARD_STATUS_CHECK, name="status_enum"),
    ]
    if with_scan_kind:
        columns.append(
            sa.Column("scan_kind", sa.Text, nullable=False, server_default="board")
        )
        constraints.append(sa.CheckConstraint(SCAN_KIND_CHECK, name=SCAN_KIND_TOKEN))
    return sa.Table("board_scans", meta, *columns, *constraints)


def upgrade() -> None:
    with op.batch_alter_table(
        "companies", copy_from=_companies(SOURCE_TWO), recreate="always"
    ) as batch_op:
        # op.f() marks the name as ALREADY-FINAL so the convention is not applied twice.
        batch_op.drop_constraint(op.f(SOURCE_RENDERED), type_="check")
        batch_op.create_check_constraint(op.f(SOURCE_RENDERED), SOURCE_THREE)
    with op.batch_alter_table(
        "board_scans", copy_from=_board_scans(with_scan_kind=False), recreate="always"
    ) as batch_op:
        batch_op.add_column(
            sa.Column("scan_kind", sa.Text, nullable=False, server_default="board")
        )
        batch_op.create_check_constraint(op.f(SCAN_KIND_RENDERED), SCAN_KIND_CHECK)


def downgrade() -> None:
    # A rebuild does not re-validate existing rows, so anything the widened schema allowed
    # would survive the narrowing as silently illegal data. Both kinds are deleted rather than
    # remapped: unlike b7e41c0a9f23's health probe, a lane row has no honest board equivalent —
    # calling a lane scan a board scan is what `scan_kind` exists to prevent, and it would
    # restore the coverage double-count. Nothing is lost that a lane run cannot rediscover.
    op.execute("DELETE FROM board_scans WHERE scan_kind = 'lane'")
    op.execute(
        "DELETE FROM board_scans WHERE company_id IN "
        "(SELECT id FROM companies WHERE source = 'lane')"
    )
    op.execute("DELETE FROM companies WHERE source = 'lane'")
    with op.batch_alter_table(
        "board_scans", copy_from=_board_scans(with_scan_kind=True), recreate="always"
    ) as batch_op:
        batch_op.drop_constraint(op.f(SCAN_KIND_RENDERED), type_="check")
        batch_op.drop_column("scan_kind")
    with op.batch_alter_table(
        "companies", copy_from=_companies(SOURCE_THREE), recreate="always"
    ) as batch_op:
        batch_op.drop_constraint(op.f(SOURCE_RENDERED), type_="check")
        batch_op.create_check_constraint(op.f(SOURCE_RENDERED), SOURCE_TWO)
