"""Reviewed exceptions and the shipped-data inventory.

Every entry carries a reason, so intent is visible in the diff that adds it. Every
table is checked bidirectionally: an unmatched entry is itself a violation, which
stops these tables from rotting into rubber stamps.

Nothing in here may name a person. Identity is matched by SHAPE only. A public repo
shipping a denylist of the maintainer's name, email and handles would be exactly the
disclosure these checks exist to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass

# R1: exact matched text -> reason. Empty today; the tree uses no absolute home paths.
HOME_PATH_EXCEPTIONS: dict[str, str] = {}

# R2: exact email address -> reason. Reserved example domains never need an entry.
EMAIL_EXCEPTIONS: dict[str, str] = {}

# R3: exact matched text -> reason. Empty today; the tree uses no real phone numbers.
PHONE_EXCEPTIONS: dict[str, str] = {}

# R4: exact matched text -> reason. Empty today; the tree uses no personal profile URLs.
PROFILE_URL_EXCEPTIONS: dict[str, str] = {}

# R5: exact repo-relative path -> reason. Empty today.
ARTIFACT_NAME_EXCEPTIONS: dict[str, str] = {}

# R6: exact repo-relative path -> reason. Empty today; this repo ships no documents.
BINARY_DOC_EXCEPTIONS: dict[str, str] = {}


@dataclass(frozen=True)
class DataEntry:
    """One shipped data file and the justification for shipping it.

    `pin` is 'sha256:<digest>' for content that should not drift, or 'none' for
    living product data that has its own validators (see PIN_REQUIRED_KINDS).
    """

    kind: str
    reason: str
    provenance: str = "first-party"
    source: str | None = None
    license_: str | None = None
    pin: str = "none"


_FIXTURE = "Recorded provider API response, used by the contract tests"

SHIPPED_DATA: dict[str, DataEntry] = {
    "src/boardwatch/extract/taxonomy.yaml": DataEntry(
        kind="taxonomy",
        reason="Curated generic tech taxonomy. Describes the world, not one user. "
        "Overridable per user via {config_dir}/taxonomy.yaml (D24)",
    ),
    "src/boardwatch/registry/companies.yaml": DataEntry(
        kind="company_enumeration",
        reason="The one public starter registry of company job boards. Schema-validated, "
        "health-verified in CI, tags limited to ALLOWED_REGISTRY_TAGS",
    ),
    "src/boardwatch/store/migrations/script.py.mako": DataEntry(
        kind="template",
        reason="Alembic migration template",
        pin="sha256:114d2c8daf1106848ce42d0c5f13a4d0056ec4205dfc568999d988c131bb8c54",
    ),
    "tests/fixtures/ashby/dead.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:0019dfc4b32d63c1392aa264aed2253c1e0c2fb09216f8e2cc269bbfb8bb49b5",
    ),
    "tests/fixtures/ashby/empty.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:0e2e66ec1a28141acccbc898acd3fc5997247ee06c8af6536bd217b85b6f6d45",
    ),
    "tests/fixtures/ashby/huge.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:8c86b064f349f1c689268df34e5f9741cd42ec7fe86781f1652be5595a55517e",
    ),
    "tests/fixtures/ashby/normal.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:192aae6e9fbfdfad381a1177c0803833f1b252373a1ef3fd2b998688ddd866a1",
    ),
    "tests/fixtures/ashby/normal_response_headers.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:446f441dffc8409dec293489639013c3f2afb21930b3fa8f17378c9df96aa000",
    ),
    "tests/fixtures/greenhouse/dead_404.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:4cbfef08f9f6abcad34da29e9f9cdc15139efb08a3df3d33d767f83c02a63f7c",
    ),
    "tests/fixtures/greenhouse/empty.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:9fdf25af38a93d597125fdb48338ffd276e854c64953c0914ce921e72b408fed",
    ),
    "tests/fixtures/greenhouse/normal.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:26dced4509e250096176463e15a15ac8e766c3886ac32e2cdfb020dbf3a77d79",
    ),
    "tests/fixtures/greenhouse/normal_response_headers.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:2547602e77c8afb5fae16a39f7b063cafd860f56d9d6423a891167815d121257",
    ),
    "tests/fixtures/lever/dead_404.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:fe305e3fd91950ebc7e6576179bea6ae0d50aa627955c6945f54c6f94a24393c",
    ),
    "tests/fixtures/lever/empty.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "tests/fixtures/lever/normal.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:79ef841c032e76212da58aaf7dfde763f58d85e1544d105991b26b6c54cad6e1",
    ),
    "tests/fixtures/lever/normal_response_headers.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:0b71201005de8f1d3ca97c40ef9227e225338b36c56d82df8e476d088f0f3a42",
    ),
}
