"""`lane_seeds` — a posting URL one lane found and another lane resolves.

Tier-D vendors are per-tenant with no cross-tenant search, so a discovering lane and a
resolving lane are different lanes that generally do not run in the same stage pass (D-413).
The handoff therefore has to be durable, which is what this table is.

CREATE TABLE, not an ALTER: it references `runs` twice and nothing references it, so there is
no rebuild question here and no child to orphan (alembic runs with `foreign_keys` OFF, which
is why a `batch_alter_table` on `runs` is forbidden — that caveat does not apply to a new
table).

It does NOT enter the run manifest hash. A seed is an observation about where a posting might
be found — acquisition, the same class as `lanes_enabled` and the lane page knobs, which
`reports/manifest.py` classifies `_CONFIG_IRRELEVANT` for the recorded reason that
`policy_version` derives from `config_hash` and would stale every permanent disposition.
"""

from alembic import op

revision = "p_lane_seeds"
down_revision = "p_runs_corpus_counts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lane_seeds (
            id INTEGER NOT NULL,
            url TEXT NOT NULL,
            discovered_by TEXT NOT NULL,
            first_seen_run_id INTEGER NOT NULL,
            first_seen_at DATETIME NOT NULL,
            attempts INTEGER DEFAULT 0 NOT NULL,
            last_attempt_run_id INTEGER,
            last_attempt_at DATETIME,
            resolved_at DATETIME,
            CONSTRAINT pk_lane_seeds PRIMARY KEY (id),
            CONSTRAINT uq_lane_seeds_url UNIQUE (url),
            CONSTRAINT fk_lane_seeds_first_seen_run_id_runs
                FOREIGN KEY(first_seen_run_id) REFERENCES runs (id),
            CONSTRAINT fk_lane_seeds_last_attempt_run_id_runs
                FOREIGN KEY(last_attempt_run_id) REFERENCES runs (id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_lane_seeds_resolved_at_attempts"
        " ON lane_seeds (resolved_at, attempts)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_lane_seeds_resolved_at_attempts")
    op.execute("DROP TABLE lane_seeds")
