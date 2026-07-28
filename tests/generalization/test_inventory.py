"""R7: no data file enters the tree without a reviewed inventory entry."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.generalization import allowlists as al
from tools.generalization.allowlists import DataEntry
from tools.generalization.discovery import Repo, RepoFile, discover
from tools.generalization.inventory import check_inventory, inventory_scope

REPO_ROOT = Path(__file__).resolve().parents[2]


def _entry(path: str, tmp_path: Path, body: str = "a: 1\n") -> RepoFile:
    target = tmp_path / "blob"
    target.write_text(body, encoding="utf-8")
    return RepoFile(path=path, abspath=target, is_text=True, text=body)


def test_scope_covers_data_files_repo_wide() -> None:
    scope = inventory_scope(discover(REPO_ROOT))
    assert "src/boardwatch/registry/companies.yaml" in scope
    assert "tests/fixtures/lever/normal.json" in scope
    assert len(scope) == 16


def test_scope_excludes_tooling_config_and_workflows() -> None:
    scope = inventory_scope(discover(REPO_ROOT))
    for path in ("pyproject.toml", "uv.lock", "alembic.ini", ".pre-commit-config.yaml"):
        assert path not in scope
    assert not any(p.startswith(".github/") for p in scope)


def test_real_tree_inventory_is_complete_and_current() -> None:
    assert check_inventory(discover(REPO_ROOT)) == []


def test_unknown_data_file_is_rejected(tmp_path: Path) -> None:
    repo = Repo(root=tmp_path, files=(_entry("docs/harvested.yaml", tmp_path),))
    found = [v for v in check_inventory(repo) if "not in SHIPPED_DATA" in v.detail]
    assert [v.rule for v in found] == ["R7"]
    assert found[0].path == "docs/harvested.yaml"


def test_stale_inventory_entry_is_rejected(tmp_path: Path) -> None:
    repo = Repo(root=tmp_path, files=())
    found = check_inventory(repo)
    assert found
    assert all(v.rule == "R7" for v in found)
    assert all("stale" in v.detail for v in found)


def test_changed_pinned_content_is_rejected() -> None:
    repo = discover(REPO_ROOT)
    pinned = "tests/fixtures/lever/normal.json"
    original = al.SHIPPED_DATA[pinned]
    al.SHIPPED_DATA[pinned] = DataEntry(
        kind=original.kind,
        reason=original.reason,
        provenance=original.provenance,
        source=original.source,
        license_=original.license_,
        pin="sha256:" + "0" * 64,
    )
    try:
        found = [v for v in check_inventory(repo) if v.path == pinned]
        assert [v.rule for v in found] == ["R7"]
        assert "content changed" in found[0].detail
    finally:
        al.SHIPPED_DATA[pinned] = original


def test_living_product_data_must_not_be_pinned() -> None:
    """taxonomy.yaml and companies.yaml churn; pinning them would put a hash bump
    in the path of every community registry PR, which is how checks get deleted."""
    for path in (
        "src/boardwatch/extract/taxonomy.yaml",
        "src/boardwatch/registry/companies.yaml",
    ):
        assert al.SHIPPED_DATA[path].pin == "none"


def test_every_fixture_pin_matches_the_file_on_disk() -> None:
    repo = discover(REPO_ROOT)
    for path, entry in al.SHIPPED_DATA.items():
        if not entry.pin.startswith("sha256:"):
            continue
        found = repo.by_path(path)
        assert found is not None, path
        digest = hashlib.sha256(found.abspath.read_bytes()).hexdigest()
        assert digest == entry.pin.removeprefix("sha256:"), path


def test_stale_entries_are_reported_even_when_an_unknown_file_exists(tmp_path: Path) -> None:
    """Bidirectional comparison is not conditional: a rename is a delete plus an add, and
    the orphaned entry must not be masked by the new file."""
    repo = Repo(root=tmp_path, files=(_entry("docs/harvested.yaml", tmp_path),))
    details = [v.detail for v in check_inventory(repo)]
    assert any("not in SHIPPED_DATA" in d for d in details)
    assert any("stale SHIPPED_DATA entry" in d for d in details)


def test_line_endings_are_pinned_so_content_pins_are_platform_stable() -> None:
    """R7 hashes raw bytes, so a CRLF checkout would break every pin at once."""
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    lines = [line.strip() for line in attributes.splitlines()]
    assert "* text=auto eol=lf" in lines


def test_living_product_data_carrying_a_pin_is_rejected() -> None:
    path = "src/boardwatch/registry/companies.yaml"
    original = al.SHIPPED_DATA[path]
    al.SHIPPED_DATA[path] = DataEntry(
        kind=original.kind, reason=original.reason, pin="sha256:" + "0" * 64
    )
    try:
        found = [v for v in check_inventory(discover(REPO_ROOT)) if "pin='none'" in v.detail]
        assert [v.rule for v in found] == ["R7"]
    finally:
        al.SHIPPED_DATA[path] = original


def test_pinned_kind_without_a_sha256_pin_is_rejected() -> None:
    path = "tests/fixtures/lever/normal.json"
    original = al.SHIPPED_DATA[path]
    al.SHIPPED_DATA[path] = DataEntry(kind=original.kind, reason=original.reason, pin="none")
    try:
        found = [
            v for v in check_inventory(discover(REPO_ROOT)) if "requires a sha256 pin" in v.detail
        ]
        assert [v.rule for v in found] == ["R7"]
    finally:
        al.SHIPPED_DATA[path] = original


def test_a_mislabelled_kind_cannot_dodge_the_pin_requirement() -> None:
    """The pin exemption is bound to the path, so relabelling a fixture 'taxonomy' does
    not buy the churn exemption that taxonomy.yaml has."""
    path = "tests/fixtures/lever/normal.json"
    original = al.SHIPPED_DATA[path]
    al.SHIPPED_DATA[path] = DataEntry(kind="taxonomy", reason="pretending to be living data")
    try:
        found = [
            v for v in check_inventory(discover(REPO_ROOT)) if "requires a sha256 pin" in v.detail
        ]
        assert [v.rule for v in found] == ["R7"]
    finally:
        al.SHIPPED_DATA[path] = original


def test_an_unrecognised_kind_is_rejected() -> None:
    path = "tests/fixtures/lever/normal.json"
    original = al.SHIPPED_DATA[path]
    al.SHIPPED_DATA[path] = DataEntry(
        kind="fixtures", reason=original.reason, pin=original.pin
    )
    try:
        found = [v for v in check_inventory(discover(REPO_ROOT)) if "is not one of" in v.detail]
        assert [v.rule for v in found] == ["R7"]
    finally:
        al.SHIPPED_DATA[path] = original


def test_an_empty_reason_is_rejected() -> None:
    path = "tests/fixtures/lever/normal.json"
    original = al.SHIPPED_DATA[path]
    al.SHIPPED_DATA[path] = DataEntry(kind=original.kind, reason="   ", pin=original.pin)
    try:
        found = [v for v in check_inventory(discover(REPO_ROOT)) if "'reason' is empty" in v.detail]
        assert [v.rule for v in found] == ["R7"]
    finally:
        al.SHIPPED_DATA[path] = original


def test_licensed_provenance_requires_a_license(tmp_path: Path) -> None:
    path = "docs/borrowed.yaml"
    body = "a: 1\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    al.SHIPPED_DATA[path] = DataEntry(
        kind="corpus",
        reason="borrowed sample",
        provenance="public",
        source="https://example.com/corpus",
        license_=None,
        pin=f"sha256:{digest}",
    )
    try:
        repo = Repo(root=tmp_path, files=(_entry(path, tmp_path, body),))
        found = [v for v in check_inventory(repo) if "requires a 'license'" in v.detail]
        assert [v.rule for v in found] == ["R7"]
    finally:
        del al.SHIPPED_DATA[path]


def test_non_first_party_provenance_requires_a_source(tmp_path: Path) -> None:
    path = "docs/borrowed.yaml"
    body = "a: 1\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    al.SHIPPED_DATA[path] = DataEntry(
        kind="corpus",
        reason="borrowed sample",
        provenance="public",
        source=None,
        license_="CC0",
        pin=f"sha256:{digest}",
    )
    try:
        repo = Repo(root=tmp_path, files=(_entry(path, tmp_path, body),))
        found = [v for v in check_inventory(repo) if "requires a 'source'" in v.detail]
        assert [v.rule for v in found] == ["R7"]
    finally:
        del al.SHIPPED_DATA[path]


def test_an_unrecognised_provenance_is_rejected() -> None:
    path = "tests/fixtures/lever/normal.json"
    original = al.SHIPPED_DATA[path]
    al.SHIPPED_DATA[path] = DataEntry(
        kind=original.kind,
        reason=original.reason,
        provenance="third-party",
        source="https://example.com/x",
        pin=original.pin,
    )
    try:
        found = [
            v
            for v in check_inventory(discover(REPO_ROOT))
            if "is not one of" in v.detail and "provenance=" in v.detail
        ]
        assert [v.rule for v in found] == ["R7"]
    finally:
        al.SHIPPED_DATA[path] = original
