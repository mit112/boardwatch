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
from boardwatch.extract.taxonomy import load_taxonomy, write_extraction
from boardwatch.store.tables import extractions, postings, profile

BATCH_SIZE = 200


@dataclass
class PreflightStats:
    profile_refreshed: bool = False
    postings_backfilled: int = 0


def run_preflight(
    engine: Engine, settings: Settings, console: Console | None = None
) -> PreflightStats:
    console = console or Console()
    taxonomy = load_taxonomy(settings.config_dir)
    stats = PreflightStats()

    with engine.begin() as conn:
        row = conn.execute(select(profile).where(profile.c.id == 1)).one_or_none()
        if row is not None and row.taxonomy_version != taxonomy.version:
            skills = sorted(taxonomy.extract(row.text))
            conn.execute(
                update(profile)
                .where(profile.c.id == 1)
                .values(skills_json=skills, taxonomy_version=taxonomy.version)
            )
            stats.profile_refreshed = True

    pending = _open_postings_missing_extraction(engine, taxonomy.version)
    if pending:
        console.print(f"taxonomy changed — re-extracting {len(pending)} postings\u2026")
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
