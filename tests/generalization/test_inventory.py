"""R7: no data file enters the tree without a reviewed inventory entry."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.generalization import allowlists as al
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
    found = check_inventory(repo)
    assert [v.rule for v in found] == ["R7"]
    assert "not in SHIPPED_DATA" in found[0].detail


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
    al.SHIPPED_DATA[pinned] = type(original)(
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


def test_non_first_party_provenance_requires_a_source(tmp_path: Path) -> None:
    path = "docs/borrowed.yaml"
    body = "a: 1\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    entry_type = type(al.SHIPPED_DATA["tests/fixtures/lever/normal.json"])
    al.SHIPPED_DATA[path] = entry_type(
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
