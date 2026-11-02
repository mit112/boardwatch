"""T291: the corpus-wide reads are answered from indexes instead of a disk page per posting.

A posting's row averages 16.5 KB (`raw_json` and `body_text`), so a table page holds about one,
and any statement over the open postings reads one page per posting whatever columns it wants:
~100 s at 830k open, ~200 s when it also reads the body. Three additive changes, no table rebuild:

- `ix_postings_corpus` covers the per-company counts and the scan's open-id load, and carries the
  empty-body expression so `body_is_empty` reads no body.
- `ix_postings_id_status` answers a join's "is this posting open?" without the row.
- `ix_posting_identities_key` gains the two columns the duplicate sweep joins on. Its old columns
  are its prefix, so every reader of the old index is still served.

Upgrading reads every posting body once to build the expression (about 6 min on the measured store).
"""

from alembic import op

revision = "p_corpus_indexes"
down_revision = "p_board_scans_lane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent, because each statement commits on its own under alembic's engine and the first takes
    # minutes: a run killed mid-way leaves some of these built at the old revision, and the retry must
    # finish the job rather than fail with "already exists" on every later command.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_postings_corpus ON postings "
        "(status, company_id, provider_posting_id, "
        "(trim(body_text, char(32, 9, 10, 13, 12, 11)) = ''))"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_postings_id_status ON postings (id, status)")
    op.execute("DROP INDEX IF EXISTS ix_posting_identities_key")
    op.execute(
        "CREATE INDEX ix_posting_identities_key ON posting_identities "
        "(kind, identity_key, algorithm_version, posting_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posting_identities_key")
    op.execute("CREATE INDEX ix_posting_identities_key ON posting_identities (kind, identity_key)")
    op.execute("DROP INDEX IF EXISTS ix_postings_id_status")
    op.execute("DROP INDEX IF EXISTS ix_postings_corpus")
