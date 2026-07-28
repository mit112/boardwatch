"""P2: typed eligibility facts and per-family severity policy on the profile singleton.

Two additive nullable JSON columns, ALTER TABLE ADD COLUMN with no table rebuild.
NULL reads as "no facts, no policy overrides": every resolver then abstains and the
CLI surfaces that state rather than hiding it (spec §4.6). Downgrade uses native
DROP COLUMN, the same path p0_jobs_anchor takes (SQLite >= 3.35).
"""
from alembic import op

revision = "p2_profile_eligibility"
down_revision = "p0_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE profile ADD COLUMN eligibility_facts_json JSON")
    op.execute("ALTER TABLE profile ADD COLUMN eligibility_policy_json JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE profile DROP COLUMN eligibility_policy_json")
    op.execute("ALTER TABLE profile DROP COLUMN eligibility_facts_json")
