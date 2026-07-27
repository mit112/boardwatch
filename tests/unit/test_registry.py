from pathlib import Path

import pytest

from boardwatch.registry.loader import load_catalog, starter_entries
from boardwatch.registry.validate import CatalogError, CompanyEntry

VALID = """\
companies:
  - name: Acme
    provider: greenhouse
    slug: acme
    tags: [starter]
  - name: Globex
    provider: lever
    slug: globex
    tags: []
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "companies.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_catalog_parses_entries(tmp_path: Path) -> None:
    entries = load_catalog(_write(tmp_path, VALID))
    assert {e.slug for e in entries} == {"acme", "globex"}
    assert entries[0].provider == "greenhouse"


def test_starter_subset_extraction(tmp_path: Path) -> None:
    starters = starter_entries(load_catalog(_write(tmp_path, VALID)))
    assert [e.slug for e in starters] == ["acme"]


def test_unknown_provider_is_rejected_naming_the_entry(tmp_path: Path) -> None:
    bad = VALID.replace("provider: lever", "provider: workday")
    with pytest.raises(CatalogError) as exc:
        load_catalog(_write(tmp_path, bad))
    assert "globex" in str(exc.value)


def test_unknown_provider_message_is_registry_sourced() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc:
        CompanyEntry(name="X", provider="workday", slug="x")
    msg = str(exc.value)
    assert "unknown provider" in msg          # our field_validator, not the old Literal error
    assert "workday" in msg
    for name in ("ashby", "greenhouse", "lever"):
        assert name in msg


def test_duplicate_provider_slug_is_rejected(tmp_path: Path) -> None:
    # duplicate detection lives inside load_catalog (it calls validate_entries),
    # so the public entry point catches it directly — no raw/__wrapped__ shim needed
    dup = VALID + "  - {name: Acme2, provider: greenhouse, slug: acme, tags: []}\n"
    with pytest.raises(CatalogError) as exc:
        load_catalog(_write(tmp_path, dup))
    assert "greenhouse:acme" in str(exc.value)


def test_bundled_catalog_loads_clean() -> None:
    # the shipped attended catalog must always load + validate
    entries = load_catalog()
    assert len(entries) >= 30


def test_validate_never_imports_store_transitively() -> None:
    # a SOURCE-STRING check misses transitive imports; assert the real import graph in a
    # clean subprocess: importing validate must not pull in any boardwatch.store.* module
    import subprocess
    import sys

    code = (
        "import boardwatch.registry.validate; import sys; "
        "bad=[m for m in sys.modules if m.startswith('boardwatch.store')]; "
        "assert not bad, bad"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
