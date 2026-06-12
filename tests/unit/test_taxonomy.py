from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.extract.taxonomy import (
    EXTRACTOR_REVISION,
    TaxonomyError,
    bundled_taxonomy_text,
    load_taxonomy,
    write_extraction,
)
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine


def test_bundled_taxonomy_has_119_patterns(tmp_path: Path) -> None:
    taxonomy = load_taxonomy(tmp_path)  # no override present -> bundled
    assert taxonomy.source == "bundled"
    assert len(taxonomy.patterns) == 119


def test_override_wins_when_present(tmp_path: Path) -> None:
    (tmp_path / "taxonomy.yaml").write_text(
        "patterns:\n"
        "  - {name: 'OnlyOne', category: language, pattern: '\\bonlyone\\b', case_sensitive: false}\n",
        encoding="utf-8",
    )
    taxonomy = load_taxonomy(tmp_path)
    assert taxonomy.source == "override"
    assert [p.name for p in taxonomy.patterns] == ["OnlyOne"]


def test_override_changes_version(tmp_path: Path) -> None:
    bundled_version = load_taxonomy(tmp_path).version
    (tmp_path / "taxonomy.yaml").write_text(
        "patterns:\n"
        "  - {name: 'Zig', category: language, pattern: '\\bzig\\b', case_sensitive: false}\n",
        encoding="utf-8",
    )
    assert load_taxonomy(tmp_path).version != bundled_version


def test_override_identical_to_bundle_yields_bundle_version(tmp_path: Path) -> None:
    bundled_version = load_taxonomy(tmp_path).version
    (tmp_path / "taxonomy.yaml").write_text(bundled_taxonomy_text(), encoding="utf-8")
    assert load_taxonomy(tmp_path).version == bundled_version


def test_reformatted_override_yields_same_version(tmp_path: Path) -> None:
    # version hashes the CANONICAL form: formatting/key order do not matter
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "taxonomy.yaml").write_text(
        "patterns:\n"
        "  - {name: 'Zig', category: language, pattern: '\\bzig\\b', case_sensitive: false}\n",
        encoding="utf-8",
    )
    (tmp_path / "b" / "taxonomy.yaml").write_text(
        "patterns:\n"
        "  - case_sensitive: false\n"
        "    pattern: '\\bzig\\b'\n"
        "    category: language\n"
        "    name: Zig\n",
        encoding="utf-8",
    )
    assert load_taxonomy(tmp_path / "a").version == load_taxonomy(tmp_path / "b").version


def test_extractor_revision_bump_changes_version_without_yaml_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = load_taxonomy(tmp_path).version
    monkeypatch.setattr("boardwatch.extract.taxonomy.EXTRACTOR_REVISION", EXTRACTOR_REVISION + 1)
    assert load_taxonomy(tmp_path).version != before


def test_bad_regex_error_names_file_and_pattern(tmp_path: Path) -> None:
    (tmp_path / "taxonomy.yaml").write_text(
        "patterns:\n"
        "  - {name: 'Broken', category: language, pattern: '([unclosed', case_sensitive: false}\n",
        encoding="utf-8",
    )
    with pytest.raises(TaxonomyError) as excinfo:
        load_taxonomy(tmp_path)
    assert "Broken" in str(excinfo.value)
    assert "taxonomy.yaml" in str(excinfo.value)


def test_duplicate_names_rejected(tmp_path: Path) -> None:
    (tmp_path / "taxonomy.yaml").write_text(
        "patterns:\n"
        "  - {name: 'Dup', category: language, pattern: '\\ba\\b', case_sensitive: false}\n"
        "  - {name: 'Dup', category: language, pattern: '\\bb\\b', case_sensitive: false}\n",
        encoding="utf-8",
    )
    with pytest.raises(TaxonomyError, match="Dup"):
        load_taxonomy(tmp_path)


def test_extract_returns_hit_names(tmp_path: Path) -> None:
    taxonomy = load_taxonomy(tmp_path)
    hits = taxonomy.extract("We use Python, PostgreSQL, and Kubernetes on AWS.")
    assert {"Python", "PostgreSQL", "Kubernetes", "AWS"} <= hits


def test_write_extraction_is_idempotent(tmp_path: Path) -> None:
    engine: Engine = get_engine(tmp_path / "data")
    ensure_schema(engine)
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(tables.companies).values(
                    name="Acme", provider="greenhouse", slug="acme", source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        from datetime import datetime

        posting_id = int(
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id, provider_posting_id="1", title="SWE",
                    normalized_title="swe", first_seen_at=datetime(2026, 1, 1),
                    last_seen_at=datetime(2026, 1, 1), status="open",
                    consecutive_missing=0, content_hash="h1",
                    body_text="Python and Go.",
                )
            ).inserted_primary_key[0]
        )
    taxonomy = load_taxonomy(tmp_path)
    with engine.begin() as conn:
        assert write_extraction(conn, taxonomy, posting_id, "h1", "Python and Go.") is True
        assert write_extraction(conn, taxonomy, posting_id, "h1", "Python and Go.") is False
    with engine.connect() as conn:
        rows = conn.execute(select(tables.extractions)).all()
    assert len(rows) == 1
    assert rows[0].engine_version == taxonomy.version
    assert "Python" in rows[0].json["skills"] and "Go" in rows[0].json["skills"]
