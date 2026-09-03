"""`record_body_revision` — the non-run writer that repairs a body it did not fetch.

WHAT THESE DEFEND, and each fails against a specific plausible wrong repair:

* `test_a_revision_appends_a_version_and_leaves_the_superseded_body_byte_identical` fails against
  a repair that UPDATEs the existing `posting_versions` row instead of appending one. That is the
  tempting shape — one row, one statement, no version-chain growth — and it silently breaks the
  keystone: 1,146 `eligibility_inputs` rows fingerprint a specific version id, and every quoted
  `INELIGIBLE` span is a slice of that version's `body_text` at a recorded offset. Unescaping
  shortens the string, so every offset past the first backslash moves. A mutating repair leaves
  those rows pointing at a document that no longer holds their quote where they say it does.

* `test_a_repair_leaves_a_unicode_escape_exactly_as_job_apps_wrote_it` fails against a repair
  that re-derives the escape set as "backslash followed by anything". D-443: `\\uXXXX` and `\\n`
  in these bodies are undecoded JSON escapes — a DIFFERENT, unfixed upstream defect — and
  dropping their backslash leaves the literal text `u2014` in the frozen JD, which is worse than
  the escape. The shipped `unescape_markdown` restricts itself to an ASCII-punctuation follower,
  and this test is why that restriction may not be respelled by a caller.

* `test_the_postings_row_and_the_new_version_cannot_disagree_on_the_hash` fails against a repair
  that appends the version but leaves `postings.content_hash` behind (or the reverse). That is
  the D-414(a) half-write: eligibility reads the CURRENT version, so a posting whose hash names a
  superseded version is one whose evidence chain cites a document nobody evaluated.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, func, insert, select

from boardwatch.core.normalize import content_hash
from boardwatch.lanes.jobapps import unescape_markdown
from boardwatch.store.body_revision import record_body_revision
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.queries import current_posting_versions
from boardwatch.store.tables import companies, jobs, posting_versions, postings

NOW = datetime(2026, 9, 2, 12, 0, 0)
LATER = datetime(2026, 9, 3, 12, 0, 0)

#: A harvested job-apps body, verbatim in shape: a markdown-escaped years bar and hyphen next to
#: an undecoded JSON escape, which is the pairing that makes a re-derived escape set dangerous.
HARVESTED = (
    "About the role\n"
    "3\\+ years of non\\-internship professional software development experience\n"
    "Balance what matters\\u2014your work, your life\n"
    "Line one\\nline two\n"
    "C\\+\\+ or Python required\n"
)
REPAIRED = (
    "About the role\n"
    "3+ years of non-internship professional software development experience\n"
    "Balance what matters\\u2014your work, your life\n"
    "Line one\\nline two\n"
    "C++ or Python required\n"
)


def _seed(data_dir: Path) -> tuple[Engine, int, int]:
    """A posting with one `new` version carrying the escaped body. Returns (engine, pid, vid)."""
    engine = get_engine(data_dir)
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="Acme", provider="jobapps", slug="acme", source="lane", watched=True
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id="pst_abc",
                    title="Software Engineer", normalized_title="software engineer",
                    url="https://example.com/jobs/1", locations_json=["Durham, NC"],
                    posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW,
                    status="open", consecutive_missing=0,
                    content_hash=content_hash(HARVESTED), body_text=HARVESTED,
                )
            ).inserted_primary_key[0]
        )
        version_id = int(
            conn.execute(
                insert(posting_versions).values(
                    posting_id=posting_id, content_hash=content_hash(HARVESTED),
                    body_text=HARVESTED, captured_at=NOW, capture_reason="new",
                )
            ).inserted_primary_key[0]
        )
    return engine, posting_id, version_id


def _repair(engine: Engine, posting_id: int, body: str) -> int:
    """The repair's transform-and-persist step, exactly as the one-off driver composes it."""
    repaired = unescape_markdown(body)
    with engine.begin() as conn:
        return record_body_revision(
            conn,
            posting_id=posting_id,
            body_text=repaired,
            content_hash=content_hash(repaired),
            captured_at=LATER,
        )


def test_a_revision_appends_a_version_and_leaves_the_superseded_body_byte_identical(
    tmp_path: Path,
) -> None:
    engine, posting_id, old_version_id = _seed(tmp_path)
    new_version_id = _repair(engine, posting_id, HARVESTED)

    assert new_version_id != old_version_id
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count()).select_from(posting_versions).where(
                    posting_versions.c.posting_id == posting_id
                )
            ).scalar()
            == 2
        )
        superseded = conn.execute(
            select(posting_versions.c.body_text, posting_versions.c.content_hash,
                   posting_versions.c.capture_reason)
            .where(posting_versions.c.id == old_version_id)
        ).one()
        # The frozen JD. Byte-identical, INCLUDING its hash, so an existing quoted span still
        # slices out of the document at the offset it recorded.
        assert superseded.body_text == HARVESTED
        assert superseded.content_hash == content_hash(HARVESTED)
        assert superseded.capture_reason == "new"

        appended = conn.execute(
            select(posting_versions.c.body_text, posting_versions.c.capture_reason,
                   posting_versions.c.run_id, posting_versions.c.captured_at)
            .where(posting_versions.c.id == new_version_id)
        ).one()
        assert appended.body_text == REPAIRED
        assert appended.capture_reason == "revised"
        # No run to attribute it to, and none invented. `posting_versions.run_id` is nullable for
        # exactly this writer.
        assert appended.run_id is None

        # Eligibility reads the CURRENT version, so the appended row has to be the one it finds.
        current = current_posting_versions(conn, [posting_id])[posting_id]
        assert current.posting_version_id == new_version_id
        assert current.body_text == REPAIRED


def test_a_repair_leaves_a_unicode_escape_exactly_as_job_apps_wrote_it(tmp_path: Path) -> None:
    engine, posting_id, _ = _seed(tmp_path)
    new_version_id = _repair(engine, posting_id, HARVESTED)

    with engine.connect() as conn:
        body = conn.execute(
            select(posting_versions.c.body_text).where(posting_versions.c.id == new_version_id)
        ).scalar_one()
    # Fixed: the markdown escapes the eligibility catalog cannot read through.
    assert "3+ years of non-internship" in body
    assert "C++ or Python" in body
    # UNTOUCHED: a different, unfixed upstream defect (D-443). Stripping these backslashes would
    # leave `u2014` and `nline two` as literal text in the frozen JD.
    assert "\\u2014your work" in body
    assert "Line one\\nline two" in body
    assert "u2014your work" not in body.replace("\\u2014your work", "")


def test_the_postings_row_and_the_new_version_cannot_disagree_on_the_hash(tmp_path: Path) -> None:
    engine, posting_id, _ = _seed(tmp_path)
    new_version_id = _repair(engine, posting_id, HARVESTED)

    with engine.connect() as conn:
        row = conn.execute(
            select(postings.c.body_text, postings.c.content_hash).where(
                postings.c.id == posting_id
            )
        ).one()
        version = conn.execute(
            select(posting_versions.c.body_text, posting_versions.c.content_hash).where(
                posting_versions.c.id == new_version_id
            )
        ).one()
    assert row.body_text == version.body_text == REPAIRED
    assert row.content_hash == version.content_hash == content_hash(REPAIRED)


def test_a_second_pass_finds_nothing_left_to_repair(tmp_path: Path) -> None:
    """Idempotent by the transform, not by a guard: the repaired body is a fixed point."""
    engine, posting_id, _ = _seed(tmp_path)
    _repair(engine, posting_id, HARVESTED)
    with engine.connect() as conn:
        current = current_posting_versions(conn, [posting_id])[posting_id]
    assert unescape_markdown(current.body_text) == current.body_text
