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
        pin="sha256:8b6ce4f02ab311c53b0007691424da376a4d1637eb954dbeae24b968a6d24c41",
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
    "src/boardwatch/tailor/personas.yaml": DataEntry(
        kind="taxonomy",
        reason="Curated generic persona registry (résumé-presentation lenses: title, "
        "skill-group order, entry subset, deterministic JD role-family selection). Describes "
        "the mechanism, not one user; overridable per user via {config_dir}/personas.yaml "
        "(P4 item 7, D-062)",
        pin="sha256:baa9e9cbe736182e7a8b3376a3699d383e191a1d5526f765b0de63b06e185c3c",
    ),
    "src/boardwatch/rank/leveling.yaml": DataEntry(
        kind="taxonomy",
        reason="Seniority level grammars, company-free rung ladders, and per-field word "
        "meanings. Describes how postings word seniority, not one user's targets — it "
        "contains no company names at all, because a company's ladder is not a fact "
        "boardwatch can ship. The company binding is user config in "
        "{config_dir}/leveling-bindings.yaml (D-246)",
        pin="sha256:65f6ee5ec230480840831aaea17d63d09e6a6b2f61acfe3921889c59f8ee2e07",
    ),
    "src/boardwatch/registry/companies.yaml": DataEntry(
        kind="company_enumeration",
        reason="The one public starter registry of company job boards. Schema-validated, "
        "health-verified in CI, tags limited to ALLOWED_REGISTRY_TAGS",
    ),
    "web/package.json": DataEntry(
        kind="template",
        reason=(
            "The frontend's dependency and script declaration for the local review web app. "
            "Declares build tooling only, no person, employer, posting or metric. Pinned "
            "because a change to the dependency set of a bundle that ships inside the wheel "
            "is security-sensitive and must be a deliberate act rather than a drift."
        ),
        pin="sha256:457f6e0121c39c176bc302596e13022d6fe9b19d525d7712f3aed0a52277603f",
    ),
    "web/package-lock.json": DataEntry(
        kind="template",
        reason=(
            "The resolved dependency tree behind the committed frontend bundle. Ships so a "
            "clean checkout rebuilds the exact bytes in src/boardwatch/web/static/, which "
            "the CI web-bundle job verifies. Pinned for the same reason as package.json, "
            "more strongly: this file decides which third-party code is compiled into a "
            "published artifact."
        ),
        pin="sha256:bb1058eef052b0279878d6fe9801c7f73f627b7b4d439894314a86636b5f7f35",
    ),
    "web/tsconfig.json": DataEntry(
        kind="template",
        reason=(
            "TypeScript compiler settings for the frontend. Describes compilation, not "
            "data."
        ),
        pin="sha256:a35c9cfab65389e8d51e9c2b79569decd72f73c94edafb261d12580176ad63f1",
    ),
    "src/boardwatch/delivery/answers.example.yaml": DataEntry(
        kind="template",
        reason="Placeholder-only schema for the read-and-copy answers panel served by "
        "`boardwatch web` (delivery design §9). Declares the field names an application form "
        "asks for; carries no real name, email, phone or link, and deliberately ships NO "
        "work-authorisation value at all, because that is the one answer a first-run user must "
        "not inherit from a template. The user copies it to {config_dir}/answers.yaml and their "
        "copy is never committed. Pinned so a real value cannot be added without the pin failing.",
        pin="sha256:1cec1cd8c400bed7f212fb221393d73887df16625f37e2e79f293702e0788824",
    ),
    "src/boardwatch/profile_bundle/resources/career-profile.schema.json": DataEntry(
        kind="template",
        reason="JSON Schema generated from the career-profile bundle's typed models, shipped so an "
        "authoring person or agent can read the contract without running the code (Gate A design "
        "§19). Describes record SHAPES only — no person, organisation, metric or claim value. A "
        "parity test asserts the committed bytes equal schema.schema_json() exactly, so this pin "
        "and that test together stop the shipped contract from drifting from the models.",
        pin="sha256:92214ec3264432bd2d7bd3a6080f1d5a3faadc83afcc7bcb39906f963c619f05",
    ),
    "src/boardwatch/profile_bundle/resources/predicate-catalog-v1.yaml": DataEntry(
        kind="taxonomy",
        reason="The builtin starter predicate catalog seeded into every fresh career-profile "
        "bundle (Gate B Slice A, design §5). A generic, field-agnostic vocabulary of record "
        "predicate CONTRACTS (subject kinds, value types, evidence, surfaces) — describes the "
        "world, not one user, and carries no person, organisation or claim value. The audited "
        "comprehensive-example rows plus two sanctioned changes (technology.used admits "
        "incidental; a new project.name). Content-addressed into the bundle, so it is pinned "
        "rather than exempted; docs/profile-bundle-predicate-catalog-audit.md records the audit.",
        pin="sha256:66ede8814efce3e41203525fb3344ecf34e2870c9af9d649b09b26c02477e09b",
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
        pin="sha256:26787e133fabf1aa9a761e29ac586498cf0ac527e5143658ddd4a2186d5666a8",
    ),
    "src/boardwatch/projection/examples/projection.example.yaml": DataEntry(
        kind="fixture",
        reason=(
            "The example editorial declaration for bundle-to-résumé projection, over the "
            "synthetic career-profile bundle. Synthetic throughout, so the golden projection "
            "test runs in CI with no owner content."
        ),
        provenance="synthetic",
        source="authored for this task, over the synthetic "
        "profile_bundle/examples/comprehensive fixture",
        pin="sha256:bff0a349d460d5f48e421d06ff95045a2a5de60ee5e5057b858069c0bfcbbe61",
    ),
    "src/boardwatch/projection/examples/projection.golden.txt": DataEntry(
        kind="fixture",
        reason=(
            "The golden projected document: `project_pool` run over the synthetic "
            "career-profile bundle and `projection.example.yaml`, serialised by "
            "`serialize.resume_document_bytes`. Synthetic throughout — no owner content — so "
            "the byte-equality test runs in CI. Regenerated by calling the generator and "
            "writing its output by hand; there is no snapshot-update flag."
        ),
        provenance="synthetic",
        source="generated for this task by projection.pool.project_pool over the synthetic "
        "profile_bundle/examples/comprehensive fixture and projection.example.yaml",
        pin="sha256:9a5b3b7446617040c1cfbf73f4ad6590011d03380fd8a4be47932b3a267b85bc",
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
    "tests/fixtures/workday/list_censored_with_facets.json": DataEntry(
        kind="fixture",
        reason=_FIXTURE,
        pin="sha256:e87de23c8ec3289bf4ae845ace25d1fb528e1055eb743814f4a9b7ace1dceb9f",
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


# The comprehensive synthetic bundle example (Gate A design sections 19 and 22). One pin per
# document, each on its own line so an edit to any single file is visible in the diff, but sharing
# one reason and one path root because these are 33 documents of ONE artifact rather than 33
# independent decisions. Every value in it is invented -- Example Candidate, Example Labs, Example
# University, Packet Pantry, an example.com contact -- and it ships as package data so a person or
# an authoring agent has a complete, valid bundle to read alongside the generated JSON Schema. It
# is also the fixture every Gate A model, layout, identity, validation, promotion and CLI test runs
# against, which is why it is pinned: a silent edit would move the digests those tests assert.
_BUNDLE_EXAMPLE_ROOT = "src/boardwatch/profile_bundle/examples/comprehensive"

_BUNDLE_EXAMPLE_REASON = (
    "One document of the comprehensive synthetic career-profile bundle example: fully invented "
    "values, shipped as package data as the readable companion to the generated JSON Schema, and "
    "used as the fixture for every Gate A validation and promotion test."
)

_BUNDLE_EXAMPLE_PINS: dict[str, str] = {
    "application/gated-facts.yaml":
        "sha256:dfa4d4074248e9ddf14e2bd8e89a22349a873a7e9972c1668a39be07420d7482",
    "claims/bullet-candidates.yaml":
        "sha256:f36df58c49251558f7abd1bc03607fc35bc2792fbf2e386bf0c2f396c7ac2af9",
    "claims/summary-candidates.yaml":
        "sha256:7b29c304a26e69b539a32dc32841ad8a0b672f86aabe98d2ea71724b04bca6ea",
    "conflicts/groups.yaml":
        "sha256:c1af2b5b9f3cad187b4a70be56fd93905a0eb463ceb92a2044bb1e3a825e611a",
    "conflicts/rulings.yaml":
        "sha256:c9679bd12c8cead852bdafbb4f164c2771d5867d4606f9425b5c9b5186d04345",
    "evidence/records.yaml":
        "sha256:f8b141ac260230517981753671647cf6c8fe129401e724916aa8eba2b88f191b",
    "facts/affiliations.yaml":
        "sha256:761319ddc42e8bf9316f51ccb71b6f2033e3248224cde3b76ca5fbf0ac300618",
    "facts/awards.yaml":
        "sha256:1cc2a9e7dbcfe40fd13cf39c4917824124ded6604b7a6cfb58984814db9f3de8",
    "facts/certifications.yaml":
        "sha256:ff2548790d99ecce875db0100509d4a74b874f2b3ac3fc16ec5ee79f254c5167",
    "facts/courses.yaml":
        "sha256:43f7a13e37cf2c5274427ab78b20016c1a3729965aa1cccd7ef9471bda957d18",
    "facts/education.yaml":
        "sha256:86f19bee927a530ff4bcdc6cd854ccae9e808ea6fcb582ebffafe0b2e1e6ca05",
    "facts/experience/employment.example-labs.yaml":
        "sha256:7a3acb072dbf7a6a8173ba2da50dd92e86105ae4da7f1096a0c6630c448c21be",
    "facts/identity.yaml":
        "sha256:597e2d3de7b9d63542a2286fe09361d85826358491f4ee75803a77cd6d645b33",
    "facts/patents.yaml":
        "sha256:ca720fa926db6fabaecdec0a1a0b38c0066f99439b1f4776744cea8a6bf99c57",
    "facts/presentations.yaml":
        "sha256:e684690e2f3a93d08aa5f744c38bcd519e839c19cccf2434cbfeb4ae7be8ba99",
    "facts/projects/project.packet-pantry.yaml":
        "sha256:007713158d4c5e56ea0a61843f200215faf5e116752c5cc3f7303cea33c4454e",
    "facts/publications.yaml":
        "sha256:9992e6009ac516e41027882ea7127d040b7bd1c6cf55bfc102284f7298744d1c",
    "history/approvals.yaml":
        "sha256:45d72b74246e2e65aadab40d58f14a68064c041901b45605f7849fb5260f301e",
    "history/changes.yaml":
        "sha256:7ab038d67defb45a80bf8ca9dbfceea24b3c1b1f06d2bafe5f08c06b0344d770",
    "imports/candidates.yaml":
        "sha256:72441cc66ff2abad028751d89edeeef3f52772075c9bb1542efd020828d7f5dd",
    "imports/exclusions.yaml":
        "sha256:9b9af24f0e1361ea69c81d79de39d971828d9e9a49a145bcbd6c1160ba714bad",
    "imports/extraction-report.yaml":
        "sha256:d07739139cac7fe2b7e68e0751723662c03f27fbe838e09b5fdcb85825337764",
    "imports/source-ledger.yaml":
        "sha256:54944a319fcae78bb170d9ba7bdb04aaa0972038f57499f6b6aa1acc0ea1c450",
    "manifest.yaml":
        "sha256:793af34cc74f4ae504259e6d02a039b7d00038eb8c1d7ea8763fb0f7c5467541",
    "metrics/records.yaml":
        "sha256:0e43342b74ab39230e7c3cd06cab040d4619ebdebf3d50269c497f697a259f42",
    "policy/assertion-tags.yaml":
        "sha256:7b6611700c8b75f6ecd603170e994cf24b4fa9decce3b19de2074cf50cbc35a7",
    "policy/extraction-mappings.yaml":
        "sha256:3d073bcd17648f97a69c5145fdb1eda367d8a969177661ff5382b4ed443d25e2",
    "policy/predicates.yaml":
        "sha256:bbae76d1f85baae28e5ffecfb343becb2525a0a7aa72e31d391b1124fb399cc7",
    "policy/relations.yaml":
        "sha256:ccc7d7adf02df6b746e130624ef94ddacd8dbcc38c1d051d718d03e790ced9bd",
    "policy/secret-scan.yaml":
        "sha256:35285428a600ad9eb7ca8ab7e7d6345f5a43a8dc83071656360c83d4b0b7d66b",
    "policy/skill-categories.yaml":
        "sha256:718c17258356a9e3d62a61ba739fb668c22d9600834271b78fec3e701649301f",
    "policy/sources.yaml":
        "sha256:783170039199ba516d91c8f9b90963dc94142dd621bb1aae1e3096f66cc56787",
    "policy/units.yaml":
        "sha256:c65149400c55dcdf4061407d90842a5aa4adfd31cd4a826c8871a93a358179f7",
    "relations/records.yaml":
        "sha256:4fd9acf24620dd9c55ce1517c67f9c63234b26459db80a8f8dcd7d15eaddbf16",
    "skills/inventory.yaml":
        "sha256:a3d91788d0a25605607c5a4f18fbec87526b177b0da744e37a14ea3867d3f108",
}

SHIPPED_DATA.update(
    {
        f"{_BUNDLE_EXAMPLE_ROOT}/{relative}": DataEntry(
            kind="fixture",
            reason=_BUNDLE_EXAMPLE_REASON,
            provenance="synthetic",
            source="generated for Gate A model and validation tests",
            pin=pin,
        )
        for relative, pin in _BUNDLE_EXAMPLE_PINS.items()
    }
)

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
