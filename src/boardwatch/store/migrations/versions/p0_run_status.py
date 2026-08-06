"""P0 item 4: exit status on the run ledger.

Additive. `op.add_column` with a server_default, never `batch_alter_table` — a rebuild
would drop and recreate `runs`, and six tables carry an FK to `runs.id`.

The default is `running`, and that is the load-bearing choice. A run row is created by the
scan stage and closed by whoever owns the pipeline, so the only writer that can set a
terminal status is the one in the `finally`. A SIGKILL never reaches it. Defaulting to
`running` means such a row keeps saying `running` forever with `finished_at` NULL, which is
exactly what happened; defaulting to `ok` would launder a killed run into a clean one, and
defaulting to `failed` would mark every in-flight run as broken while it is still working.
"""
from alembic import op

revision = "p0_run_status"
down_revision = "run_attribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows are historical and already closed; they get `running` from the default
    # and are indistinguishable from a killed run. That is honest — nothing recorded their
    # outcome at the time, and inventing `ok` for them would be a fabricated measurement.
    op.execute("ALTER TABLE runs ADD COLUMN status TEXT NOT NULL DEFAULT 'running'")


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP COLUMN status")
