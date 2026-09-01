"""`boardwatch postings reparse-bodies` — the drain for a corrected provider body parser.

WHAT THESE DEFEND. The scan path cannot repair an existing row: `known_posting_ids` keeps every
stored posting out of detail fetching, so a corrected parser reaches only NEW postings. Each test
here fails against a plausible wrong drain — one that skips closed rows, one that writes without
`--apply`, one that attributes the version to a run, one that leaves identities stale, and one
that empties a body it has no payload for.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.core.normalize import content_hash
from boardwatch.core.posting_identity import IdentityInputs, compute_identities
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import (
    companies,
    jobs,
    posting_identities,
    posting_versions,
    postings,
)

NOW = datetime(2026, 9, 1, 12, 0, 0)

#: One real SmartRecruiters shape: `jobAd.sections[*].text` is HTML, and `companyDescription`
#: is excluded from the body by the provider on purpose.
HTML_SECTIONS = {
    "jobDescription": {"text": "<p>Build <strong>APIs</strong> for the platform.</p>"},
    "qualifications": {"text": "<ul><li>Python</li><li>SQL</li></ul>"},
    "companyDescription": {"text": "<p>Boilerplate about us.</p>"},
}


def _invoke(data_dir: Path, *args: str):
    return CliRunner().invoke(app, ["--data-dir", str(data_dir), *args])


def _seed(data_dir: Path, *, status: str = "open", with_detail: bool = True) -> tuple:
    engine = get_engine(data_dir)
    ensure_schema(engine)
    raw = {"listed": {"id": "sr-1"}, "detail": {"jobAd": {"sections": HTML_SECTIONS}}}
    body = "<p>Build <strong>APIs</strong> for the platform.</p>\n\n<ul><li>Python</li><li>SQL</li></ul>"
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name="Acme", provider="smartrecruiters", slug="acme",
                    source="user", watched=True,
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id="sr-1",
                    title="Software Engineer", normalized_title="software engineer",
                    url="https://jobs.smartrecruiters.com/Acme/1",
                    locations_json=["Remote"], remote_policy="remote",
                    posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW,
                    status=status, consecutive_missing=0,
                    content_hash=content_hash(body), body_text=body,
                    raw_json=json.dumps(raw) if with_detail else json.dumps({"listed": {}}),
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=content_hash(body), body_text=body,
                captured_at=NOW, capture_reason="new",
            )
        )
    return engine, posting_id, body, company_id


def test_apply_converts_body_hash_version_and_identities_together(tmp_path: Path) -> None:
    engine, posting_id, old_body, company_id = _seed(tmp_path)
    result = _invoke(tmp_path, "postings", "reparse-bodies", "--provider", "smartrecruiters",
                     "--apply")
    assert result.exit_code == 0, result.output

    with engine.begin() as conn:
        body, stored_hash = conn.execute(
            select(postings.c.body_text, postings.c.content_hash)
            .where(postings.c.id == posting_id)
        ).one()
        # The body is text now, and the words survived in order.
        assert "<p>" not in body and "<ul>" not in body and "<li>" not in body
        assert "Build APIs for the platform." in body
        assert body.index("Python") < body.index("SQL")
        # companyDescription stays excluded.
        assert "Boilerplate" not in body
        # The stored hash matches the stored body — the two moved together.
        assert stored_hash == content_hash(body)
        assert stored_hash != content_hash(old_body)

        # A `revised` version was appended with a NULL run_id, and the `new` one is untouched.
        versions = conn.execute(
            select(posting_versions.c.capture_reason, posting_versions.c.run_id,
                   posting_versions.c.content_hash, posting_versions.c.body_text)
            .where(posting_versions.c.posting_id == posting_id)
            .order_by(posting_versions.c.id)
        ).all()
        assert [v[0] for v in versions] == ["new", "revised"]
        assert versions[1][1] is None, "a drain has no run; run_id must stay NULL"
        assert versions[1][2] == stored_hash
        assert versions[1][3] == body
        assert versions[0][3] == old_body, "history must keep what was actually delivered"

        # Identities exist and carry the NEW hash, not the old one.
        rows = dict(
            conn.execute(
                select(posting_identities.c.kind, posting_identities.c.identity_key)
                .where(posting_identities.c.posting_id == posting_id)
            ).all()
        )
        assert "exact_quad" in rows, (
            "identities must be rewritten: content_hash is one of exact_quad's parts"
        )
        # `_key` hashes its parts, so the content_hash never appears literally in the key.
        # Compare against the key computed from each body instead: the stored one must be the
        # NEW body's, and must not still be the OLD body's.
        base = dict(
            posting_id=posting_id, company_id=company_id, company_name="Acme",
            provider_posting_id="sr-1", title="Software Engineer", locations=["Remote"],
            url="https://jobs.smartrecruiters.com/Acme/1", first_seen_at=NOW,
        )
        want = {
            i.kind: i.identity_key
            for i in compute_identities(
                IdentityInputs(content_hash=stored_hash, body_text=body, **base)
            )
        }
        stale = {
            i.kind: i.identity_key
            for i in compute_identities(
                IdentityInputs(
                    content_hash=content_hash(old_body), body_text=old_body, **base
                )
            )
        }
        assert rows["exact_quad"] == want["exact_quad"]
        assert rows["exact_quad"] != stale["exact_quad"], (
            "a drain that rewrote identities from the pre-conversion body would land here"
        )


def test_without_apply_nothing_is_written(tmp_path: Path) -> None:
    engine, posting_id, old_body, company_id = _seed(tmp_path)
    result = _invoke(tmp_path, "postings", "reparse-bodies", "--provider", "smartrecruiters")
    assert result.exit_code == 0, result.output
    assert "would rewrite 1" in result.output

    with engine.begin() as conn:
        body = conn.execute(
            select(postings.c.body_text).where(postings.c.id == posting_id)
        ).scalar_one()
        assert body == old_body, "reporting mode must not write"
        assert conn.execute(
            select(func.count()).select_from(posting_versions)
            .where(posting_versions.c.posting_id == posting_id)
        ).scalar_one() == 1


def test_second_apply_is_a_no_op(tmp_path: Path) -> None:
    engine, posting_id, _, company_id = _seed(tmp_path)
    first = _invoke(tmp_path, "postings", "reparse-bodies", "--provider", "smartrecruiters",
                    "--apply")
    assert "rewrote 1" in first.output, first.output
    second = _invoke(tmp_path, "postings", "reparse-bodies", "--provider", "smartrecruiters",
                     "--apply")
    assert "rewrote 0" in second.output, second.output
    with engine.begin() as conn:
        assert conn.execute(
            select(func.count()).select_from(posting_versions)
            .where(posting_versions.c.posting_id == posting_id)
        ).scalar_one() == 2, "an idempotent drain appends no second revision"


def test_closed_postings_are_repaired_too(tmp_path: Path) -> None:
    engine, posting_id, old_body, company_id = _seed(tmp_path, status="closed")
    result = _invoke(tmp_path, "postings", "reparse-bodies", "--provider", "smartrecruiters",
                     "--apply")
    assert result.exit_code == 0, result.output
    with engine.begin() as conn:
        body = conn.execute(
            select(postings.c.body_text).where(postings.c.id == posting_id)
        ).scalar_one()
    assert "<p>" not in body, "a closed posting reopens without ever being re-fetched"
    assert body != old_body


def test_a_posting_without_a_stored_payload_is_left_alone(tmp_path: Path) -> None:
    engine, posting_id, old_body, company_id = _seed(tmp_path, with_detail=False)
    result = _invoke(tmp_path, "postings", "reparse-bodies", "--provider", "smartrecruiters",
                     "--apply")
    assert result.exit_code == 0, result.output
    assert "1 without a usable stored payload" in result.output
    with engine.begin() as conn:
        body = conn.execute(
            select(postings.c.body_text).where(postings.c.id == posting_id)
        ).scalar_one()
    assert body == old_body, "an empty body would collide on content_hash('')"


def test_unknown_provider_is_an_error_not_a_new_bucket(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = _invoke(tmp_path, "postings", "reparse-bodies", "--provider", "greenhouse")
    assert result.exit_code != 0
    assert "no reparser" in result.output
