"""The policy stamp a permanent ledger decision carries (P6 slice 2, design §2.4).

Its own module because two unrelated callers need it — the pipeline, which stamps a decision as
it records it, and `ledger show/reopen`, which compares a stored stamp against the current one to
find drift. A private helper on either one would have made the other import it.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection

from boardwatch.core.settings import Settings
from boardwatch.eligibility.engine import engine_version
from boardwatch.eligibility.preflight import current_identity
from boardwatch.reports.manifest import config_hash, policy_version, profile_row_hash
from boardwatch.store.queries import get_profile


def run_policy_version(conn: Connection, settings: Settings) -> str:
    """The stamp decisions taken under the current configuration should carry.

    Reuses the run manifest's identity wholesale — the same five components the funnel artifact
    already reports — so "what would make us re-decide this" and "what makes two runs comparable"
    cannot drift apart. Nothing new is hashed here.
    """
    identity = current_identity(conn, settings)
    profile_row = get_profile(conn)
    return policy_version(
        code_fingerprint=engine_version(),
        config_hash=config_hash(settings),
        profile_row_hash=(
            profile_row_hash(
                skills=profile_row.skills_json,
                target_titles=profile_row.target_titles_json,
                exclude_titles=profile_row.exclude_titles_json,
                locations=profile_row.locations_json,
                remote_only=profile_row.remote_only,
                target_seniority_band=profile_row.target_seniority_band,
            )
            if profile_row is not None
            else None
        ),
        profile_facts_hash=identity[0] if identity is not None else None,
        rules_hash=identity[1] if identity is not None else None,
    )
