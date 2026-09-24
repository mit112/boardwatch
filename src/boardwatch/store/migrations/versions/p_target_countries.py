"""DESIGN-T183 B1: the countries the tenant targets, on the profile singleton.

One additive column, ISO-3166 alpha-3 codes as a JSON list, NOT NULL with a server default of
`[]`. Empty is UNDECLARED, and one representation of it is the point: `NULL` and `[]` would be
two fingerprint inputs for one behaviour, the reason `target_seniority_band` is NOT NULL too.
Every existing install reads as undeclared, and nothing reads the column yet. ALTER TABLE ADD
COLUMN with no table rebuild; downgrade uses native DROP COLUMN (SQLite >= 3.35), the path
p_seniority_band takes. The closed vocabulary is enforced at the write site (ProfileInput).

It enters the ranker's `profile_row_hash`, so the `policy_version` stamp re-keys once.
"""

from alembic import op

revision = "p_target_countries"
down_revision = "p_form_questions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE profile ADD COLUMN target_countries_json JSON NOT NULL DEFAULT '[]'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE profile DROP COLUMN target_countries_json")
