"""Tests for `boardwatch.delivery.names` (design §4.1).

Every byte count here is computed from the literal destination shape
`<root>/_skipped/<folder>/<pdf>` rather than by calling the module's own helpers, so the
budget is counted through a different path than the one that produced it.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from boardwatch.delivery.names import (
    COMPONENT_BYTE_CAP,
    DESTINATION_BYTE_CAP,
    DRAIN_DIRS,
    PDF_SUFFIX,
    RESERVED_DEVICE_NAMES,
    RESUME_NAME_BYTE_CAP,
    LeadNames,
    NameBudgetError,
    ResumeNaming,
    plan_lead_names,
    plan_resume_naming,
    slug,
)

IDENTITY = "9f2b1c0d4e5a6b7c8d9e0f1a2b3c4d5e"
OTHER_IDENTITY = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"
OWNER = "Ada Lovelace"  # slugs to 12 bytes
OWNER_SLUG = "Ada_Lovelace"
COMPANY = "Acme"  # slugs to 4 bytes
#: `_component`'s fallback stem for a blank part, digested here rather than by calling the
#: module's own `_short_hash` — an assertion against the shared helper would be vacuous.
PLAN_FALLBACK = hashlib.sha256(IDENTITY.encode("utf-8")).hexdigest()[:8]
SHORT_ROOT = Path("/q")


def blen(text: str) -> int:
    return len(text.encode("utf-8"))


def destination_bytes(root: Path, names: LeadNames) -> int:
    """Bytes of the longest final destination, spelled out rather than delegated.

    The drain is taken as the LONGEST of `DRAIN_DIRS`, which is what `_prefix_bytes` prices the
    budget against. This said `_skipped` — a hardcoded 8-byte drain — so once the 11-byte
    `_ineligible` existed the helper measured a destination 3 bytes shorter than the one the cap
    is about, and every assertion built on it was measuring the wrong path.
    """
    return blen(f"{root}/{max(DRAIN_DIRS, key=len)}/{names.folder}/{names.pdf}")


def plan(
    title: str,
    *,
    root: Path = SHORT_ROOT,
    company: str = COMPANY,
    owner_name: str = OWNER,
    identity_hash: str = IDENTITY,
) -> LeadNames:
    return plan_lead_names(
        root=root,
        owner_name=owner_name,
        company=company,
        title=title,
        identity_hash=identity_hash,
    )


def assert_within_budget(root: Path, names: LeadNames) -> None:
    assert blen(names.folder) <= COMPONENT_BYTE_CAP
    assert blen(names.pdf) <= COMPONENT_BYTE_CAP
    assert destination_bytes(root, names) <= DESTINATION_BYTE_CAP
    # A component, not a path: nothing here may introduce a directory level.
    assert Path(names.folder).name == names.folder
    assert Path(names.pdf).name == names.pdf
    for part in (names.folder, names.pdf):
        assert "�" not in part, "a byte-level cut split a character"
        assert "__" not in part and not part.startswith("_") and not part.endswith("_")


def title_body(names: LeadNames) -> str:
    """The folder's title component: everything after the company, minus a hash suffix."""
    return names.folder.removeprefix(f"{COMPANY}_")


# --------------------------------------------------------------------------------------
# The caps are the numbers §4.1 states, not whatever the module happens to hold
# --------------------------------------------------------------------------------------


def test_caps_are_the_documented_byte_numbers() -> None:
    assert (COMPONENT_BYTE_CAP, DESTINATION_BYTE_CAP) == (200, 240)


# --------------------------------------------------------------------------------------
# slug: collapsing, stripping, normalising, preserving
# --------------------------------------------------------------------------------------


def test_slug_collapses_whitespace_and_punctuation_runs_to_one_underscore() -> None:
    assert slug("Senior   Software  ---  Engineer!!!") == "Senior_Software_Engineer"
    assert slug("Backend  (Rust)  --  L4") == "Backend_Rust_L4"


def test_slug_replaces_the_windows_illegal_set_and_control_characters() -> None:
    # Replaced, not deleted: `Backend/Infra` must read as two words, not as `BackendInfra`.
    assert slug('R&D / Ops: "Lead" <x>|y?z*') == "R_D_Ops_Lead_x_y_z"
    assert slug("Data\x00Eng\x1fRole\t2\n") == "Data_Eng_Role_2"
    for illegal in '<>:"/\\|?*':
        assert illegal not in slug(f"a{illegal}b")
        assert slug(f"a{illegal}b") == "a_b"


def test_slug_strips_leading_and_trailing_dots_and_spaces() -> None:
    for value in ("  ..Staff Engineer.. ", ".Staff Engineer.", " Staff Engineer "):
        result = slug(value)
        assert result == "Staff_Engineer"
        assert not result.startswith((".", " ", "_"))
        assert not result.endswith((".", " ", "_"))


def test_slug_nfc_normalises_before_anything_else() -> None:
    # Built with NFD rather than typed as a literal: a literal is only as trustworthy as
    # this file's own encoding, and a re-encode would leave the test comparing NFC to NFC.
    composed = unicodedata.normalize("NFC", "Ingénieur")
    decomposed = unicodedata.normalize("NFD", composed)  # e + COMBINING ACUTE
    assert decomposed != composed and len(decomposed) == 10
    assert slug(decomposed) == slug(composed) == composed
    assert len(slug(decomposed)) == 9  # 10 if the combining mark survived un-composed
    assert unicodedata.is_normalized("NFC", slug(decomposed))


def test_slug_preserves_non_ascii_letters() -> None:
    assert slug("Ingénieur Logiciel (Débutant)") == "Ingénieur_Logiciel_Débutant"
    assert slug("ソフトウェア エンジニア") == "ソフトウェア_エンジニア"
    assert slug("ソフトウェア　エンジニア") == "ソフトウェア_エンジニア"  # ideographic space
    assert slug("Программист") == "Программист"


def test_slug_returns_empty_for_a_value_with_no_usable_characters() -> None:
    for value in ("", "!!! ---   ***", "   ", "...", "<<>>||??**", "\x00\x01"):
        assert slug(value) == ""


# --------------------------------------------------------------------------------------
# slug: the Windows reserved device names
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("reserved", sorted(RESERVED_DEVICE_NAMES))
def test_slug_rejects_every_reserved_device_name_in_any_case(reserved: str) -> None:
    assert slug(reserved) == ""
    assert slug(reserved.lower()) == ""
    assert slug(reserved.capitalize()) == ""
    assert slug(f"  {reserved}. ") == "", "a trailing dot or space still leaves the device name"


def test_the_reserved_catalog_is_the_documented_closed_set() -> None:
    expected = {"CON", "PRN", "AUX", "NUL"}
    expected |= {f"COM{n}" for n in range(1, 10)}
    expected |= {f"LPT{n}" for n in range(1, 10)}
    assert RESERVED_DEVICE_NAMES == expected


def test_a_reserved_name_with_an_extension_never_survives_as_one() -> None:
    # Windows rejects `CON.txt` as well as `CON`, and it keys on the stem -- everything up
    # to the first dot. No dot survives slugging, so the stem is the whole result, and that
    # is what must never be a device name. `CON_txt` and `LPT1_DOC` are ordinary names.
    for value in ("CON.txt", "con.pdf", "AUX.", "lpt1.doc", "COM4.tar.gz"):
        result = slug(value)
        assert "." not in result
        assert result.upper() not in RESERVED_DEVICE_NAMES
    assert slug("CON.txt") == "CON_txt"
    assert slug("AUX.") == ""


def test_slug_does_not_over_reject_names_that_merely_start_with_a_device_name() -> None:
    for value in ("CONSOLE", "AUXILIARY", "PRNT", "COM10", "COM0", "NULL", "LPT10"):
        assert slug(value) == value


# --------------------------------------------------------------------------------------
# The empty fallback
# --------------------------------------------------------------------------------------


def test_a_punctuation_only_title_falls_back_to_posting_hash() -> None:
    names = plan("!!! ---   ***")
    assert re.fullmatch(r"Acme_posting_[0-9a-f]{8}", names.folder), names.folder
    assert re.fullmatch(r"Ada_Lovelace_Acme_posting_[0-9a-f]{8}\.pdf", names.pdf), names.pdf
    assert "" not in names.folder.split("_")
    assert_within_budget(SHORT_ROOT, names)


def test_a_company_named_aux_dot_falls_back_and_never_yields_a_device_name() -> None:
    names = plan("Software Engineer", company="AUX.")
    assert re.fullmatch(r"posting_[0-9a-f]{8}_Software_Engineer", names.folder), names.folder
    assert "AUX" not in names.folder.upper().split("_")
    assert "" not in names.folder.split("_")
    assert_within_budget(SHORT_ROOT, names)


def test_a_title_of_exactly_con_falls_back_and_never_yields_a_device_name() -> None:
    names = plan("CON")
    assert re.fullmatch(r"Acme_posting_[0-9a-f]{8}", names.folder), names.folder
    assert "CON" not in names.folder.upper().split("_")
    stem = names.pdf.upper().removesuffix(".PDF")
    assert stem not in RESERVED_DEVICE_NAMES and "CON" not in stem.split("_")
    assert_within_budget(SHORT_ROOT, names)


def test_the_fallback_is_keyed_on_the_posting_identity() -> None:
    mine = plan("***")
    theirs = plan("***", identity_hash=OTHER_IDENTITY)
    assert mine.folder != theirs.folder
    assert mine.folder == plan("***").folder


# --------------------------------------------------------------------------------------
# The byte budget, taken against the longest final destination
# --------------------------------------------------------------------------------------


def test_a_four_hundred_character_japanese_title_fits_the_byte_budget() -> None:
    title = "エ" * 400  # 400 characters, 1,200 UTF-8 bytes
    assert blen(title) == 1200
    for root in (SHORT_ROOT, Path("/queue/of/leads"), Path("/q/" + "x" * 20)):
        names = plan(title, root=root)
        assert_within_budget(root, names)
        head, _, suffix = title_body(names).rpartition("_")
        assert set(head) == {"エ"}, f"the retained title is not whole characters: {head!r}"
        assert re.fullmatch(r"[0-9a-f]{8}", suffix), names.folder


@pytest.mark.parametrize("characters", [40, 60])
def test_the_budget_is_bytes_not_characters(characters: int) -> None:
    """The fixture has to sit where a character count still *looks* affordable.

    A 400-character title is over any cap either way, and the cut itself is made in bytes,
    so counting characters and then cutting bytes accidentally lands inside the budget. At
    40 and 60 Japanese characters a character count sees room -- 40 and 60 against a cap of
    200 -- while the real cost is 120 and 180 bytes, which overruns the destination and, at
    60, the PDF name's own cap too.
    """
    names = plan("エ" * characters)
    assert len(names.folder) < COMPONENT_BYTE_CAP, "characters alone were never the problem"
    assert blen(names.folder) <= COMPONENT_BYTE_CAP
    assert blen(names.pdf) <= COMPONENT_BYTE_CAP
    assert destination_bytes(SHORT_ROOT, names) <= DESTINATION_BYTE_CAP


def test_the_budget_is_taken_against_the_destination_not_the_component_cap() -> None:
    names = plan("S" * 300)
    # Both names are far below 200 bytes: what bound them is the whole destination path.
    assert blen(names.folder) < COMPONENT_BYTE_CAP
    assert blen(names.pdf) < COMPONENT_BYTE_CAP
    assert destination_bytes(SHORT_ROOT, names) <= DESTINATION_BYTE_CAP
    assert destination_bytes(SHORT_ROOT, names) > DESTINATION_BYTE_CAP - 4, (
        "the budget should be spent, not left on the table"
    )


def test_a_longer_root_leaves_less_room_for_the_title() -> None:
    short = plan("S" * 300, root=Path("/q"))
    longer = plan("S" * 300, root=Path("/q/" + "x" * 40))
    assert blen(longer.folder) < blen(short.folder)
    assert destination_bytes(Path("/q/" + "x" * 40), longer) <= DESTINATION_BYTE_CAP


def test_a_name_legal_in_the_queue_is_still_legal_after_it_drains() -> None:
    """Every drain, taken from `DRAIN_DIRS` rather than a literal pair.

    The literal went stale the moment a third drain was added: `_ineligible` is 11 bytes against
    the others' 8, so the budget was under-priced by 3 and this test could not see it. Iterating
    the constant the budget itself is computed from is what makes the two impossible to diverge.
    """
    root = Path("/q/" + "x" * 40)
    names = plan("S" * 300, root=root)
    assert len(DRAIN_DIRS) >= 3, "premise: the loop must cover more than the original pair"
    for drain in DRAIN_DIRS:
        assert blen(f"{root}/{drain}/{names.folder}/{names.pdf}") <= DESTINATION_BYTE_CAP


def test_the_budget_is_priced_against_the_longest_drain() -> None:
    """The specific defect: pricing against `_applied` (8 bytes) while `_ineligible` (11) exists
    means `NameBudgetError` accepts names whose drained destination it promised to refuse."""
    longest = max(DRAIN_DIRS, key=len)
    root = Path("/" + "d" * 181)
    names = plan("S" * 300, root=root)
    assert blen(f"{root}/{longest}/{names.folder}/{names.pdf}") <= DESTINATION_BYTE_CAP


def test_a_root_that_leaves_no_room_at_all_is_refused_before_anything_is_created() -> None:
    root = Path("/" + "d" * 199)
    assert blen(str(root)) == 200
    with pytest.raises(NameBudgetError) as raised:
        plan("Software Engineer", root=root)
    assert "too long" in str(raised.value)
    assert str(DESTINATION_BYTE_CAP) in str(raised.value)


def test_the_longest_root_that_still_fits_spends_the_budget_exactly() -> None:
    # 183 bytes of root + "/_ineligible/" (13) = 196, and the shortest names the cascade can
    # produce for a 4-byte company and a 12-byte owner are 11 + 1 + 32 = 44 bytes. 196 + 44 is
    # exactly the cap. The arithmetic moved when `_ineligible` joined `DRAIN_DIRS`: the budget is
    # priced against the LONGEST drain, so a third drain 3 bytes longer than the original pair
    # tightens every planned name by 3. That is the whole point of pricing against the longest --
    # a name legal in the queue has to stay legal in whichever drain it ends up in.
    root = Path("/" + "d" * 182)
    assert blen(str(root)) == 183
    names = plan("S" * 300, root=root)
    assert destination_bytes(root, names) == DESTINATION_BYTE_CAP
    assert_within_budget(root, names)


# --------------------------------------------------------------------------------------
# Truncation: boundaries, and the suffix that stops two long titles colliding
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("padding", range(12))
def test_truncation_never_splits_a_combining_sequence(padding: int) -> None:
    # Devanagari KA + VOWEL SIGN I: one grapheme, two codepoints, six bytes, and NFC does
    # not compose them -- so a cut can land between the base and its mark.
    pair = "कि"
    title = pair * 200
    assert unicodedata.normalize("NFC", title) == title
    assert unicodedata.category(title[1]).startswith("M")
    root = Path("/q" + "x" * padding)  # shifts the cut through every byte offset
    names = plan(title, root=root)
    head, _, suffix = title_body(names).rpartition("_")
    assert re.fullmatch(r"[0-9a-f]{8}", suffix), names.folder
    assert head, "the title was truncated away entirely"
    assert head == pair * (len(head) // 2), f"a combining mark was orphaned: {head!r}"
    assert_within_budget(root, names)


def test_two_long_titles_sharing_their_first_bytes_do_not_collide() -> None:
    shared = "S" * 200
    first = shared + "A" * 100
    second = shared + "B" * 100
    assert first[:200].encode() == second[:200].encode() and first != second

    # The hard case is one posting whose title was edited: the identity is the same, so a
    # suffix keyed on the identity alone would be the same too.
    same = plan(first)
    also_same = plan(second)
    assert same.folder != also_same.folder
    assert same.pdf != also_same.pdf
    # Everything except the suffix is identical, which is what makes the suffix load-bearing.
    assert same.folder.rpartition("_")[0] == also_same.folder.rpartition("_")[0]

    across = plan(first, identity_hash=OTHER_IDENTITY)
    assert across.folder != same.folder
    for names in (same, also_same, across):
        assert_within_budget(SHORT_ROOT, names)


def test_an_untruncated_title_carries_no_hash_suffix() -> None:
    names = plan("Software Engineer, Compilers")
    assert names.folder == "Acme_Software_Engineer_Compilers"
    assert names.pdf == "Ada_Lovelace_Acme_Software_Engineer_Compilers.pdf"


# --------------------------------------------------------------------------------------
# The owner's name comes from the profile
# --------------------------------------------------------------------------------------


def test_the_pdf_name_comes_from_the_owner_and_the_folder_does_not() -> None:
    mine = plan("Software Engineer")
    theirs = plan("Software Engineer", owner_name="Grace Hopper")
    assert mine.folder == theirs.folder == "Acme_Software_Engineer"
    assert mine.pdf == f"{OWNER_SLUG}_Acme_Software_Engineer.pdf"
    assert theirs.pdf == "Grace_Hopper_Acme_Software_Engineer.pdf"


def test_an_absurd_owner_name_is_absorbed_without_an_empty_component() -> None:
    # The stated order is title first, then company, then owner, and the destination cap is
    # shared -- so a 404-byte owner does cost the title, which collapses to its hash floor.
    # That is the price of the order, not a defect; what must hold is that every component
    # survives and both caps do.
    names = plan("Software Engineer", owner_name="Ada " + "L" * 400)
    assert_within_budget(SHORT_ROOT, names)
    assert re.fullmatch(r"Acme_[0-9a-f]{8}", names.folder), names.folder
    assert blen(names.pdf) == COMPONENT_BYTE_CAP, "the owner is trimmed to the cap, not past it"
    assert names.pdf.startswith("Ada_L")


# --------------------------------------------------------------------------------------
# Purity and determinism
# --------------------------------------------------------------------------------------


_ALLOWED_IMPORTS = frozenset({"__future__", "dataclasses", "hashlib", "pathlib", "re", "unicodedata"})


def test_the_module_imports_nothing_but_those_six_standard_library_modules() -> None:
    """A store import, a clock or an `os` call would make the planner unreproducible."""
    from boardwatch.delivery import names as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert imported <= _ALLOWED_IMPORTS, f"unexpected imports: {sorted(imported - _ALLOWED_IMPORTS)}"


def test_planning_touches_no_filesystem(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("plan_lead_names reached the filesystem")

    for attribute in ("exists", "stat", "iterdir", "open", "resolve", "is_dir"):
        monkeypatch.setattr(Path, attribute, forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    try:
        names = plan("Software Engineer", root=Path("/does/not/exist/anywhere"))
    finally:
        # Undone before asserting: pytest reads files to build a failure report, so leaving
        # the patch up turns any failure here into an INTERNALERROR that aborts the session.
        monkeypatch.undo()
    assert names.folder == "Acme_Software_Engineer"


# Deliberately ASCII on the way in and on the way out: a non-ASCII argv or a non-ASCII
# stdout would make this probe fail on a Windows code page for a reason of its own.
_SEED_SCRIPT = r"""
from pathlib import Path
from boardwatch.delivery.names import plan_lead_names

for title in ("Software Engineer", "\u30a8" * 400, "!!!", "S" * 300, "\u0915\u093f" * 200):
    names = plan_lead_names(
        root=Path("/q"),
        owner_name="Ada Lovelace",
        company="Acme",
        title=title,
        identity_hash="9f2b1c0d4e5a6b7c8d9e0f1a2b3c4d5e",
    )
    print((names.folder + " " + names.pdf).encode("unicode_escape").decode("ascii"))
"""


def test_names_are_identical_across_interpreter_hash_seeds() -> None:
    """Re-calling inside one interpreter cannot see a `hash()`-derived suffix: the salt is
    fixed for the life of the process, so a salted digest still looks deterministic."""

    def run(seed: str) -> str:
        finished = subprocess.run(
            [sys.executable, "-c", _SEED_SCRIPT],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        return finished.stdout

    first = run("1")
    assert first == run("2") == run("0")
    assert first.strip(), "the probe produced no names"


def test_plan_lead_names_is_deterministic_and_frozen() -> None:
    first = plan("Software Engineer, Compilers")
    assert first == plan("Software Engineer, Compilers")
    with pytest.raises(AttributeError):
        first.folder = "other"  # type: ignore[misc]


# --------------------------------------------------------------------------------------
# The delivered résumé's own name and PDF metadata
# --------------------------------------------------------------------------------------


ROLE = "Software Engineer"


def naming(
    *,
    owner_name: str = OWNER,
    company: str = COMPANY,
    role: str = ROLE,
    identity_hash: str = IDENTITY,
    variant: str = "",
) -> ResumeNaming:
    return plan_resume_naming(
        owner_name=owner_name,
        company=company,
        role=role,
        identity_hash=identity_hash,
        variant=variant,
    )


def test_the_resume_is_named_owner_company_role_and_the_metadata_agrees_with_it() -> None:
    """The owner's chosen format, all three layers at once: an underscored filename, a
    spaced-hyphen PDF title that reads role-then-company, and the owner as PDF author."""
    planned = naming()
    assert f"{planned.stem}{PDF_SUFFIX}" == "Ada_Lovelace_Acme_Software_Engineer.pdf"
    assert planned.pdf_title == "Ada Lovelace - Software Engineer - Acme"
    assert planned.pdf_author == "Ada Lovelace"


def test_the_metadata_keeps_the_original_text_the_filename_had_to_slug() -> None:
    """PDF /Info is free text, so the punctuation and accents the filename loses survive there.
    Without this the title would read the slug back at the owner."""
    planned = naming(company="Nestlé & Co.", role="Backend Engineer (Remote)")
    assert planned.pdf_title == "Ada Lovelace - Backend Engineer (Remote) - Nestlé & Co."
    assert planned.stem == "Ada_Lovelace_Nestlé_Co_Backend_Engineer_Remote"


def test_the_role_gives_way_first_the_company_second_and_the_owner_never() -> None:
    """The cap is on the company and the role. A recruiter reading the file in an upload
    dialog has to see whose résumé it is, so the owner's name is the one component that is
    never cut — measured here by requiring it whole while both others are shortened."""
    company = "Connexxion Telecoms Group International Holdings"
    role = "Staff Software Development Engineer, Platform Infrastructure"
    planned = naming(company=company, role=role)
    filename = f"{planned.stem}{PDF_SUFFIX}"

    assert blen(filename) <= RESUME_NAME_BYTE_CAP, filename
    assert filename.startswith(f"{OWNER_SLUG}_"), "the owner's name was cut"
    tail = planned.stem[len(OWNER_SLUG) + 1 :]
    assert blen(tail) < blen(slug(company)) + 1 + blen(slug(role)), "nothing was truncated"
    # Both survivors keep a hash suffix, so two long roles at one company never collide.
    assert naming(company=company, role=role + " and Developer Experience") != planned


def test_a_role_that_alone_overruns_the_cap_still_leaves_the_company_readable() -> None:
    """The floor: when the role cannot fit at all it degrades to its hash rather than to
    nothing, and the company is not sacrificed to it."""
    planned = naming(role="Distinguished " * 12 + "Engineer", company="Acme Robotics")
    assert blen(f"{planned.stem}{PDF_SUFFIX}") <= RESUME_NAME_BYTE_CAP
    assert planned.stem.startswith(f"{OWNER_SLUG}_Acme_Robotics_")
    assert planned.stem != f"{OWNER_SLUG}_Acme_Robotics_"


def test_a_blank_company_or_role_falls_back_to_the_posting_and_never_to_an_empty_part() -> None:
    """A posting with no title and a lead with no company must still name a file. The
    fallback is the queue's own `posting_<hash>`, so the two agree, and it keys on the
    posting so two nameless leads do not collide."""
    planned = naming(company="", role="")
    assert planned.stem == f"{OWNER_SLUG}_posting_{PLAN_FALLBACK}_posting_{PLAN_FALLBACK}"
    assert "__" not in planned.stem
    assert planned.pdf_title == "Ada Lovelace", "empty segments must be dropped, not spaced"
    assert planned.pdf_author == "Ada Lovelace"
    other = naming(company="", role="", identity_hash=OTHER_IDENTITY)
    assert other.stem != planned.stem


def test_each_variant_is_distinguishable_from_the_others_and_still_inside_the_cap() -> None:
    """The untailored safety net and the Tier B render are different artifacts of one lead and
    share a folder, so their names must differ from the tailored one and from each other."""
    base = naming()
    untailored = naming(variant="untailored")
    llm = naming(variant="llm")
    stems = {base.stem, untailored.stem, llm.stem}
    assert len(stems) == 3, stems
    assert untailored.stem == f"{base.stem}_untailored"
    assert llm.stem == f"{base.stem}_llm"
    for planned in (base, untailored, llm):
        assert blen(f"{planned.stem}{PDF_SUFFIX}") <= RESUME_NAME_BYTE_CAP
    # The metadata describes the application, not the artifact, so it does not vary.
    assert untailored.pdf_title == llm.pdf_title == base.pdf_title


def test_the_variant_is_priced_into_the_cap_rather_than_appended_past_it() -> None:
    long_role = "Senior Backend Platform Engineer, Developer Infrastructure"
    with_variant = naming(role=long_role, variant="untailored")
    assert blen(f"{with_variant.stem}{PDF_SUFFIX}") <= RESUME_NAME_BYTE_CAP
    assert with_variant.stem.endswith("_untailored")


def test_plan_resume_naming_is_deterministic_and_frozen() -> None:
    first = naming()
    assert first == naming()
    with pytest.raises(AttributeError):
        first.stem = "other"  # type: ignore[misc]
