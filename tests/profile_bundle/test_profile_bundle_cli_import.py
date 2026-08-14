"""`profile-bundle import`: enumerating an owner-approved source into a draft's ledger.

Gate B's first mechanical step. Import has shipped since Gate A as typed models, deterministic
enumerators and validation, with `docs/profile-bundle-authoring.md` §16 telling the owner to author
`imports/source-ledger.yaml` by hand; nothing turned an enumerator's records into that document.

Two properties this file is answerable for, because both are how a denominator stops meaning
anything without any test going red:

- **Disposition is derived, never carried over by spelling.** `build_source_ledger` decides it from
  the candidates and exclusions already in the draft (`imports.py`), so a re-import cannot promote a
  record to `imported` on its own.
- **Re-importing an unchanged source changes no byte.** The ledger is the Gate B denominator; a
  document that churns on every run cannot be reviewed, and a digest over it would move for no
  reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.profile_bundle.paths import BUNDLE_DIR_NAME, draft_root
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from tests.profile_bundle.conftest import materialise, quoted_yaml

LEDGER = PurePosixPath("imports/source-ledger.yaml")
SOURCES = PurePosixPath("policy/sources.yaml")

RESUME_SOURCE_ID = "source.synthetic-resume"
#: A second source of the same kind, so a re-import can be exercised against a source that is not
#: the last one in the ledger. Without it the in-place splice cannot be told from remove-and-append.
SECOND_SOURCE_ID = "source.synthetic-resume-two"

#: A minimal document of exactly the shape `BoardwatchResumeEnumerator` accepts. Seven records:
#: two header, one education, two skill-group items, one entry metadata, one bullet. Counted here
#: rather than asserted from the adapter, so the test pins a number the adapter has to reach rather
#: than agreeing with whatever it produces.
RESUME_DOCUMENT: dict[str, Any] = {
    "header": ["Ada Lovelace", "ada@example.invalid"],
    "education": ["Example University, BSc"],
    "skill_groups": [{"label": "Languages", "items": ["Python", "Rust"]}],
    "entries": [
        {
            "entry_id": "entry-analytical-engine",
            "heading": "Example Labs",
            "kind": "experience",
            "title": "Engineer",
            "bullets": [{"bullet_id": "bullet-1", "text": "Built a synthetic thing."}],
        }
    ],
}
EXPECTED_RECORD_COUNT = 7


@dataclass(frozen=True)
class Env:
    data_dir: Path
    config_dir: Path

    @property
    def bundle_root(self) -> Path:
        return self.config_dir / BUNDLE_DIR_NAME

    @property
    def draft(self) -> Path:
        return draft_root(self.bundle_root, "baseline")

    def ledger(self) -> dict[str, Any]:
        raw = (self.draft / "imports" / "source-ledger.yaml").read_bytes()
        loaded = load_yaml_bytes(raw, logical_path=LEDGER)
        assert isinstance(loaded, dict)
        return loaded


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    """The comprehensive example as `drafts/baseline`, with a résumé source declared in policy.

    The example ships three sources, none of them `boardwatch_resume`, so the kind Gate B actually
    needs has to be declared here. Declaring it in `policy/sources.yaml` is the owner-approval step
    the command deliberately does not perform for you.
    """
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(config_dir))
    root = config_dir / BUNDLE_DIR_NAME
    root.mkdir()
    (root / "drafts").mkdir()
    bundle = materialise(root)

    declared = load_yaml_bytes((bundle.draft / "policy" / "sources.yaml").read_bytes(),
                               logical_path=SOURCES)
    assert isinstance(declared, dict)
    declared["sources"].extend(
        [
            {
                "source_id": RESUME_SOURCE_ID,
                "source_kind": "boardwatch_resume",
                "portable_locator": "resume.yaml",
            },
            {
                "source_id": SECOND_SOURCE_ID,
                "source_kind": "boardwatch_resume",
                "portable_locator": "resume-two.yaml",
            },
        ]
    )
    (bundle.draft / "policy" / "sources.yaml").write_bytes(
        quoted_yaml(declared, logical_path=SOURCES)
    )
    return Env(data_dir=tmp_path / "data", config_dir=config_dir)


@pytest.fixture
def resume_file(tmp_path: Path) -> Path:
    """The source document, deliberately outside the bundle: it is the owner's own file."""
    path = tmp_path / "resume.yaml"
    path.write_bytes(quoted_yaml(RESUME_DOCUMENT, logical_path=PurePosixPath("resume.yaml")))
    return path


@pytest.fixture
def second_resume_file(tmp_path: Path) -> Path:
    """A different résumé, so the two sources cannot collide on a record ID."""
    path = tmp_path / "resume-two.yaml"
    path.write_bytes(
        quoted_yaml(
            {**RESUME_DOCUMENT, "header": ["Grace Hopper", "grace@example.invalid"]},
            logical_path=PurePosixPath("resume-two.yaml"),
        )
    )
    return path


def run(env: Env, args: list[str]):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(app, ["--data-dir", str(env.data_dir), "profile-bundle", *args])


def import_resume(env: Env, resume_file: Path, *, extra: list[str] | None = None):  # type: ignore[no-untyped-def]
    return _import(env, RESUME_SOURCE_ID, resume_file, extra)


def import_second(env: Env, resume_file: Path, *, extra: list[str] | None = None):  # type: ignore[no-untyped-def]
    return _import(env, SECOND_SOURCE_ID, resume_file, extra)


def _import(env: Env, source_id: str, document: Path, extra: list[str] | None):  # type: ignore[no-untyped-def]
    return run(
        env,
        [
            "import",
            "--draft",
            "baseline",
            "--source",
            source_id,
            "--from",
            str(document),
            *(extra or []),
        ],
    )


def test_import_resolves_the_source_through_the_local_sidecar_when_from_is_omitted(
    env: Env, resume_file: Path
) -> None:
    """§6's whole purpose: `local-sources.yaml` is how an owner reopens an original document.

    Without this the owner retypes an absolute path on every import, and the sidecar — the one file
    designed to hold exactly that path — never does the job it exists for. The mapping is to a
    ROOT, and the document is found beneath it at the source's `portable_locator`, because that
    split is what keeps the machine-local half out of every revisioned document.
    """
    (env.bundle_root / "local-sources.yaml").write_bytes(
        quoted_yaml(
            {RESUME_SOURCE_ID: str(resume_file.parent)},
            logical_path=PurePosixPath("local-sources.yaml"),
        )
    )
    result = run(env, ["import", "--draft", "baseline", "--source", RESUME_SOURCE_ID])
    assert result.exit_code == 0, result.output

    records = [row for row in env.ledger()["records"] if row["source_id"] == RESUME_SOURCE_ID]
    assert len(records) == EXPECTED_RECORD_COUNT


def test_import_refuses_when_neither_from_nor_a_sidecar_mapping_resolves_the_source(
    env: Env,
) -> None:
    """The refusal has to name both routes, because either one is a legitimate fix.

    Reported rather than crashed, and without an absolute path: an operator pastes this JSON into a
    bug report.
    """
    result = run(env, ["import", "--draft", "baseline", "--source", RESUME_SOURCE_ID, "--json"])
    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert body["result"] == {}
    codes = [item["code"] for item in body["diagnostics"]]
    assert "missing_required_file" in codes, body["diagnostics"]
    message = " ".join(item["message"] for item in body["diagnostics"])
    assert "--from" in message and "local-sources.yaml" in message


def test_import_enumerates_a_declared_source_into_the_draft_ledger(
    env: Env, resume_file: Path
) -> None:
    """The one thing that did not exist: enumerated records reaching `imports/source-ledger.yaml`.

    Exit 0, and that is worth stating plainly because it is easy to expect otherwise: every record
    this import adds is undispositioned, but `import_record_undispositioned` is a **completeness**
    finding, and the revalidation every authoring command ends with does not run that tier. The
    seven records are therefore reported by the command's own result, never by its exit code —
    which is why `counts_by_disposition` is in the result at all, and why the next test asserts the
    same seven records through `validate --completeness` instead.
    """
    result = import_resume(env, resume_file)
    assert result.exit_code == 0, result.output

    ledger = env.ledger()
    enumerated = [source for source in ledger["sources"] if source["source_id"] == RESUME_SOURCE_ID]
    assert len(enumerated) == 1, ledger["sources"]
    assert enumerated[0]["enumerator_id"] == "boardwatch-resume-v1"
    assert enumerated[0]["approved_scope"] == {"kind": "complete_file"}

    records = [row for row in ledger["records"] if row["source_id"] == RESUME_SOURCE_ID]
    assert len(records) == EXPECTED_RECORD_COUNT
    assert {row["disposition"] for row in records} == {"review_required"}
    assert enumerated[0]["source_record_ids"] == [row["source_record_id"] for row in records]


def test_the_seven_records_are_undispositioned_to_the_completeness_tier(
    env: Env, resume_file: Path
) -> None:
    """The same seven records, counted through the tier Gate B is actually measured at.

    Deliberately a second path: the import command reporting seven `review_required` records is the
    component's self-report, and §18's arithmetic is enforced by `validate --completeness`, which
    reads the document rather than the command's return value. If these two ever disagree, the
    denominator is wrong in one of them.
    """
    assert import_resume(env, resume_file).exit_code == 0
    result = run(
        env,
        ["validate", "--draft", "baseline", "--completeness", "--as-of", "2026-08-14", "--json"],
    )
    body = json.loads(result.output)
    undispositioned = [
        item
        for item in body["diagnostics"]
        if item["code"] == "import_record_undispositioned"
        and item["record_id"] in set(_record_ids(env, RESUME_SOURCE_ID))
    ]
    assert len(undispositioned) == EXPECTED_RECORD_COUNT, body["diagnostics"]


def test_re_importing_an_unchanged_source_moves_no_byte(env: Env, resume_file: Path) -> None:
    """The ledger is the Gate B denominator, and a document that churns cannot be reviewed."""
    assert import_resume(env, resume_file).exit_code == 0
    after_first = (env.draft / "imports" / "source-ledger.yaml").read_bytes()

    result = import_resume(env, resume_file, extra=["--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["result"]["changed"] is False
    assert (env.draft / "imports" / "source-ledger.yaml").read_bytes() == after_first


def test_a_re_import_keeps_a_disposition_the_owner_already_made(
    env: Env, resume_file: Path
) -> None:
    """The one that matters most, because getting it wrong is silent.

    Disposition is derived from the candidates and exclusions in the draft, so an exclusion the
    owner wrote after the first import must survive the second. A command that rebuilt the rows
    from the enumerator alone would quietly reset every decision the owner had made — and the
    ledger would still validate, because `review_required` is a legal disposition.
    """
    assert import_resume(env, resume_file).exit_code == 0
    excluded_id = _record_ids(env, RESUME_SOURCE_ID)[0]
    exclusions = PurePosixPath("imports/exclusions.yaml")
    # Appended, not replaced: the example already excludes a record of its own, and dropping that
    # exclusion would make the ledger inconsistent about a source this test never touched.
    document = load_yaml_bytes(
        (env.draft / "imports" / "exclusions.yaml").read_bytes(), logical_path=exclusions
    )
    assert isinstance(document, dict)
    document["exclusions"].append(
        {
            "source_record_id": excluded_id,
            "reason": "non_professional",
            "rationale": "A synthetic contact line, kept out of the profile.",
        }
    )
    (env.draft / "imports" / "exclusions.yaml").write_bytes(
        quoted_yaml(document, logical_path=exclusions)
    )

    result = import_resume(env, resume_file, extra=["--json"])
    # The counts are asserted BEFORE the exit code deliberately. Derive the disposition without the
    # draft's exclusions and validation also reports a denominator mismatch, so an exit-code
    # assertion placed first would trip on the consequence and this test would pass while asserting
    # nothing about the disposition it is named for.
    counts = json.loads(result.output)["result"]["counts_by_disposition"]
    assert counts == {
        "excluded": 1,
        "imported": 0,
        "review_required": EXPECTED_RECORD_COUNT - 1,
    }

    rows = {
        row["source_record_id"]: row["disposition"]
        for row in env.ledger()["records"]
        if row["source_id"] == RESUME_SOURCE_ID
    }
    assert rows[excluded_id] == "excluded"
    assert result.exit_code == 0, result.output


def test_importing_one_source_leaves_every_other_source_exactly_where_it_was(
    env: Env, resume_file: Path
) -> None:
    """A re-import touches one source. The other two are a diff an owner should never have to read."""
    before = env.ledger()
    untouched = [
        row for row in before["records"] if row["source_id"] != RESUME_SOURCE_ID
    ]
    before_sources = [source["source_id"] for source in before["sources"]]

    assert import_resume(env, resume_file).exit_code == 0

    after = env.ledger()
    assert [row for row in after["records"] if row["source_id"] != RESUME_SOURCE_ID] == untouched
    assert [source["source_id"] for source in after["sources"]] == [
        *before_sources,
        RESUME_SOURCE_ID,
    ]


def test_re_importing_a_source_that_is_not_last_keeps_its_position(
    env: Env, resume_file: Path, second_resume_file: Path
) -> None:
    """The splice replaces a source's block in place; it does not remove and re-append it.

    This needs a source with another one *after* it, which is why a second résumé source exists at
    all: once a source is last in the ledger, remove-and-append and replace-in-place produce the
    same document, and every cheaper arrangement of this test passes under either. The ledger is a
    document an owner reads, and a re-import that moved one source to the end would produce a diff
    across two sources for a change that touched one.
    """
    assert import_resume(env, resume_file).exit_code == 0
    assert import_second(env, second_resume_file).exit_code == 0
    before = [source["source_id"] for source in env.ledger()["sources"]]
    before_records = [row["source_id"] for row in env.ledger()["records"]]
    assert before[-1] == SECOND_SOURCE_ID, before

    assert import_resume(env, resume_file).exit_code == 0

    assert [source["source_id"] for source in env.ledger()["sources"]] == before
    assert [row["source_id"] for row in env.ledger()["records"]] == before_records


def test_import_refuses_a_source_the_policy_catalog_does_not_declare(
    env: Env, resume_file: Path
) -> None:
    """The catalog is where a source becomes one the bundle may read, so this cannot be inferred."""
    result = run(
        env,
        [
            "import",
            "--draft",
            "baseline",
            "--source",
            "source.never-approved",
            "--from",
            str(resume_file),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert body["result"] == {}
    assert [item["code"] for item in body["diagnostics"]] == ["broken_reference"]


def test_import_refuses_to_derive_a_selected_sections_scope(env: Env, tmp_path: Path) -> None:
    """Which sections may be read is the owner's decision, and §18 prices it at a new approval.

    A `repository_markdown` source with no ledger row yet has no approved scope, and deriving one
    would be this command approving its own input. The example's existing repository source is not
    a substitute: it already carries a scope, so it exercises the reuse branch instead.
    """
    declared = load_yaml_bytes((env.draft / "policy" / "sources.yaml").read_bytes(),
                               logical_path=SOURCES)
    assert isinstance(declared, dict)
    declared["sources"].append(
        {
            "source_id": "source.synthetic-unscoped-repository",
            "source_kind": "repository_markdown",
            "portable_locator": "docs/README.md",
        }
    )
    (env.draft / "policy" / "sources.yaml").write_bytes(
        quoted_yaml(declared, logical_path=SOURCES)
    )
    document = tmp_path / "README.md"
    document.write_text("# Title\n\nA paragraph.\n", encoding="utf-8")

    result = run(
        env,
        [
            "import",
            "--draft",
            "baseline",
            "--source",
            "source.synthetic-unscoped-repository",
            "--from",
            str(document),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert [item["code"] for item in body["diagnostics"]] == ["import_scope_invalid"]


def test_re_importing_a_scoped_source_reuses_the_scope_the_owner_approved(
    env: Env, tmp_path: Path
) -> None:
    """§18: the approved scope is a property of the ledger, not of the enumerator.

    The example's repository source is approved for `readme/architecture` alone. Re-importing it
    must enumerate under exactly that scope — not the whole file — because a command that widened
    the scope would read sections the owner never approved, and the widening is supposed to cost a
    new approval. The `unapproved` section exists precisely so the difference is visible: under the
    approved scope this document yields two records, and the whole file would yield five.

    Headings are lowercase because a heading path preserves case, and the example's approved
    locator is `readme/architecture`. A capitalised heading resolves to `Readme/Architecture` and
    matches no selected section — which is a refusal, not a wider read.
    """
    document = tmp_path / "README.md"
    document.write_text(
        "# readme\n\n## architecture\n\nA synthetic architecture paragraph.\n\n"
        "## unapproved\n\nA section outside the approved scope.\n",
        encoding="utf-8",
    )
    result = run(
        env,
        [
            "import",
            "--draft",
            "baseline",
            "--source",
            "source.synthetic-repository",
            "--from",
            str(document),
            "--json",
        ],
    )
    body = json.loads(result.output)
    assert body["result"]["record_count"] == 2, body["result"]
    ledger_source = next(
        source
        for source in env.ledger()["sources"]
        if source["source_id"] == "source.synthetic-repository"
    )
    assert ledger_source["approved_scope"] == {
        "kind": "selected_sections",
        "locators": ["readme/architecture"],
    }


def test_a_source_that_is_not_the_shape_the_adapter_expects_is_refused_not_crashed(
    env: Env, tmp_path: Path
) -> None:
    """An owner points `--from` at the wrong file eventually. It has to read as a refusal."""
    wrong = tmp_path / "not-a-resume.yaml"
    wrong.write_bytes(
        quoted_yaml({"unexpected": "shape"}, logical_path=PurePosixPath("not-a-resume.yaml"))
    )
    result = import_resume(env, wrong, extra=["--json"])
    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert body["result"] == {}
    assert [item["code"] for item in body["diagnostics"]] == ["model_validation_error"]


def test_no_diagnostic_carries_an_absolute_path(env: Env, tmp_path: Path) -> None:
    """§7's rule for this command family, checked on the arm that handles the operator's own file.

    The refusal is about a document outside the bundle, which is precisely where an absolute path
    would otherwise be the most natural thing to report.
    """
    wrong = tmp_path / "not-a-resume.yaml"
    wrong.write_bytes(quoted_yaml({"unexpected": 1}, logical_path=PurePosixPath("x.yaml")))
    result = import_resume(env, wrong, extra=["--json"])
    rendered = json.dumps(json.loads(result.output)["diagnostics"])
    assert str(tmp_path) not in rendered
    assert str(env.bundle_root) not in rendered


def _record_ids(env: Env, source_id: str) -> list[str]:
    return [
        row["source_record_id"]
        for row in env.ledger()["records"]
        if row["source_id"] == source_id
    ]
