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

    `pin` is 'sha256:<digest>' for content that should not drift. The only exceptions are
    named by path in `inventory.UNPINNED_PATHS`: living product data that churns and has its
    own validators. The exemption is bound to the path, not to `kind`, so a mislabelled entry
    cannot inherit it.
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
    "src/boardwatch/eligibility/rules.yaml": DataEntry(
        kind="taxonomy",
        reason="The eligibility rule catalog: requirement phrasings, answer types, "
        "vocabularies and ranks. Describes how postings word requirements, not one "
        "user's situation. A wrong pattern is a wrong verdict, so it is pinned rather "
        "than exempted (D-P2-7). Overridable per user via {config_dir}/rules.yaml",
        pin="sha256:82ac4ae6ab66f47d1c630a82fa5ffafcfbaaddb6f34a7831fadf7fb86bae8f12",
    ),
    "src/boardwatch/tailor/equivalences.yaml": DataEntry(
        kind="taxonomy",
        reason="Curated, entailment-neutral synonym trust root for Tier A résumé "
        "tailoring. Describes the world, not one user. Bundled-only, NOT user-overridable "
        "(safety-critical); frozen by sha256 pin.",
        pin="sha256:e0eb98d678e181d6022e265a68381581dc15012bdcfe0eebae337a2db3766627",
    ),
    "src/boardwatch/tailor/register.yaml": DataEntry(
        kind="taxonomy",
        reason="Curated universal English-register slop catalog (banned phrases, "
        "buzzwords, per-bullet buzzword-density ceiling, qualification-register cues "
        "for P4 item 3b) for the P4 craft guards. Describes bad résumé register in "
        "general, not one user. Bundled-only, NOT user-overridable (safety-critical); "
        "frozen by sha256 pin.",
        pin="sha256:7450b5a139d1ad893e0712fb1a4c87f4c04d9045e7f1fcaaf949e206aa8fca55",
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
    "src/boardwatch/tailor/render/templates/resume_base.tex": DataEntry(
        kind="template",
        reason="Bundled default LaTeX résumé template for the tectonic render substrate "
        "(Increment 1, Task 4). Generic placeholder header/contact/education only ('Your "
        "Name', example.com contact, a sample degree) so the default is user-agnostic; a "
        "real user's résumé installs their own at {config_dir}/resume_template.tex (Task 7) "
        "and that file wins over this one. Describes LaTeX layout macros, not any user's "
        "data.",
        provenance="first-party",
        source="derived from the 'Jake's Resume' LaTeX template lineage via job-apps' "
        "~/dev/Job apps/resume_base.tex, genericized for this repo",
        pin="sha256:d7715a26bc9f549743d722d92711da741b3c844e4247fd7a9ae126512486caa8",
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
    "tests/fixtures/smartrecruiters/detail_empty_sections.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:303c85bdb2bc3c7d88e4d6ab469e95df74b7113493b06afa11fe90e128bb425e",
    ),
    "tests/fixtures/smartrecruiters/detail_inactive.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:3c8c5bd504015bd0c95a2f9ac23003b7bdf7353bb41f771aa8e18b09483ddcfd",
    ),
    "tests/fixtures/smartrecruiters/detail_normal.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:13fb1a44e6785df1f93b50885d12063d30522e1685fbed6dc8faa5e7784360af",
    ),
    "tests/fixtures/smartrecruiters/list_empty.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:162a4602127b019eb5309242f077effbaf733b9f69341bc02f484c90a88ea858",
    ),
    "tests/fixtures/smartrecruiters/list_normal.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:ceb9f742f1080765aa6b5c7e96aff2851eff72487c8e02da1fd133fc9fe0a82f",
    ),
    "tests/fixtures/smartrecruiters/normal_response_headers.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:938f995faa5ae49c46c7966028dd432f7ffa68fd047ff5caf3b5d9ea2f9ed426",
    ),
    "tests/fixtures/workable/dead_404.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:915fab36326382fe808614aa7e51c19f748224912b213e645605bbf603a253a8",
    ),
    "tests/fixtures/workable/empty.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:17e77b255f65248cdf364acd2c3f8b486bd6c2a24890fc065298a8a01c929639",
    ),
    "tests/fixtures/workable/normal.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:fe2d1a390190f00fe28aa0f76b3e24ad4ea74545bed22eeccfa7c4ee4967b56f",
    ),
    "tests/fixtures/workable/normal_response_headers.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:3ea639fa92918e10fda9999671338499a58e00a38b0dc3500ddb10c5214f1c3a",
    ),
    "tests/fixtures/workday/dead_s21.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:42ba73a4e1b8c8e5f9fca0bdf32fedc0aeeca15d89ef706d705ae48a61d1236b",
    ),
    "tests/fixtures/workday/detail_normal.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:41bd4cebaf602f03f9d6c40c24515cd3872009ced1e1d2f2cbe1422758392efa",
    ),
    "tests/fixtures/workday/list_empty.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:3ab3f62d720d6cb3b5979758289474ece9c15c38c5c0c326b4216c1f6497287b",
    ),
    "tests/fixtures/workday/list_facet_intern.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:4d9b3774be1d33f58ebff384bbafc2bbe704820664f950d0da6ddce8dd5c4365",
    ),
    "tests/fixtures/workday/list_normal.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:24b9340cf07871cf4f3183f17000fbe94437908b5571df2db602e79aecdb0d24",
    ),
    "tests/fixtures/workday/list_page_full.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:352e377722d0c6c9319ea7909af68acc2c955d5e74786eebd6dcfe5735fdcb83",
    ),
    "tests/fixtures/workday/list_page_short.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:c4faf2d3125483286b95f80aabd381369ffdaac71c3bb9b2afe9789e74d91c60",
    ),
    "tests/fixtures/workday/normal_response_headers.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:f2a2052ca48f2144011ca0f180672fddac961efdc4d080fb47f30d45457a60e2",
    ),
    "tools/tier_b_eval/corpus.yaml": DataEntry(
        kind="corpus",
        reason="Hand-authored labeled evaluation corpus for the Tier B entailment gate. "
        "Describes fabrication patterns (invented skills, inflated numbers, scope creep, "
        "...), not any user's résumé or posting. Used only by the offline eval harness "
        "(tools/tier_b_eval) and one hermetic test; pinned because a silent edit would "
        "weaken the gate's measured false-accept bar.",
        pin="sha256:be1c9f5c61f8570c8f0a438ccd5d43eea3e861c42fcd955213eb5bcb7dfa5f14",
    ),
}

# The designation "the company registry" is bound to a literal path, not to a label a
# contributor picks, so a second bulk list cannot inherit the designation by relabelling.
# A second list CAN still be admitted under a different kind (a pinned first-party "corpus",
# say), and if it is read from any module other than the loader, the single-loader invariant
# never sees it either. The residual gate there is R7's diff-visible entry plus review, which
# is the honest limit rather than a hole nobody wrote down.
CANONICAL_REGISTRY_PATH = "src/boardwatch/registry/companies.yaml"
REGISTRY_LOADER_PATH = "src/boardwatch/registry/loader.py"

# Public, product-meaningful tags only. CompanyEntry(extra="forbid") blocks unknown
# KEYS but not unknown VALUES, so a personal annotation like tags: [dream-job] would
# otherwise validate cleanly.
ALLOWED_REGISTRY_TAGS: frozenset[str] = frozenset({"starter"})
