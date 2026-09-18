"""T91: the Greenhouse application form's questions, cached per posting version.

One new table, no change to any existing one. `posting_form_questions` holds the form
`boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}?questions=true` returned for one frozen
posting version, so `delivery/form_questions` asks each board once per version rather than once
per run per lead.

**Keyed on `posting_version_id` rather than `posting_id`, and that is the load-bearing choice.**
A revised requisition is a new evaluation subject everywhere else in this store, and its
application form may have been revised with it — so the version key is what makes "re-ask when the
posting changes, never otherwise" fall out of the schema instead of needing a TTL. A `postings`
column would have had to carry its own staleness rule, and a stale form is the dangerous
direction: it is the input to a hold.

`questions_json` stores the FETCHED payload, never the match, so the catalog can gain a surface
and take effect on the next reconcile without re-asking a single board.

No backfill: nothing has ever been asked, so an empty table is the truth. Every pre-existing lead
reads as "no questions known" until the next sweep, which is the same fail-open state a board that
will not answer produces — never a hold.

The downgrade drops the table. The cached forms are lost and re-fetched; no posting is.
"""

from alembic import op

revision = "p_form_questions"
down_revision = "p_body_precondition_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE posting_form_questions ("
        "posting_version_id INTEGER NOT NULL, "
        "questions_json JSON NOT NULL, "
        "fetched_at DATETIME NOT NULL, "
        "CONSTRAINT pk_posting_form_questions PRIMARY KEY (posting_version_id), "
        "CONSTRAINT fk_posting_form_questions_posting_version_id_posting_versions "
        "FOREIGN KEY(posting_version_id) REFERENCES posting_versions (id)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE posting_form_questions")
