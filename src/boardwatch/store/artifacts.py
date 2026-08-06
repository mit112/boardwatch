"""Artifact-projection store (resume/cover-letter/export references + lineage; P5/P7).

Stores references (uri) + metadata + lineage, never blobs. artifact_derivations records
immutable derivation edges. Functions take the caller's open Connection.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, Row, insert, select

from boardwatch.core.clock import utcnow
from boardwatch.store.tables import artifact_derivations, artifacts


def record_artifact(
    conn: Connection,
    *,
    kind: str,
    uri: str,
    job_id: int | None = None,
    posting_version_id: int | None = None,
    application_id: int | None = None,
    content_hash: str | None = None,
    generator: str | None = None,
    generator_version: str | None = None,
    media_type: str | None = None,
    byte_size: int | None = None,
    meta: dict[str, Any] | None = None,
    run_id: int | None = None,
) -> int:
    return int(
        conn.execute(
            insert(artifacts).values(
                job_id=job_id, posting_version_id=posting_version_id, application_id=application_id,
                kind=kind, uri=uri, content_hash=content_hash, generator=generator,
                generator_version=generator_version, media_type=media_type, byte_size=byte_size,
                meta_json=meta, created_at=utcnow(), run_id=run_id,
            )
        ).inserted_primary_key[0]  # type: ignore[index]
    )


def get_or_create_master_artifact(
    conn: Connection,
    *,
    content_hash: str,
    uri: str,
    generator_version: str,
    meta: dict[str, Any],
    run_id: int | None = None,
) -> int:
    """Content-address the authored master résumé under (kind='resume_master', content_hash).

    Re-tailoring from the same master reuses the one master artifact instead of accreting
    duplicates, so lineage stays a clean fan-out from a single node (P7).

    `run_id` is therefore recorded only on CREATE. A reused master keeps the run that first
    authored it, which is the honest answer — the node was not produced by this run. Counting
    masters per run would need a separate edge, not an overwrite of this column.
    """
    existing = conn.execute(
        select(artifacts.c.id).where(
            artifacts.c.kind == "resume_master", artifacts.c.content_hash == content_hash
        )
    ).first()
    if existing is not None:
        return int(existing.id)
    return record_artifact(
        conn, kind="resume_master", uri=uri, content_hash=content_hash,
        generator="boardwatch.tailor", generator_version=generator_version, meta=meta,
        run_id=run_id,
    )


def list_artifacts(conn: Connection, *, job_id: int | None = None) -> list[Row[Any]]:
    stmt = select(artifacts).order_by(artifacts.c.id)
    if job_id is not None:
        stmt = stmt.where(artifacts.c.job_id == job_id)
    return list(conn.execute(stmt).all())


def add_derivation(
    conn: Connection, *, artifact_id: int, parent_artifact_id: int, relation: str
) -> None:
    conn.execute(
        insert(artifact_derivations).values(
            artifact_id=artifact_id, parent_artifact_id=parent_artifact_id,
            relation=relation, created_at=utcnow(),
        )
    )


def get_derivations(conn: Connection, artifact_id: int) -> list[Row[Any]]:
    return list(
        conn.execute(
            select(artifact_derivations)
            .where(artifact_derivations.c.artifact_id == artifact_id)
            .order_by(artifact_derivations.c.parent_artifact_id)
        ).all()
    )
