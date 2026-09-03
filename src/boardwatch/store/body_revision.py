"""One corrected body persisted as a revision, by a writer that has no run to attribute it to.

WHY IT IS A FUNCTION. `postings.body_text`/`content_hash` and the immutable `posting_versions`
row have to move together or eligibility reads a body whose hash names a version that is no
longer current — the D-414(a) half-write, stated at `scan/apply.py`'s revision branch. Until now
`cli/postings_cmd.py` was the only non-run writer and spelled the pair out inline; it has a
second caller, so the pair lives in one place rather than two.

NOT THE SCAN PATH, and the differences are schema facts rather than taste. `scan/apply.py`
additionally appends a `revised` `posting_events` row and a `posting_version_sources` row.
Neither is available to a non-run writer and neither is invented here:

- `posting_events.run_id` is NOT NULL (`tables.py`), so there is no event a runless writer could
  append. `posting_versions.run_id` is nullable precisely so that this writer can still append a
  version.
- `posting_version_sources` is documented as one row per SCAN-CAPTURED version, whose provenance
  is not invented (`store/sources.py`). A re-derivation reads text the store already holds; no
  source served it at this moment, so claiming one would date the lane's observation wrongly.

THE VERSION IS APPENDED, NEVER REWRITTEN. The superseded row stays the frozen JD that every
existing `eligibility_inputs` row was fingerprinted against and that every quoted `INELIGIBLE`
span was sliced out of. Rewriting it in place would leave those rows pointing at a document that
no longer contains their quote at the offset they recorded — an evidence chain that reads as
intact while quoting text no JD ever held. The schema agrees and does not take it on trust: the
`posting_versions_no_update` and `posting_versions_no_delete` triggers (`migrations/versions/
p0_posting_versions.py`) abort either statement, so an in-place repair fails loudly rather than
quietly. Undoing a revision therefore means appending the old body again, not deleting a row.

`posting_identities` is NOT touched here. `content_hash` is one of `exact_quad`'s four
components, so it does have to be recomputed, but `load_identity_inputs` is a batched read and
its callers rewrite identities once for the whole changed set.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, insert, update

from boardwatch.store.tables import posting_versions, postings


def record_body_revision(
    conn: Connection,
    *,
    posting_id: int,
    body_text: str,
    content_hash: str,
    captured_at: datetime,
) -> int:
    """`postings` updated and a `revised` version appended with a NULL `run_id`.

    Returns the new `posting_versions.id`. Takes the caller's open connection and neither begins
    nor commits: the two statements are one atomic change or they are a half-write.
    """
    conn.execute(
        update(postings)
        .where(postings.c.id == posting_id)
        .values(content_hash=content_hash, body_text=body_text)
    )
    return int(
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id,
                content_hash=content_hash,
                body_text=body_text,
                captured_at=captured_at,
                run_id=None,
                capture_reason="revised",
            )
        ).inserted_primary_key[0]  # type: ignore[index]
    )
