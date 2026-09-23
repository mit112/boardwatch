"""D21 preflight: ONE entry point that (1) re-derives profile skills when
profile.taxonomy_version is stale and (2) ensures every OPEN posting has an
extraction row at the current taxonomy_version, computing missing ones in a
visible batch before the calling command proceeds.

Editing taxonomy.yaml costs nothing until the next ranking command, which pays
a stated one-time cost. Closed postings keep old-version rows (displayed,
never ranked); superseded rows remain but are unreachable through the version
key. Batches commit independently (per-row idempotent under the UNIQUE key),
so a crash between batches leaves a consistent, resumable state.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from sqlalchemy import Engine, select, update

from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import Taxonomy, load_taxonomy, write_extraction
from boardwatch.store.db import write_connection
from boardwatch.store.tables import extractions, postings, profile

BATCH_SIZE = 200


@dataclass
class PreflightStats:
    profile_refreshed: bool = False
    postings_backfilled: int = 0


def refresh_profile_taxonomy(engine: Engine, taxonomy: Taxonomy) -> bool:
    """The profile-refresh half of the preflight, alone: re-derive `profile.skills_json` and
    stamp `profile.taxonomy_version` when the profile row is stale against `taxonomy`. Returns
    whether it fired.

    Split out (T164) so a caller that must read the profile AFTER this refresh but BEFORE the
    rest of the preflight runs — the pipeline's run-start identity capture, which otherwise reads
    a stale row while the funnel's end reading reads the ranker's own refreshed one, reporting a
    false `profile_row_hash` drift on the first run after every taxonomy bump — can perform this
    half early, exactly once. The caller passes the result back into `run_preflight` as
    `profile_already_refreshed` so the UPDATE below never runs twice.
    """
    # T134: read-then-write, so IMMEDIATE at BEGIN. A DEFERRED transaction takes its WAL
    # snapshot at the SELECT and SQLite cannot upgrade an obsolete one, so any writer
    # committing before the UPDATE fails it with `SQLITE_BUSY_SNAPSHOT`, which
    # `busy_timeout` does not retry.
    with write_connection(engine) as conn, conn.begin():
        row = conn.execute(select(profile).where(profile.c.id == 1)).one_or_none()
        if row is not None and row.taxonomy_version != taxonomy.version:
            skills = sorted(taxonomy.extract(row.text))
            conn.execute(
                update(profile)
                .where(profile.c.id == 1)
                .values(skills_json=skills, taxonomy_version=taxonomy.version)
            )
            return True
    return False


def run_preflight(
    engine: Engine,
    settings: Settings,
    console: Console | None = None,
    *,
    profile_already_refreshed: bool = False,
) -> PreflightStats:
    """`profile_already_refreshed` means a caller already ran `refresh_profile_taxonomy` this
    run and it fired (T164). It only keeps the `taxonomy changed — re-extracting` line below
    truthful. The refresh is still re-checked here, never skipped on the caller's word: it is a
    no-op on a fresh profile, and a taxonomy edited between the two calls must still refresh the
    profile before these extractions are written against the new version."""
    console = console or Console()
    taxonomy = load_taxonomy(settings.config_dir)
    stats = PreflightStats()
    stats.profile_refreshed = (
        refresh_profile_taxonomy(engine, taxonomy) or profile_already_refreshed
    )

    pending = _open_postings_missing_extraction(engine, taxonomy.version)
    if pending:
        # The CAUSE is read, never assumed. A posting lacks an extraction at the current
        # version for two unrelated reasons and only one of them is a taxonomy change: the
        # taxonomy moved -- which the branch above has already detected, because a moved
        # taxonomy necessarily leaves the profile's recorded version stale -- or the posting
        # is simply NEW and has never been extracted. The second is the ordinary case on
        # every run that scans a board, so a line hardcoded to "taxonomy changed" asserts a
        # cause it never checked: it read that way on 17 consecutive runs across which
        # `profile.taxonomy_version` never moved once, which makes it indistinguishable
        # from the one reading that would matter -- a frozen window losing its identity.
        # BOUND: with no profile row at all `profile_refreshed` cannot be True, so a genuine
        # taxonomy change on such a store reports as new postings. That store ranks nothing,
        # and the alternative -- a second query over the pending rows' stored versions --
        # buys a distinction only an unranked store could observe.
        if stats.profile_refreshed:
            console.print(f"taxonomy changed — re-extracting {len(pending)} postings\u2026")
        else:
            console.print(f"extracting {len(pending)} new posting(s)\u2026")
        for chunk_start in range(0, len(pending), BATCH_SIZE):
            chunk = pending[chunk_start : chunk_start + BATCH_SIZE]
            with engine.begin() as conn:  # one commit per batch: resumable (D21)
                for posting_id, body_hash, body_text in chunk:
                    if write_extraction(conn, taxonomy, posting_id, body_hash, body_text):
                        stats.postings_backfilled += 1
    return stats


def _open_postings_missing_extraction(
    engine: Engine, version: str
) -> list[tuple[int, str, str]]:
    current = (
        select(extractions.c.id)
        .where(
            extractions.c.posting_id == postings.c.id,
            extractions.c.content_hash == postings.c.content_hash,
            extractions.c.kind == "taxonomy",
            extractions.c.engine_version == version,
        )
        .exists()
    )
    with engine.connect() as conn:
        rows = conn.execute(
            select(postings.c.id, postings.c.content_hash, postings.c.body_text)
            .where(postings.c.status == "open", ~current)
            .order_by(postings.c.id)
        ).all()
    return [(int(r.id), str(r.content_hash), str(r.body_text)) for r in rows]
