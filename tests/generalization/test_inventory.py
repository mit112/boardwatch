"""R7: no data file enters the tree without a reviewed inventory entry."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.generalization import allowlists as al
from tools.generalization.allowlists import DataEntry
from tools.generalization.discovery import Repo, RepoFile, discover
from tools.generalization.inventory import (
    _data_literals,
    _registry_rows,
    _registry_tags,
    check_inventory,
    check_registry_invariants,
    inventory_scope,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _entry(path: str, tmp_path: Path, body: str = "a: 1\n") -> RepoFile:
    target = tmp_path / "blob"
    target.write_text(body, encoding="utf-8")
    return RepoFile(path=path, abspath=target, is_text=True, text=body)


def _repo_with(path: str, text: str, tmp_path: Path) -> Repo:
    """The real tree with one file's content replaced by a fixture."""
    files = tuple(f for f in discover(REPO_ROOT).files if f.path != path) + (
        RepoFile(path=path, abspath=tmp_path / "substitute", is_text=True, text=text),
    )
    return Repo(root=REPO_ROOT, files=files)


def _repo_without(path: str) -> Repo:
    """The real tree with one file absent."""
    return Repo(
        root=REPO_ROOT,
        files=tuple(f for f in discover(REPO_ROOT).files if f.path != path),
    )


def test_scope_covers_data_files_repo_wide() -> None:
    scope = inventory_scope(discover(REPO_ROOT))
    assert "src/boardwatch/registry/companies.yaml" in scope
    assert "src/boardwatch/eligibility/rules.yaml" in scope
    assert "tests/fixtures/lever/normal.json" in scope
    assert "src/boardwatch/tailor/register.yaml" in scope
    assert "src/boardwatch/tailor/personas.yaml" in scope
    assert "src/boardwatch/profile_bundle/resources/career-profile.schema.json" in scope
    assert len(scope) == 41


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


def test_real_tree_registry_invariants_hold() -> None:
    assert check_registry_invariants(discover(REPO_ROOT)) == []


def test_exactly_one_canonical_company_enumeration() -> None:
    designated = [p for p, e in al.SHIPPED_DATA.items() if e.kind == "company_enumeration"]
    assert designated == [al.CANONICAL_REGISTRY_PATH]


def test_a_second_company_enumeration_is_rejected() -> None:
    repo = discover(REPO_ROOT)
    al.SHIPPED_DATA["docs/other_companies.yaml"] = DataEntry(
        kind="company_enumeration", reason="sneaked in"
    )
    try:
        found = [v for v in check_registry_invariants(repo) if "exactly one" in v.detail]
        assert [v.rule for v in found] == ["R8"]
    finally:
        del al.SHIPPED_DATA["docs/other_companies.yaml"]


def test_the_real_loader_references_exactly_the_canonical_filename() -> None:
    loader = discover(REPO_ROOT).by_path(al.REGISTRY_LOADER_PATH)
    assert loader is not None
    assert _data_literals(loader.text) == {"companies.yaml"}


def test_loader_reading_a_second_data_file_is_rejected(tmp_path: Path) -> None:
    source = 'X = "companies.yaml"\nY = "extra_companies.yaml"\n'
    found = [
        v
        for v in check_registry_invariants(_repo_with(al.REGISTRY_LOADER_PATH, source, tmp_path))
        if "loader must reference only" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]


def test_no_permitted_registry_tag_is_unused() -> None:
    """A permitted tag nobody uses is a rubber stamp waiting to be used. Same bidirectional
    discipline the shape-rule exception tables get."""
    registry = discover(REPO_ROOT).by_path(al.CANONICAL_REGISTRY_PATH)
    assert registry is not None
    rows, problem = _registry_rows(registry.text)
    assert problem is None
    used = {tag for tag, _ in _registry_tags(rows)[0]}
    assert al.ALLOWED_REGISTRY_TAGS - used == frozenset()


def test_personal_registry_tag_is_rejected(tmp_path: Path) -> None:
    body = 'companies:\n  - {name: A, provider: greenhouse, slug: a, tags: [dream-job]}\n'
    found = [
        v
        for v in check_registry_invariants(_repo_with(al.CANONICAL_REGISTRY_PATH, body, tmp_path))
        if "outside the public vocabulary" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]
    assert "dream-job" in found[0].detail


def test_a_restructured_registry_is_reported_not_skipped(tmp_path: Path) -> None:
    """The Critical this round fixes: an unrecognised shape used to read as 'no bad tags',
    so restructuring the YAML disabled the tag check while the gate stayed green."""
    body = "version: 2\nentries:\n  - {name: A, provider: greenhouse, slug: a, tags: [x]}\n"
    found = [
        v
        for v in check_registry_invariants(
            _repo_with(al.CANONICAL_REGISTRY_PATH, body, tmp_path)
        )
        if "no top-level 'companies' key" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]


def test_an_unparseable_registry_is_reported(tmp_path: Path) -> None:
    body = "companies:\n  - {slug: a\n  bad: [\n"
    found = [
        v
        for v in check_registry_invariants(
            _repo_with(al.CANONICAL_REGISTRY_PATH, body, tmp_path)
        )
        if "could not be parsed as YAML" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]


def test_a_top_level_list_registry_is_reported(tmp_path: Path) -> None:
    body = "- {name: A, provider: greenhouse, slug: a, tags: [x]}\n"
    found = [
        v
        for v in check_registry_invariants(
            _repo_with(al.CANONICAL_REGISTRY_PATH, body, tmp_path)
        )
        if "top-level list" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]


def test_an_empty_registry_is_reported(tmp_path: Path) -> None:
    found = [
        v
        for v in check_registry_invariants(_repo_with(al.CANONICAL_REGISTRY_PATH, "", tmp_path))
        if "is empty" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]


def test_malformed_tags_are_reported_once_not_per_character(tmp_path: Path) -> None:
    body = "companies:\n  - {name: A, provider: greenhouse, slug: a, tags: notalist}\n"
    found = [
        v
        for v in check_registry_invariants(
            _repo_with(al.CANONICAL_REGISTRY_PATH, body, tmp_path)
        )
        if "expected a list" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]


def test_loader_prose_naming_the_registry_is_not_a_reference(tmp_path: Path) -> None:
    """A docstring or error message ending in the filename is prose, not a path reference.
    Firing on it would be the 'rule fires on legitimate content' failure this phase corrects."""
    source = (
        '"""Loads companies.yaml"""\n'
        "from pathlib import Path\n"
        'PATH = Path(__file__).parent / "companies.yaml"\n'
        'def read() -> None:\n    raise OSError("cannot read companies.yaml")\n'
    )
    assert check_registry_invariants(_repo_with(al.REGISTRY_LOADER_PATH, source, tmp_path)) == []


def test_an_unparseable_loader_is_reported(tmp_path: Path) -> None:
    found = [
        v
        for v in check_registry_invariants(
            _repo_with(al.REGISTRY_LOADER_PATH, "def broken(\n", tmp_path)
        )
        if "could not be parsed as Python" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]


def test_a_missing_loader_is_reported() -> None:
    found = [
        v
        for v in check_registry_invariants(_repo_without(al.REGISTRY_LOADER_PATH))
        if "loader is missing" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]


def test_a_missing_registry_file_is_reported() -> None:
    found = [
        v
        for v in check_registry_invariants(_repo_without(al.CANONICAL_REGISTRY_PATH))
        if "registry file is missing" in v.detail
    ]
    assert [v.rule for v in found] == ["R8"]
