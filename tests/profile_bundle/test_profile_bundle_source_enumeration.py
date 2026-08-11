"""T12 deterministic source enumeration (design §18, §18.1).

The denominator Gate B is measured against is `len(source-ledger.records)`, and every property here
exists to keep that number meaningful:

- **Identity is derived, never proposed.** Every expected ID in this module is recomputed by a
  hand-rolled `hashlib`/`json` path rather than by calling the production helper, so a change to the
  derivation is a test failure instead of a test that agrees with itself.
- **Content digests are lineage, not identity.** Changing bytes at the same logical locator must
  leave the record ID and the record count alone while changing the record digest.
- **Re-enumeration is byte-identical.** Locators, order, IDs, and digests are asserted twice over
  the same bytes, because an adapter that iterated a `set` would still pass a single-run assertion.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from boardwatch.profile_bundle.enumerators import (
    _HEADING_RE,
    _MAX_HEADING_LEVEL,
    MARKDOWN_BLOCKS_V1,
    SOURCE_KIND_ADAPTERS,
    BoardwatchResumeEnumerator,
    EnumerationError,
    MarkdownBlocksEnumerator,
    StructuredObjectsEnumerator,
    derive_source_record_id,
    encode_locator_segment,
    enumerator_for,
    is_normalized_locator,
    normalize_locator,
    source_content_digest,
)
from boardwatch.profile_bundle.models.imports import CompleteFileScope, SelectedSectionsScope
from boardwatch.profile_bundle.models.policy import SourceKind

SOURCE = "source.synthetic-example"
COMPLETE = CompleteFileScope(kind="complete_file")


# --------------------------------------------------------------------------------------
# An independent digest path. Deliberately not the production serializer.
# --------------------------------------------------------------------------------------


def independent_digest(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def expected_record_id(source_id: str, locator: str) -> str:
    return "source-record." + independent_digest(["source-record", source_id, locator])


def locators(records: tuple[object, ...]) -> list[str]:
    return [record.normalized_locator for record in records]  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------
# The closed version-1 source-kind / adapter table (§18)
# --------------------------------------------------------------------------------------


def test_the_source_kind_adapter_table_is_exactly_the_designs_four_rows() -> None:
    assert {kind: (b.enumerator_id, b.enumerator_version, b.scope_kind)
            for kind, b in SOURCE_KIND_ADAPTERS.items()} == {
        SourceKind.BOARDWATCH_RESUME: ("boardwatch-resume-v1", 1, "complete_file"),
        SourceKind.MARKDOWN_DOCUMENT: ("markdown-blocks-v1", 1, "complete_file"),
        SourceKind.STRUCTURED_OBJECTS: ("structured-objects-v1", 1, "complete_file"),
        SourceKind.REPOSITORY_MARKDOWN: ("markdown-blocks-v1", 1, "selected_sections"),
    }


def test_the_table_covers_every_source_kind_so_a_new_kind_cannot_ship_unpaired() -> None:
    assert set(SOURCE_KIND_ADAPTERS) == set(SourceKind)


@pytest.mark.parametrize("kind", list(SourceKind))
def test_every_source_kind_resolves_to_its_declared_adapter(kind: SourceKind) -> None:
    adapter = enumerator_for(kind, source_id=SOURCE)
    binding = SOURCE_KIND_ADAPTERS[kind]
    assert adapter.id == binding.enumerator_id
    assert adapter.version == binding.enumerator_version


def test_repository_markdown_and_markdown_document_share_one_adapter_identity() -> None:
    assert (
        enumerator_for(SourceKind.REPOSITORY_MARKDOWN, source_id=SOURCE).id
        == enumerator_for(SourceKind.MARKDOWN_DOCUMENT, source_id=SOURCE).id
        == MARKDOWN_BLOCKS_V1
    )


# --------------------------------------------------------------------------------------
# Locator normalization (§18)
# --------------------------------------------------------------------------------------


def markdown_adapter() -> MarkdownBlocksEnumerator:
    return MarkdownBlocksEnumerator(source_id=SOURCE)


def test_a_locator_is_nfc_normalized_and_surrounding_whitespace_is_trimmed() -> None:
    decomposed = "cafe\u0301/x"
    composed = "caf\u00e9/x"
    assert decomposed != composed
    adapter = markdown_adapter()
    assert (
        normalize_locator(f"  {decomposed}  ", adapter=adapter)
        == normalize_locator(composed, adapter=adapter)
        == "caf%C3%A9/x"
    )


def test_a_locator_preserves_case() -> None:
    assert normalize_locator("Overview/Details", adapter=markdown_adapter()) == "Overview/Details"


def test_only_ascii_alphanumerics_and_dot_underscore_hyphen_survive_unescaped() -> None:
    assert (
        normalize_locator("a b/c~d/e.f_g-h", adapter=markdown_adapter())
        == "a%20b/c%7Ed/e.f_g-h"
    )


def test_a_non_ascii_segment_is_percent_encoded_from_its_utf8_bytes() -> None:
    assert encode_locator_segment("é", adapter=markdown_adapter()) == "%C3%A9"


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "/absolute/path", "a//b", "a/", "/a", "a/./b", "a/../b", ".", ".."],
)
def test_empty_absolute_dot_and_dotdot_locator_components_are_refused(raw: str) -> None:
    with pytest.raises(EnumerationError):
        normalize_locator(raw, adapter=markdown_adapter())


def test_a_segment_containing_a_slash_is_encoded_rather_than_split() -> None:
    assert encode_locator_segment("a/b", adapter=markdown_adapter()) == "a%2Fb"


def test_a_duplicate_heading_suffix_survives_re_normalization() -> None:
    """A resolved heading path is what an owner writes into a selected-sections scope, so
    normalizing one again must not turn its `~2` into `%7E2` and stop matching."""
    assert normalize_locator("Overview~2/Details", adapter=markdown_adapter()) == "Overview~2/Details"


@pytest.mark.parametrize(
    "text",
    ["_root/paragraph-1", "a%20b/c", "Overview~2/Details/heading", "objects/x.y_z-1"],
)
def test_a_normalized_locator_is_recognised_as_normalized(text: str) -> None:
    assert is_normalized_locator(text)


@pytest.mark.parametrize(
    "text",
    ["", "/a", "a//b", "a/./b", "a/../b", "a b", "a%2", "a%2g", "a%2f", "café", "a~1", "a~0"],
)
def test_a_locator_that_is_not_normalized_is_recognised_as_such(text: str) -> None:
    assert not is_normalized_locator(text)


# --------------------------------------------------------------------------------------
# Derived source-record identity (§18)
# --------------------------------------------------------------------------------------


def test_the_source_record_id_is_the_lowercase_sha256_of_the_canonical_json_array() -> None:
    assert derive_source_record_id(SOURCE, "_root/paragraph-1") == expected_record_id(
        SOURCE, "_root/paragraph-1"
    )


def test_the_source_record_id_depends_on_both_the_source_and_the_locator() -> None:
    assert derive_source_record_id(SOURCE, "a") != derive_source_record_id(SOURCE, "b")
    assert derive_source_record_id("source.other", "a") != derive_source_record_id(SOURCE, "a")


def test_source_content_digest_is_sha256_over_the_raw_bytes() -> None:
    raw = b"raw source bytes\r\n"
    assert source_content_digest(raw) == "sha256:" + hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------------------------
# markdown-blocks-v1 (§18.1)
# --------------------------------------------------------------------------------------

MARKDOWN = (
    "Intro paragraph before any heading.\n"
    "\n"
    "# Overview\n"
    "\n"
    "First overview paragraph.\n"
    "Still the same paragraph.\n"
    "\n"
    "- first bullet\n"
    "  continued at deeper indent\n"
    "- second bullet\n"
    "\n"
    "```text\n"
    "fenced line one\n"
    "fenced line two\n"
    "```\n"
    "\n"
    "### Details\n"
    "\n"
    "Detail paragraph.\n"
    "\n"
    "# Overview\n"
    "\n"
    "Duplicate heading body.\n"
)

MARKDOWN_LOCATORS = [
    "_root/paragraph-1",
    "Overview/heading",
    "Overview/paragraph-1",
    "Overview/list-item-1",
    "Overview/list-item-2",
    "Overview/fence-1",
    "Overview/Details/heading",
    "Overview/Details/paragraph-1",
    "Overview~2/heading",
    "Overview~2/paragraph-1",
]


def markdown_records(text: str = MARKDOWN, scope: object = COMPLETE) -> tuple[object, ...]:
    return markdown_adapter().enumerate(text.encode("utf-8"), scope=scope)  # type: ignore[arg-type]


def test_markdown_emits_every_block_in_source_order_with_the_designs_locators() -> None:
    assert locators(markdown_records()) == MARKDOWN_LOCATORS


def test_markdown_record_content_is_the_exact_source_substring_including_markers() -> None:
    by_locator = {r.normalized_locator: r.atomic_value for r in markdown_records()}  # type: ignore[attr-defined]
    assert by_locator["Overview/heading"] == "# Overview"
    assert by_locator["Overview/paragraph-1"] == (
        "First overview paragraph.\nStill the same paragraph."
    )
    assert by_locator["Overview/list-item-1"] == "- first bullet\n  continued at deeper indent"
    assert by_locator["Overview/fence-1"] == (
        "```text\nfenced line one\nfenced line two\n```"
    )
    assert by_locator["_root/paragraph-1"] == "Intro paragraph before any heading."


def test_markdown_record_ids_are_derived_from_source_and_locator() -> None:
    for record in markdown_records():
        assert record.source_record_id == expected_record_id(  # type: ignore[attr-defined]
            SOURCE, record.normalized_locator  # type: ignore[attr-defined]
        )


def test_markdown_record_digests_are_the_canonical_json_of_the_atomic_value() -> None:
    for record in markdown_records():
        assert record.record_content_digest == "sha256:" + independent_digest(  # type: ignore[attr-defined]
            record.atomic_value  # type: ignore[attr-defined]
        )


def test_re_enumeration_reproduces_byte_identical_locators_order_ids_and_digests() -> None:
    first = markdown_records()
    second = markdown_records()
    assert first == second


def test_crlf_and_cr_are_normalized_to_lf_for_record_content() -> None:
    crlf = MARKDOWN.replace("\n", "\r\n")
    assert markdown_records(crlf) == markdown_records()


def test_changed_bytes_at_the_same_locator_change_the_digest_without_churning_the_denominator(
) -> None:
    edited = MARKDOWN.replace("Detail paragraph.", "Detail paragraph, revised.")
    before = {r.normalized_locator: r for r in markdown_records()}  # type: ignore[attr-defined]
    after = {r.normalized_locator: r for r in markdown_records(edited)}  # type: ignore[attr-defined]

    assert set(before) == set(after), "the denominator churned"
    assert len(before) == len(after)
    target = "Overview/Details/paragraph-1"
    assert before[target].source_record_id == after[target].source_record_id
    assert before[target].record_content_digest != after[target].record_content_digest


def test_a_heading_stack_may_skip_levels_and_preserves_case() -> None:
    records = markdown_records("# Alpha\n\n### Beta\n\ntext\n")
    assert locators(records) == ["Alpha/heading", "Alpha/Beta/heading", "Alpha/Beta/paragraph-1"]


def test_a_deeper_heading_closes_when_a_shallower_one_follows() -> None:
    records = markdown_records("# A\n\n## B\n\nb text\n\n# C\n\nc text\n")
    assert locators(records) == [
        "A/heading",
        "A/B/heading",
        "A/B/paragraph-1",
        "C/heading",
        "C/paragraph-1",
    ]


def test_a_third_duplicate_heading_path_receives_the_next_suffix() -> None:
    records = markdown_records("# A\n\n# A\n\n# A\n")
    assert locators(records) == ["A/heading", "A~2/heading", "A~3/heading"]


def test_a_heading_body_is_encoded_as_exactly_one_locator_segment() -> None:
    records = markdown_records("# a/b c\n")
    assert locators(records) == ["a%2Fb%20c/heading"]


def test_a_blank_heading_body_is_a_hard_enumeration_error() -> None:
    with pytest.raises(EnumerationError):
        markdown_records("#   \n")


def test_a_line_of_hashes_without_a_space_is_not_a_heading() -> None:
    records = markdown_records("#no-space\n")
    assert locators(records) == ["_root/paragraph-1"]


def test_a_blank_line_ends_a_paragraph_and_is_not_a_record() -> None:
    records = markdown_records("one\n\ntwo\n")
    assert locators(records) == ["_root/paragraph-1", "_root/paragraph-2"]


def test_a_list_item_takes_only_lines_indented_farther_than_its_own_opener() -> None:
    records = markdown_records("- a\n  deeper\nnot deeper\n")
    values = [r.atomic_value for r in records]  # type: ignore[attr-defined]
    assert locators(records) == ["_root/list-item-1", "_root/paragraph-1"]
    assert values == ["- a\n  deeper", "not deeper"]


def test_a_tab_counts_to_the_next_multiple_of_four_indentation_columns() -> None:
    """The opener sits at column 3, so a one-tab continuation only qualifies if the tab
    advances to column 4. Counting a tab as one column leaves it at column 1 and splits it."""
    records = markdown_records("   - a\n\tcontinued\n")
    assert locators(records) == ["_root/list-item-1"]
    assert records[0].atomic_value == "   - a\n\tcontinued"  # type: ignore[attr-defined]


def test_an_ordered_list_opener_is_recognised() -> None:
    records = markdown_records("1. a\n2) b\n")
    assert locators(records) == ["_root/list-item-1", "_root/list-item-2"]


def test_a_tilde_fence_closes_only_on_its_own_character_and_length() -> None:
    records = markdown_records("~~~~\n```\nstill inside\n~~~~\nafter\n")
    assert locators(records) == ["_root/fence-1", "_root/paragraph-1"]
    assert records[0].atomic_value == "~~~~\n```\nstill inside\n~~~~"  # type: ignore[attr-defined]


def test_an_unterminated_fence_is_a_hard_enumeration_error() -> None:
    with pytest.raises(EnumerationError):
        markdown_records("```\nnever closed\n")


def test_a_closer_shorter_than_its_opener_does_not_close_the_fence() -> None:
    with pytest.raises(EnumerationError):
        markdown_records("````\n```\n")


def test_a_closer_needs_only_trailing_whitespace_after_its_run() -> None:
    """A same-character run followed by an info string is not a close. Treating it as one would
    end the fence early and leave the real closer opening a second, unterminated fence."""
    records = markdown_records("```\n```info\nstill inside\n```\nafter\n")
    assert locators(records) == ["_root/fence-1", "_root/paragraph-1"]
    assert records[0].atomic_value == "```\n```info\nstill inside\n```"  # type: ignore[attr-defined]


def test_markdown_requires_utf8() -> None:
    with pytest.raises(EnumerationError):
        markdown_adapter().enumerate(b"\xff\xfe not utf-8", scope=COMPLETE)


# --------------------------------------------------------------------------------------
# repository_markdown selected-section closure (§18.1)
# --------------------------------------------------------------------------------------


def selected(*paths: str) -> SelectedSectionsScope:
    return SelectedSectionsScope(kind="selected_sections", locators=tuple(paths))


def test_a_selected_heading_includes_its_heading_record_and_every_descendant_block() -> None:
    records = markdown_records(MARKDOWN, selected("Overview"))
    assert locators(records) == [
        "Overview/heading",
        "Overview/paragraph-1",
        "Overview/list-item-1",
        "Overview/list-item-2",
        "Overview/fence-1",
        "Overview/Details/heading",
        "Overview/Details/paragraph-1",
    ]


def test_a_selected_descendant_heading_selects_only_its_own_subtree() -> None:
    records = markdown_records(MARKDOWN, selected("Overview/Details"))
    assert locators(records) == ["Overview/Details/heading", "Overview/Details/paragraph-1"]


def test_overlapping_selected_scopes_deduplicate_while_preserving_source_order() -> None:
    overlapping = markdown_records(MARKDOWN, selected("Overview/Details", "Overview"))
    assert locators(overlapping) == locators(markdown_records(MARKDOWN, selected("Overview")))


def test_a_selected_scope_may_name_a_duplicate_suffixed_path() -> None:
    records = markdown_records(MARKDOWN, selected("Overview~2"))
    assert locators(records) == ["Overview~2/heading", "Overview~2/paragraph-1"]


def test_a_selected_heading_that_does_not_exist_is_a_hard_error() -> None:
    with pytest.raises(EnumerationError):
        markdown_records(MARKDOWN, selected("Nonexistent"))


@pytest.mark.parametrize("spelling", ["  Overview/Details  ", "Overview/Details ", " Overview"])
def test_a_selected_scope_locator_that_is_not_already_normalized_is_a_hard_error(
    spelling: str,
) -> None:
    """§18.1: a selected locator names an already-resolved heading path, so the adapter validates
    it rather than repairing it.

    This test previously asserted the opposite — that surrounding whitespace was trimmed before
    matching. Trimming makes the adapter accept a locator that `is_normalized_locator` refuses and
    that no enumeration can ever emit, which means the ledger's scope and the ledger's records can
    disagree about which string names a section. Refusing is the only spelling under which the two
    are the same string.
    """
    with pytest.raises(EnumerationError):
        markdown_records(MARKDOWN, selected(spelling))


def test_selecting_root_content_is_a_hard_error_because_root_is_not_a_heading() -> None:
    with pytest.raises(EnumerationError):
        markdown_records(MARKDOWN, selected("_root"))


# --------------------------------------------------------------------------------------
# boardwatch-resume-v1 (§18.1)
# --------------------------------------------------------------------------------------

RESUME = """\
title: Synthetic Headline
header:
- Example Candidate
- Somewhere
education:
- Example University
skill_groups:
- label: Languages
  items:
  - Example Language
  - Second Language
entries:
- entry_id: entry-one
  heading: Example Labs
  kind: experience
  title: Engineer
  dates: "2024-2025"
  subtitle: Platform
  location: Remote
  bullets:
  - bullet_id: bullet-one
    text: Built  the  ingestion  path
    tech_tags:
    - example-language
extracurricular:
- Example Society
"""

RESUME_LOCATORS = [
    "header/1",
    "header/2",
    "title",
    "education/1",
    "skill-groups/Languages/1",
    "skill-groups/Languages/2",
    "entries/entry-one/metadata",
    "entries/entry-one/bullets/bullet-one",
    "extracurricular/1",
]


def resume_records(text: str = RESUME) -> tuple[object, ...]:
    adapter = BoardwatchResumeEnumerator(source_id=SOURCE)
    return adapter.enumerate(text.encode("utf-8"), scope=COMPLETE)


def test_the_resume_adapter_emits_the_designs_record_boundaries_in_the_designs_order() -> None:
    assert locators(resume_records()) == RESUME_LOCATORS


def test_entry_metadata_is_emitted_as_a_stage_ahead_of_every_bullet() -> None:
    """§18.1 numbers metadata (5) and bullets (6) as separate emission stages, so every entry's
    metadata precedes every bullet rather than interleaving per entry. Pinned because canonical
    order is what `sources[].source_record_ids` must equal exactly."""
    two_entries = RESUME.replace(
        "extracurricular:",
        "- entry_id: entry-two\n  heading: Other\n  bullets:\n"
        "  - bullet_id: bullet-two\n    text: Second\nextracurricular:",
    )
    assert locators(resume_records(two_entries)) == [
        "header/1",
        "header/2",
        "title",
        "education/1",
        "skill-groups/Languages/1",
        "skill-groups/Languages/2",
        "entries/entry-one/metadata",
        "entries/entry-two/metadata",
        "entries/entry-one/bullets/bullet-one",
        "entries/entry-two/bullets/bullet-two",
        "extracurricular/1",
    ]


def test_a_resume_scalar_record_carries_the_authored_string_untouched() -> None:
    by_locator = {r.normalized_locator: r.atomic_value for r in resume_records()}  # type: ignore[attr-defined]
    assert by_locator["header/1"] == "Example Candidate"
    assert by_locator["title"] == "Synthetic Headline"
    assert by_locator["education/1"] == "Example University"
    assert by_locator["extracurricular/1"] == "Example Society"


def test_a_skill_item_record_carries_its_group_label_so_no_field_escapes_lineage() -> None:
    by_locator = {r.normalized_locator: r.atomic_value for r in resume_records()}  # type: ignore[attr-defined]
    assert by_locator["skill-groups/Languages/1"] == {
        "label": "Languages",
        "item": "Example Language",
    }


def test_entry_metadata_is_the_complete_entry_excluding_bullets() -> None:
    by_locator = {r.normalized_locator: r.atomic_value for r in resume_records()}  # type: ignore[attr-defined]
    assert by_locator["entries/entry-one/metadata"] == {
        "entry_id": "entry-one",
        "heading": "Example Labs",
        "kind": "experience",
        "title": "Engineer",
        "dates": "2024-2025",
        "subtitle": "Platform",
        "location": "Remote",
    }


def test_a_bullet_record_is_the_complete_bullet_object_including_tech_tags() -> None:
    by_locator = {r.normalized_locator: r.atomic_value for r in resume_records()}  # type: ignore[attr-defined]
    assert by_locator["entries/entry-one/bullets/bullet-one"] == {
        "bullet_id": "bullet-one",
        "text": "Built  the  ingestion  path",
        "tech_tags": ["example-language"],
    }


def test_the_adapter_does_not_run_the_tailor_loaders_bullet_whitespace_normalization() -> None:
    """The frozen tailor `Bullet` collapses every whitespace run to one space. Import must not:
    the authored string is the source datum, and collapsing it would make the record digest
    disagree with the bytes it claims lineage over."""
    bullet = next(
        r for r in resume_records() if r.normalized_locator.endswith("bullets/bullet-one")  # type: ignore[attr-defined]
    )
    assert "  " in bullet.atomic_value["text"]  # type: ignore[attr-defined,index]


def test_optional_resume_fields_default_rather_than_being_required() -> None:
    minimal = (
        "header:\n- Example Candidate\n"
        "education: []\nskill_groups: []\n"
        "entries:\n- entry_id: e\n  heading: H\n  bullets: []\n"
    )
    records = resume_records(minimal)
    assert locators(records) == ["header/1", "entries/e/metadata"]
    metadata = records[1].atomic_value  # type: ignore[attr-defined]
    assert metadata["kind"] == "experience"
    assert metadata["title"] is None


def test_a_null_title_emits_no_title_record() -> None:
    records = resume_records(RESUME.replace("title: Synthetic Headline", "title: null"))
    assert "title" not in locators(records)


@pytest.mark.parametrize(
    "replacement",
    [
        ("- Example Candidate\n- Somewhere", "- Example Candidate\n- '   '"),
        ("title: Synthetic Headline", "title: '  '"),
        ("- Example University", "- '  '"),
        ("  - Example Language\n", "  - '  '\n"),
        ("- Example Society", "- '  '"),
    ],
)
def test_a_blank_resume_scalar_record_is_refused(replacement: tuple[str, str]) -> None:
    old, new = replacement
    with pytest.raises(EnumerationError):
        resume_records(RESUME.replace(old, new))


def test_a_blank_skill_group_label_is_refused() -> None:
    with pytest.raises(EnumerationError):
        resume_records(RESUME.replace("label: Languages", "label: '  '"))


def test_a_blank_skill_group_label_is_refused_even_when_the_group_is_empty() -> None:
    """An empty group emits no record, so the locator encoder never sees the label. §18.1 refuses
    a blank label outright, which is what makes the group's own contract enforceable."""
    with pytest.raises(EnumerationError):
        resume_records(
            RESUME.replace(
                "- label: Languages\n  items:\n  - Example Language\n  - Second Language\n",
                "- label: '  '\n  items: []\n",
            )
        )


def test_duplicate_normalized_skill_group_labels_are_refused() -> None:
    duplicated = RESUME.replace(
        "- label: Languages\n  items:\n  - Example Language\n  - Second Language\n",
        "- label: Languages\n  items:\n  - A\n- label: 'Languages '\n  items:\n  - B\n",
    )
    with pytest.raises(EnumerationError):
        resume_records(duplicated)


def test_duplicate_entry_ids_are_refused() -> None:
    duplicated = RESUME.replace(
        "extracurricular:",
        "- entry_id: entry-one\n  heading: Other\n  bullets: []\nextracurricular:",
    )
    with pytest.raises(EnumerationError):
        resume_records(duplicated)


def test_duplicate_bullet_ids_are_refused_across_entries() -> None:
    duplicated = RESUME.replace(
        "extracurricular:",
        "- entry_id: entry-two\n  heading: Other\n  bullets:\n"
        "  - bullet_id: bullet-one\n    text: Another\nextracurricular:",
    )
    with pytest.raises(EnumerationError):
        resume_records(duplicated)


@pytest.mark.parametrize("blank", ["''", "'   '"])
def test_a_blank_entry_id_is_refused(blank: str) -> None:
    with pytest.raises(EnumerationError):
        resume_records(RESUME.replace("entry_id: entry-one", f"entry_id: {blank}"))


def test_an_unknown_resume_field_is_refused() -> None:
    with pytest.raises(EnumerationError):
        resume_records(RESUME + "unexpected: value\n")


def test_the_resume_adapter_refuses_a_selected_sections_scope() -> None:
    with pytest.raises(EnumerationError):
        BoardwatchResumeEnumerator(source_id=SOURCE).enumerate(
            RESUME.encode("utf-8"), scope=selected("anything")
        )


def test_resume_record_ids_are_derived_and_reproducible() -> None:
    first = resume_records()
    assert first == resume_records()
    for record in first:
        assert record.source_record_id == expected_record_id(  # type: ignore[attr-defined]
            SOURCE, record.normalized_locator  # type: ignore[attr-defined]
        )


def test_editing_one_bullet_leaves_every_other_record_untouched() -> None:
    edited = RESUME.replace("Built  the  ingestion  path", "Built the revised ingestion path")
    before = {r.normalized_locator: r for r in resume_records()}  # type: ignore[attr-defined]
    after = {r.normalized_locator: r for r in resume_records(edited)}  # type: ignore[attr-defined]
    assert set(before) == set(after)
    changed = [key for key in before if before[key] != after[key]]
    assert changed == ["entries/entry-one/bullets/bullet-one"]


# --------------------------------------------------------------------------------------
# structured-objects-v1 (§18.1)
# --------------------------------------------------------------------------------------


def structured_records(text: str) -> tuple[object, ...]:
    adapter = StructuredObjectsEnumerator(source_id=SOURCE)
    return adapter.enumerate(text.encode("utf-8"), scope=COMPLETE)


def test_a_root_mapping_sorts_rows_by_encoded_key() -> None:
    records = structured_records("zebra: last\nalpha: first\n")
    assert locators(records) == ["objects/alpha", "objects/zebra"]


def test_a_root_mapping_atomic_value_pairs_the_normalized_key_with_its_value() -> None:
    records = structured_records("alpha: first\n")
    assert records[0].atomic_value == {"key": "alpha", "value": "first"}  # type: ignore[attr-defined]


def test_a_root_mapping_value_may_be_a_nested_structure() -> None:
    records = structured_records("alpha:\n  nested:\n  - one\n  - two\n")
    assert records[0].atomic_value == {  # type: ignore[attr-defined]
        "key": "alpha",
        "value": {"nested": ["one", "two"]},
    }


def test_a_root_list_sorts_by_encoded_id_and_keeps_the_complete_element() -> None:
    records = structured_records(
        "- id: zebra\n  note: last\n- id: alpha\n  note: first\n"
    )
    assert locators(records) == ["objects/alpha", "objects/zebra"]
    assert records[0].atomic_value == {"id": "alpha", "note": "first"}  # type: ignore[attr-defined]


def test_a_structured_key_is_encoded_as_one_locator_segment() -> None:
    records = structured_records("'a/b': value\n")
    assert locators(records) == ["objects/a%2Fb"]


def test_a_source_violating_the_restricted_yaml_contract_is_refused() -> None:
    """The one restricted loader governs sources too: a duplicate key must not be read as its
    last spelling on the way in, or the record digest would depend on YAML 1.1's constructor."""
    with pytest.raises(EnumerationError):
        structured_records("alpha: one\nalpha: two\n")


def test_a_scalar_root_is_a_hard_error() -> None:
    with pytest.raises(EnumerationError):
        structured_records("just a string\n")


def test_an_empty_source_is_a_hard_error() -> None:
    with pytest.raises(EnumerationError):
        structured_records("")


def test_a_list_element_without_an_id_is_a_hard_error() -> None:
    with pytest.raises(EnumerationError):
        structured_records("- note: positional identity is refused\n")


def test_a_list_element_that_is_not_a_mapping_is_a_hard_error() -> None:
    with pytest.raises(EnumerationError):
        structured_records("- just a string\n")


def test_a_blank_list_element_id_is_a_hard_error() -> None:
    with pytest.raises(EnumerationError):
        structured_records("- id: '   '\n")


def test_a_blank_mapping_key_is_a_hard_error() -> None:
    with pytest.raises(EnumerationError):
        structured_records("'   ': value\n")


def test_duplicate_normalized_list_ids_are_a_hard_error() -> None:
    with pytest.raises(EnumerationError):
        structured_records("- id: alpha\n- id: alpha\n")


def test_keys_that_differ_only_by_unicode_form_are_a_duplicate() -> None:
    with pytest.raises(EnumerationError):
        structured_records('"caf\u00e9": one\n"cafe\u0301": two\n')


def test_structured_objects_accepts_json_because_json_is_restricted_yaml() -> None:
    records = structured_records('{"alpha": "first", "beta": "second"}')
    assert locators(records) == ["objects/alpha", "objects/beta"]


def test_structured_records_are_derived_and_reproducible() -> None:
    text = "zebra: last\nalpha: first\n"
    assert structured_records(text) == structured_records(text)
    for record in structured_records(text):
        assert record.source_record_id == expected_record_id(  # type: ignore[attr-defined]
            SOURCE, record.normalized_locator  # type: ignore[attr-defined]
        )


def test_the_structured_adapter_refuses_a_selected_sections_scope() -> None:
    with pytest.raises(EnumerationError):
        StructuredObjectsEnumerator(source_id=SOURCE).enumerate(
            b"alpha: first\n", scope=selected("anything")
        )


# --------------------------------------------------------------------------------------
# Review findings: locator canonicality and selected-scope matching
# --------------------------------------------------------------------------------------


def test_a_heading_containing_a_space_can_be_selected_by_its_resolved_path() -> None:
    """The resolved path of `# Alpha Beta` is `Alpha%20Beta`, and §18.1 says selected locators
    "refer to these resolved paths". Re-encoding one turns `%20` into `%2520` and leaves no valid
    import route for the overwhelming majority of real headings."""
    source = "# Alpha Beta\n\ntext\n"
    assert locators(markdown_records(source)) == ["Alpha%20Beta/heading", "Alpha%20Beta/paragraph-1"]
    selected_records = markdown_records(source, selected("Alpha%20Beta"))
    assert locators(selected_records) == ["Alpha%20Beta/heading", "Alpha%20Beta/paragraph-1"]


def test_a_unicode_heading_can_be_selected_by_its_resolved_path() -> None:
    source = "# Café\n\ntext\n"
    assert locators(markdown_records(source)) == ["Caf%C3%A9/heading", "Caf%C3%A9/paragraph-1"]
    assert locators(markdown_records(source, selected("Caf%C3%A9"))) == [
        "Caf%C3%A9/heading",
        "Caf%C3%A9/paragraph-1",
    ]


def test_a_heading_body_ending_in_a_tilde_suffix_can_be_selected() -> None:
    source = "# Alpha~2\n\ntext\n"
    resolved = locators(markdown_records(source))[0].removesuffix("/heading")
    assert locators(markdown_records(source, selected(resolved)))[0].endswith("/heading")


def test_a_raw_unencoded_scope_locator_is_refused_rather_than_silently_matching() -> None:
    """`Alpha Beta` is not a normalized locator, so it names no resolved heading path. Accepting
    it would make the invalid spelling the working one."""
    with pytest.raises(EnumerationError):
        markdown_records("# Alpha Beta\n\ntext\n", selected("Alpha Beta"))


@pytest.mark.parametrize(
    "text",
    [
        "%41",           # `A` is unreserved: no adapter ever escapes it
        "a%2Fb%2E",      # `.` is unreserved
        "%2d",           # lowercase hex is not what the encoder emits
        "%C3",           # a lone continuation byte is not valid UTF-8
        "%",
        "a%",
        "~2",            # a duplicate suffix with no body
    ],
)
def test_a_non_canonical_percent_escape_is_not_a_normalized_locator(text: str) -> None:
    assert not is_normalized_locator(text)


@pytest.mark.parametrize("text", ["a%20b", "%C3%A9", "Alpha%20Beta~2/heading", "_root"])
def test_a_canonically_encoded_locator_is_normalized(text: str) -> None:
    assert is_normalized_locator(text)


def test_every_locator_an_adapter_emits_is_recognised_as_normalized() -> None:
    """The predicate and the encoder must agree, or validation rejects real ledgers."""
    source = "# Alpha Beta\n\n- a bullet\n\n## Café Détails\n\ntext\n\n# Alpha Beta\n\nmore\n"
    for record in markdown_records(source):
        assert is_normalized_locator(record.normalized_locator)  # type: ignore[attr-defined]
    for record in resume_records():
        assert is_normalized_locator(record.normalized_locator)  # type: ignore[attr-defined]
    for record in structured_records("'a/b c': value\n"):
        assert is_normalized_locator(record.normalized_locator)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------
# Review findings: résumé ID uniqueness is decided on the normalized form
# --------------------------------------------------------------------------------------


def test_entry_ids_differing_only_by_surrounding_whitespace_are_one_id() -> None:
    """`e` and `" e "` encode to the same locator segment and therefore derive the same
    source-record ID. Refusing them late, at the ledger model, still lets the adapter hand
    extraction an immutable package containing two records with one identity."""
    duplicated = RESUME.replace(
        "extracurricular:",
        "- entry_id: ' entry-one '\n  heading: Other\n  bullets: []\nextracurricular:",
    )
    with pytest.raises(EnumerationError):
        resume_records(duplicated)


def test_bullet_ids_differing_only_by_surrounding_whitespace_are_one_id() -> None:
    duplicated = RESUME.replace(
        "extracurricular:",
        "- entry_id: entry-two\n  heading: Other\n  bullets:\n"
        "  - bullet_id: ' bullet-one '\n    text: Another\nextracurricular:",
    )
    with pytest.raises(EnumerationError):
        resume_records(duplicated)


# --------------------------------------------------------------------------------------
# Review finding: determinism across interpreter hash seeds
# --------------------------------------------------------------------------------------

_HASH_SEED_SCRIPT = """
from boardwatch.profile_bundle.enumerators import MarkdownBlocksEnumerator, StructuredObjectsEnumerator
from boardwatch.profile_bundle.models.imports import CompleteFileScope

scope = CompleteFileScope(kind="complete_file")
markdown = MarkdownBlocksEnumerator(source_id="source.synthetic-example")
text = b"# Beta\\n\\nb\\n\\n# Alpha\\n\\n- one\\n- two\\n\\n# Beta\\n\\nc\\n"
for record in markdown.enumerate(text, scope=scope):
    print(record.normalized_locator, record.record_content_digest)
structured = StructuredObjectsEnumerator(source_id="source.synthetic-example")
rows = b"zebra: z\\nalpha: a\\nmiddle: m\\ndelta: d\\nomega: o\\n"
for record in structured.enumerate(rows, scope=scope):
    print(record.normalized_locator, record.record_content_digest)
"""


def test_enumeration_is_identical_across_interpreter_hash_seeds() -> None:
    """Re-running inside one interpreter cannot see hash-seed-dependent set iteration: the seed is
    fixed for the process, so an adapter that iterated a set would still look deterministic."""
    import os
    import subprocess
    import sys

    def run(seed: str) -> str:
        environment = {**os.environ, "PYTHONHASHSEED": seed}
        finished = subprocess.run(
            [sys.executable, "-c", _HASH_SEED_SCRIPT],
            capture_output=True,
            text=True,
            check=True,
            env=environment,
        )
        return finished.stdout

    first = run("1")
    assert first == run("2") == run("0")
    assert first.strip(), "the probe produced no records"


# --------------------------------------------------------------------------------------
# Verification finding: the round trip must include the encoder's own NFC and trim
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("alternate", "canonical"),
    [
        ("e%CC%81", "%C3%A9"),   # decomposed: the encoder NFC-normalises first
        ("%20a", "a"),            # leading space: the encoder trims first
        ("a%20", "a"),            # trailing space
        ("%E2%80%82x", "x"),      # EN SPACE is Unicode whitespace and is trimmed
    ],
)
def test_only_the_encoders_own_spelling_is_a_normalized_locator(
    alternate: str, canonical: str
) -> None:
    """`encode_locator_segment` NFC-normalises and trims *before* encoding, so these alternates
    are spellings it can never emit. Accepting them lets two locators stand for one heading, and
    each derives its own source-record ID — the Gate B denominator inflates with no finding."""
    adapter = markdown_adapter()
    assert encode_locator_segment(_decoded_for(alternate), adapter=adapter) == canonical
    assert is_normalized_locator(canonical)
    assert not is_normalized_locator(alternate)


def _decoded_for(segment: str) -> str:
    from boardwatch.profile_bundle.enumerators import _decoded_segment

    decoded = _decoded_segment(segment)
    assert decoded is not None
    return decoded


def test_a_normalized_locator_is_exactly_what_the_encoder_emits_for_its_own_text() -> None:
    """The property behind the predicate, stated directly over many texts."""
    adapter = markdown_adapter()
    for raw in [
        "Alpha Beta", "café", "café", " padded ", "100% Done", "a/b", "Ship it 🚀",
        "tilde~here", "dot.", "under_score", "CAPS", "  ", "x",
    ]:
        try:
            encoded = encode_locator_segment(raw, adapter=adapter)
        except EnumerationError:
            continue
        assert is_normalized_locator(encoded), raw

# --------------------------------------------------------------------------------------
# emits_locator: every adapter's byte-free locator grammar (§18.1)
# --------------------------------------------------------------------------------------


def test_every_locator_the_resume_adapter_emits_satisfies_its_own_grammar() -> None:
    """The grammar is derived from the emitter, not written alongside it.

    Asserting the predicate accepts hand-picked good spellings would only prove the predicate
    agrees with whoever wrote the test. Enumerating a real source and requiring the predicate to
    accept every locator that came out means a new emission stage cannot be added without either
    updating the grammar or turning this red.
    """
    adapter = BoardwatchResumeEnumerator(source_id=SOURCE)
    emitted = locators(resume_records())
    assert emitted
    assert [one for one in emitted if not adapter.emits_locator(one)] == []


def test_every_locator_the_markdown_adapter_emits_satisfies_its_own_grammar() -> None:
    adapter = markdown_adapter()
    emitted = locators(markdown_records())
    assert emitted
    assert [one for one in emitted if not adapter.emits_locator(one)] == []


def test_every_locator_the_structured_adapter_emits_satisfies_its_own_grammar() -> None:
    adapter = StructuredObjectsEnumerator(source_id=SOURCE)
    emitted = locators(structured_records('{"alpha": 1, "beta": 2}'))
    assert emitted
    assert [one for one in emitted if not adapter.emits_locator(one)] == []


@pytest.mark.parametrize(
    "locator",
    [
        "header",
        "header/1/extra",
        "header/0",
        "header/01",
        "title/1",
        "skill-groups/languages",
        "skill-groups/languages/0",
        "entries/entry.one",
        "entries/entry.one/bullets",
        "entries/entry.one/metadata/extra",
        "objects/alpha",
        "Overview/heading",
        "",
    ],
)
def test_a_shape_the_resume_adapter_never_emits_is_refused(locator: str) -> None:
    assert not BoardwatchResumeEnumerator(source_id=SOURCE).emits_locator(locator)


@pytest.mark.parametrize(
    "locator",
    [
        "heading",
        "Overview/sidebar-1",
        "Overview/paragraph",
        "Overview/paragraph-0",
        "Overview/paragraph-01",
        "Overview/paragraph-1x",
        "Overview/paragraph-\N{SUPERSCRIPT ONE}",
        "objects/alpha",
        "",
    ],
)
def test_a_shape_the_markdown_adapter_never_emits_is_refused(locator: str) -> None:
    assert not markdown_adapter().emits_locator(locator)


@pytest.mark.parametrize(
    "locator",
    ["alpha", "objects", "objects/alpha/beta", "Overview/heading", ""],
)
def test_a_shape_the_structured_adapter_never_emits_is_refused(locator: str) -> None:
    assert not StructuredObjectsEnumerator(source_id=SOURCE).emits_locator(locator)


# --------------------------------------------------------------------------------------
# Round-3 review findings: the grammar reads the emitter's constants (§18.1)
# --------------------------------------------------------------------------------------

ROOT_COLLISION = "Intro before any heading.\n\n# _root\n\nInside the heading.\n"


def test_a_heading_named_root_does_not_share_a_namespace_with_pre_heading_content() -> None:
    """`_root` is the adapter's own synthetic segment, so the encoder may never produce it.

    `_` is unreserved, so `encode_locator_segment("_root")` used to return `_root` unchanged and
    two different logical sections collapsed onto one namespace — pre-heading content and a
    heading literally named `_root` derived the same record IDs.
    """
    assert locators(markdown_records(ROOT_COLLISION)) == [
        "_root/paragraph-1",
        "%5Froot/heading",
        "%5Froot/paragraph-1",
    ]


def test_a_heading_named_root_can_be_selected_by_its_resolved_path() -> None:
    """The round-one defect class: a legitimate Markdown source made unimportable by a rule."""
    assert locators(markdown_records(ROOT_COLLISION, selected("%5Froot"))) == [
        "%5Froot/heading",
        "%5Froot/paragraph-1",
    ]


@pytest.mark.parametrize("raw", ["_root", " _root ", "_root ".strip()])
def test_the_encoder_never_emits_a_reserved_segment(raw: str) -> None:
    assert encode_locator_segment(raw, adapter=markdown_adapter()) == "%5Froot"


def test_the_reserved_segment_round_trips_but_its_escaped_spelling_is_the_encoders() -> None:
    assert is_normalized_locator("_root/paragraph-1")
    assert is_normalized_locator("%5Froot/heading")
    assert not is_normalized_locator("_root~2")


def test_root_is_a_locator_shape_only_for_pre_heading_blocks() -> None:
    adapter = markdown_adapter()
    assert adapter.emits_locator("_root/paragraph-1")
    assert not adapter.emits_locator("_root/heading")
    assert not adapter.emits_locator("Overview/_root/paragraph-1")


def test_six_hashes_open_a_heading_and_seven_do_not() -> None:
    """The cap is CommonMark's, stated against real enumeration rather than against the constant.

    Mutating `_MAX_HEADING_LEVEL` to 5 survived a first round of mutation testing: every assertion
    about the cap read the same constant it was checking, so the constant and the tests agreed with
    each other while both disagreed with Markdown. This one enumerates instead.
    """
    assert locators(markdown_records("###### Six\n\ntext\n")) == ["Six/heading", "Six/paragraph-1"]
    assert locators(markdown_records("####### Seven\n\ntext\n")) == [
        "_root/paragraph-1",
        "_root/paragraph-2",
    ]


def test_the_grammars_depth_cap_is_the_heading_regexs_own_cap() -> None:
    """Restating "six levels" in a second place is what let a seven-level forgery validate."""
    assert _HEADING_RE.match("#" * _MAX_HEADING_LEVEL + " deepest") is not None
    assert _HEADING_RE.match("#" * (_MAX_HEADING_LEVEL + 1) + " deeper") is None


def test_a_heading_path_deeper_than_markdown_can_nest_is_refused() -> None:
    adapter = markdown_adapter()
    deepest = "/".join(f"h{level}" for level in range(1, _MAX_HEADING_LEVEL + 1))
    assert adapter.emits_locator(f"{deepest}/heading")
    assert adapter.emits_locator(f"{deepest}/paragraph-1")
    assert not adapter.emits_locator(f"{deepest}/overflow/heading")
    assert not adapter.emits_locator(f"{deepest}/overflow/paragraph-1")


def test_the_deepest_real_enumeration_still_satisfies_the_grammar() -> None:
    """The cap must be exactly the emitter's, not one level short of it."""
    source = "\n\n".join(f"{'#' * level} H{level}" for level in range(1, _MAX_HEADING_LEVEL + 1))
    adapter = markdown_adapter()
    emitted = locators(markdown_records(source + "\n\ndeepest paragraph\n"))
    assert max(one.count("/") for one in emitted) == _MAX_HEADING_LEVEL
    assert [one for one in emitted if not adapter.emits_locator(one)] == []


@pytest.mark.parametrize(
    ("locator", "accepted"),
    [
        ("Overview~2/paragraph-1", True),
        ("Overview/Details~3/paragraph-1", True),
        ("Overview~2/heading", True),
        ("Overview/paragraph~2-1", False),
        ("Overview~1/paragraph-1", False),
    ],
)
def test_a_duplicate_suffix_is_meaningful_only_on_a_markdown_heading_segment(
    locator: str, accepted: bool
) -> None:
    assert markdown_adapter().emits_locator(locator) is accepted


def test_the_structured_adapter_refuses_a_raw_duplicate_suffix_it_can_only_escape() -> None:
    """`synthetic~2` is a normalized locator — the predicate is adapter-blind on purpose, because
    an owner writes resolved heading paths into a selected scope. The structured adapter has no
    duplicate rule at all: it encodes every key, so `~` can only ever reach a locator as `%7E`."""
    adapter = StructuredObjectsEnumerator(source_id=SOURCE)
    assert encode_locator_segment("synthetic~2", adapter=adapter) == "synthetic%7E2"
    assert is_normalized_locator("objects/synthetic~2")
    assert not adapter.emits_locator("objects/synthetic~2")
    assert adapter.emits_locator("objects/synthetic%7E2")


@pytest.mark.parametrize(
    "locator",
    [
        "entries/entry~2/metadata",
        "entries/entry-one/bullets/bullet~2",
        "skill-groups/Languages~2/1",
        "entries/entry one/metadata",
        "skill-groups/Alpha%20Beta~2/1",
    ],
)
def test_the_resume_adapter_refuses_a_segment_its_encoder_could_not_have_written(
    locator: str,
) -> None:
    assert not BoardwatchResumeEnumerator(source_id=SOURCE).emits_locator(locator)


def test_a_resume_identifier_containing_a_tilde_is_emitted_escaped_and_accepted() -> None:
    tilde = RESUME.replace("entry_id: entry-one", "entry_id: entry~2")
    adapter = BoardwatchResumeEnumerator(source_id=SOURCE)
    emitted = locators(resume_records(tilde))
    assert "entries/entry%7E2/metadata" in emitted
    assert [one for one in emitted if not adapter.emits_locator(one)] == []


def test_a_structured_key_containing_a_tilde_is_emitted_escaped_and_accepted() -> None:
    adapter = StructuredObjectsEnumerator(source_id=SOURCE)
    emitted = locators(structured_records("'synthetic~2': value\n"))
    assert emitted == ["objects/synthetic%7E2"]
    assert [one for one in emitted if not adapter.emits_locator(one)] == []


def test_every_adversarial_source_emits_only_locators_its_own_grammar_accepts() -> None:
    """The property the previous two rounds tested only over what the fixtures happened to hold.

    Each source here carries something no earlier fixture did: a maximal heading nest, a heading
    named `_root`, a heading body ending in `~2`, a percent sign, and non-BMP text.
    """
    adapter = markdown_adapter()
    sources = [
        "\n\n".join(f"{'#' * level} Level {level}" for level in range(1, _MAX_HEADING_LEVEL + 1)),
        ROOT_COLLISION,
        "# Alpha~2\n\ntext\n\n# Alpha~2\n\nmore\n",
        "# 100% Done\n\ntext\n",
        "# Ship it \N{ROCKET}\n\ntext\n",
        "no heading at all\n\n- a bullet\n",
    ]
    for source in sources:
        emitted = locators(markdown_records(source))
        assert emitted, source
        assert [one for one in emitted if not adapter.emits_locator(one)] == [], source
        assert [one for one in emitted if not is_normalized_locator(one)] == [], source
