"""T363: keep each eligibility snapshot once.

`eligibility_inputs` carried a copy of its profile snapshot (502 B) and its rules snapshot
(352 B) on every row: 6.2M rows over 3 distinct profile hashes and 14 distinct rules hashes,
5.3 GB of the table's 8.46 GB. Now `eligibility_snapshots(kind, hash, snapshot_json)` holds each
snapshot once and `eligibility_inputs` keeps the two hash columns it already had, so a reader joins
through the hash.

This is a real rebuild: SQLite cannot drop a column without rewriting the table, and the rebuild
keeps the old table until every input is proven to resolve to its original stored bytes. The steps,
in one transaction:

1. Read the table once and refuse (`EligibilitySnapshotConflict`) if two rows with one hash carry
   different stored bytes. The hash covers canonical JSON, the column holds what the JSON type wrote,
   so the comparison is on stored values, never on hashes.
2. Create `eligibility_snapshots` (with the append-only triggers) and fill it from step 1.
3. Create `eligibility_inputs_new` without the two JSON columns and copy every row, ids unchanged:
   `eligibility_evaluations.input_id` points at them.
4. Check that every old row has a new row with the same columns, and that its profile and rules hashes
   resolve to snapshots byte-identical to the old row's JSON. A mismatch aborts and rolls back.
5. Drop the old table (its index and triggers go with it), rename the new one into place, and
   recreate the index and the append-only triggers.

The order is create-new, drop-old, rename-new on purpose: renaming the OLD table aside would rewrite
the foreign key of `eligibility_evaluations` to follow it.

ONE transaction, and it is the transaction that stamps the revision. Alembic's SQLite impl has no
transactional DDL, so without an explicit BEGIN each CREATE and DROP would commit alone, and a failure at
step 4 would leave a half-built schema the next start cannot repair. The BEGIN is issued here and never
COMMITted here: alembic wraps each migration and its `alembic_version` stamp in one SQLAlchemy
transaction, whose commit is the driver's `commit()`, and the sqlite3 driver commits whatever
transaction is open on the connection, ours included. So the rebuild and the stamp become durable
together or not at all. A COMMIT in this callback would leave a window, after the commit and before the
stamp, where the store holds the new schema under the old revision and the next start re-runs an upgrade
that can no longer succeed. The transaction's write-ahead log grows by the size of the NEW table and its
two indexes, not by the table it replaces: the drop frees pages without rewriting them. The file does
not shrink. The freed pages join the freelist, and only a VACUUM returns them to the filesystem;
nothing here runs one.

Downgrade restores the old shape: the JSON columns are filled from the snapshot table and checked the
same way. A snapshot written after the upgrade is stored once, first copy wins, so its bytes can
differ from a later input's own copy in key order only (the hash covers canonical JSON).
"""

from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "p_eligibility_snapshots"
down_revision = "p_listing_runs"
branch_labels = None
depends_on = None

_BATCH = 50_000
_INDEX = "ix_eligibility_inputs_version_identity"


class EligibilitySnapshotConflict(RuntimeError):
    """Two `eligibility_inputs` rows carry one hash but different stored snapshot bytes."""

    def __init__(self, kind: str, snapshot_hash: str) -> None:
        super().__init__(
            f"{kind} snapshots with hash {snapshot_hash} differ in their stored bytes; "
            "one snapshot per hash cannot hold both"
        )
        self.kind = kind
        self.snapshot_hash = snapshot_hash


class EligibilitySnapshotMismatch(RuntimeError):
    """Rebuilt `eligibility_inputs` does not resolve to the rows it replaces."""

    def __init__(self, mismatched: int) -> None:
        super().__init__(f"{mismatched} eligibility inputs do not resolve to their original bytes")
        self.mismatched = mismatched


def _create_triggers(table: str) -> None:
    op.execute(f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
               f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END")
    op.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
               f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END")


def _create_inputs(*, with_json: bool) -> None:
    """`eligibility_inputs_new`: the shape after (no JSON columns) or before (with them)."""
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("posting_version_id", sa.Integer(), nullable=False),
        sa.Column("profile_hash", sa.Text(), nullable=False),
        sa.Column("rules_hash", sa.Text(), nullable=False),
        sa.Column("input_fingerprint", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    ]
    if with_json:
        columns.insert(3, sa.Column("profile_snapshot_json", sa.JSON(), nullable=False))
        columns.insert(5, sa.Column("rules_snapshot_json", sa.JSON(), nullable=False))
    op.create_table(
        "eligibility_inputs_new",
        *columns,
        sa.ForeignKeyConstraint(["posting_version_id"], ["posting_versions.id"],
                                name=op.f("fk_eligibility_inputs_posting_version_id_posting_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eligibility_inputs")),
        sa.UniqueConstraint("input_fingerprint", name=op.f("uq_eligibility_inputs_input_fingerprint")),
    )


def _swap_in_new_inputs() -> None:
    op.execute("DROP TABLE eligibility_inputs")
    op.execute("ALTER TABLE eligibility_inputs_new RENAME TO eligibility_inputs")
    op.create_index(_INDEX, "eligibility_inputs", ["posting_version_id", "profile_hash", "rules_hash"])
    _create_triggers("eligibility_inputs")


def _atomically(body: Callable[[], None]) -> None:
    conn = op.get_bind()
    # No COMMIT: alembic commits this transaction together with the version stamp (module docstring).
    conn.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        body()
    except BaseException:
        conn.exec_driver_sql("ROLLBACK")
        raise


def _distinct_snapshots() -> dict[tuple[str, str], Any]:
    """Every (kind, hash) -> its stored value, from one streamed pass over the table."""
    found: dict[tuple[str, str], Any] = {}
    result = op.get_bind().exec_driver_sql(
        "SELECT profile_hash, profile_snapshot_json, rules_hash, rules_snapshot_json "
        "FROM eligibility_inputs"
    )
    for batch in result.partitions(_BATCH):
        for profile_hash, profile_json, rules_hash, rules_json in batch:
            for key, value in ((("profile", profile_hash), profile_json),
                               (("rules", rules_hash), rules_json)):
                seen = found.setdefault(key, value)
                if type(seen) is not type(value) or seen != value:
                    raise EligibilitySnapshotConflict(*key)
    return found


def _unresolved(*, with_json: str, hashed: str) -> int:
    """Rows of `with_json` that `hashed` does not reproduce.

    A row is reproduced when `hashed` has the same id and columns, and its two hashes resolve through
    `eligibility_snapshots` to the very bytes (and storage class) `with_json` holds. Bytes are
    compared as BLOBs so that an affinity conversion cannot make two different values look equal.
    """
    return int(op.get_bind().exec_driver_sql(
        f"SELECT COUNT(*) FROM {with_json} j "
        f"LEFT JOIN {hashed} h ON h.id = j.id "
        "LEFT JOIN eligibility_snapshots p ON p.kind = 'profile' AND p.hash = h.profile_hash "
        "LEFT JOIN eligibility_snapshots r ON r.kind = 'rules' AND r.hash = h.rules_hash "
        "WHERE h.id IS NULL "
        "OR h.posting_version_id IS NOT j.posting_version_id "
        "OR h.profile_hash IS NOT j.profile_hash OR h.rules_hash IS NOT j.rules_hash "
        "OR h.input_fingerprint IS NOT j.input_fingerprint OR h.created_at IS NOT j.created_at "
        "OR typeof(p.snapshot_json) IS NOT typeof(j.profile_snapshot_json) "
        "OR CAST(p.snapshot_json AS BLOB) IS NOT CAST(j.profile_snapshot_json AS BLOB) "
        "OR typeof(r.snapshot_json) IS NOT typeof(j.rules_snapshot_json) "
        "OR CAST(r.snapshot_json AS BLOB) IS NOT CAST(j.rules_snapshot_json AS BLOB)"
    ).scalar_one())


def upgrade() -> None:
    def rebuild() -> None:
        snapshots = _distinct_snapshots()
        op.create_table(
            "eligibility_snapshots",
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("hash", sa.Text(), nullable=False),
            sa.Column("snapshot_json", sa.JSON(), nullable=False),
            sa.CheckConstraint("kind IN ('profile', 'rules')",
                               name=op.f("ck_eligibility_snapshots_kind_enum")),
            sa.PrimaryKeyConstraint("kind", "hash", name=op.f("pk_eligibility_snapshots")),
        )
        for (kind, snapshot_hash), value in sorted(snapshots.items()):
            op.get_bind().exec_driver_sql(
                "INSERT INTO eligibility_snapshots (kind, hash, snapshot_json) VALUES (?, ?, ?)",
                (kind, snapshot_hash, value),
            )
        _create_triggers("eligibility_snapshots")
        _create_inputs(with_json=False)
        op.execute(
            "INSERT INTO eligibility_inputs_new "
            "(id, posting_version_id, profile_hash, rules_hash, input_fingerprint, created_at) "
            "SELECT id, posting_version_id, profile_hash, rules_hash, input_fingerprint, created_at "
            "FROM eligibility_inputs ORDER BY id"
        )
        bad = _unresolved(with_json="eligibility_inputs", hashed="eligibility_inputs_new")
        if bad:
            raise EligibilitySnapshotMismatch(bad)
        _swap_in_new_inputs()

    _atomically(rebuild)


def downgrade() -> None:
    def rebuild() -> None:
        _create_inputs(with_json=True)
        op.execute(
            "INSERT INTO eligibility_inputs_new "
            "(id, posting_version_id, profile_hash, profile_snapshot_json, rules_hash, "
            " rules_snapshot_json, input_fingerprint, created_at) "
            "SELECT i.id, i.posting_version_id, i.profile_hash, p.snapshot_json, i.rules_hash, "
            "       r.snapshot_json, i.input_fingerprint, i.created_at "
            "FROM eligibility_inputs i "
            "LEFT JOIN eligibility_snapshots p ON p.kind = 'profile' AND p.hash = i.profile_hash "
            "LEFT JOIN eligibility_snapshots r ON r.kind = 'rules' AND r.hash = i.rules_hash "
            "ORDER BY i.id"
        )
        bad = _unresolved(with_json="eligibility_inputs_new", hashed="eligibility_inputs")
        if bad:
            raise EligibilitySnapshotMismatch(bad)
        _swap_in_new_inputs()
        op.execute("DROP TABLE eligibility_snapshots")

    _atomically(rebuild)
