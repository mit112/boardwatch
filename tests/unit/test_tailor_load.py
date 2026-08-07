from pathlib import Path

import pytest

from boardwatch.reports.resume_gate import GateReason
from boardwatch.tailor.load import (
    MasterResumeError,
    ResumeLoadError,
    load_resume,
    scaffold_template,
    validate_master,
)
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup


def test_scaffold_roundtrips(tmp_path):
    p = tmp_path / "resume.yaml"
    p.write_text(scaffold_template(), encoding="utf-8")
    r = load_resume(p)
    assert isinstance(r, Resume)
    assert r.entries and r.entries[0].bullets


def test_missing_file_raises(tmp_path):
    with pytest.raises(ResumeLoadError):
        load_resume(tmp_path / "nope.yaml")


def test_invalid_yaml_raises(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("::: not yaml :::", encoding="utf-8")
    with pytest.raises(ResumeLoadError):
        load_resume(p)


def test_invalid_utf8_raises_load_error(tmp_path: Path) -> None:
    # A mis-encoded file is a load failure, not a raw UnicodeDecodeError escaping the loader.
    p = tmp_path / "r.yaml"
    p.write_bytes(b"header: \xff\xfe\n")
    with pytest.raises(ResumeLoadError):
        load_resume(p)


# --- P4 item 5b: validate_master (run-once, fatal, on the authored master) -------------


def _master(
    *,
    header: list[str] | None = None,
    entries: list[Entry] | None = None,
    education: list[str] | None = None,
    skill_groups: list[SkillGroup] | None = None,
) -> Resume:
    ents = entries if entries is not None else [
        Entry(entry_id="e1", heading="Senior Engineer — Acme", bullets=[Bullet(bullet_id="b1", text="Did a thing")])
    ]
    return Resume(
        header=header if header is not None else ["Ada Lovelace", "ada@example.com"],
        education=education if education is not None else ["BSc Mathematics"],
        skill_groups=skill_groups if skill_groups is not None else [SkillGroup(label="Languages", items=["Python"])],
        entries=ents,
    )


def test_validate_master_passes_a_clean_master() -> None:
    validate_master(_master())  # no raise


def test_validate_master_accepts_a_master_with_more_than_six_bullets_and_a_long_bullet() -> None:
    # The headline negative property: length/count ceilings are P4 item 5a's job on the
    # TAILORED résumé, not this run-once check on the master. A 7-bullet entry and a 250-char
    # bullet are Mit's authoring choice and must pass here (D-055's regression must not
    # reappear).
    long_bullet_text = "a" * 250
    bullets = [Bullet(bullet_id=f"b{i}", text=f"Did thing number {i}") for i in range(6)]
    bullets.append(Bullet(bullet_id="b-long", text=long_bullet_text))
    entry = Entry(entry_id="e1", heading="Senior Engineer — Acme", bullets=bullets)
    validate_master(_master(entries=[entry]))  # no raise


def test_validate_master_rejects_empty_header() -> None:
    with pytest.raises(MasterResumeError) as exc_info:
        validate_master(_master(header=[]))
    assert exc_info.value.reason is GateReason.CONTACT_BLOCK_MISSING_NAME


def test_validate_master_rejects_single_line_header_with_no_email() -> None:
    # A single header line with no email anywhere is a real rejection, but for the EMAIL
    # reason, not line-count: line count alone is not the invariant (see the passing
    # combined-line case below).
    with pytest.raises(MasterResumeError) as exc_info:
        validate_master(_master(header=["Ada Lovelace"]))
    assert exc_info.value.reason is GateReason.CONTACT_BLOCK_INVALID_EMAIL


def test_validate_master_accepts_a_single_combined_header_line_with_name_and_email() -> None:
    # A single-element header carrying "name · email · links" all on one line is a real
    # résumé convention (design fixtures use single-element headers; nothing in the Resume
    # schema, validate_slots, or the Typst renderer requires >=2 header lines). Gating on
    # line count alone was a false-fatal that would reject a genuinely valid master.
    validate_master(_master(header=["Ada Lovelace · ada@example.com · github.com/ada"]))


def test_validate_master_rejects_blank_name_line() -> None:
    with pytest.raises(MasterResumeError) as exc_info:
        validate_master(_master(header=["   ", "ada@example.com"]))
    assert exc_info.value.reason is GateReason.CONTACT_BLOCK_MISSING_NAME


def test_validate_master_rejects_missing_email() -> None:
    with pytest.raises(MasterResumeError) as exc_info:
        validate_master(_master(header=["Ada Lovelace", "github.com/ada"]))
    assert exc_info.value.reason is GateReason.CONTACT_BLOCK_INVALID_EMAIL


def test_validate_master_rejects_malformed_email() -> None:
    with pytest.raises(MasterResumeError) as exc_info:
        validate_master(_master(header=["Ada Lovelace", "ada at example dot com"]))
    assert exc_info.value.reason is GateReason.CONTACT_BLOCK_INVALID_EMAIL


def test_validate_master_rejects_template_artifact_in_header() -> None:
    with pytest.raises(MasterResumeError) as exc_info:
        validate_master(_master(header=["{{name}}", "ada@example.com"]))
    assert exc_info.value.reason is GateReason.TEMPLATE_ARTIFACT


def test_validate_master_rejects_standalone_todo_in_bullet() -> None:
    entry = Entry(
        entry_id="e1",
        heading="Senior Engineer — Acme",
        bullets=[Bullet(bullet_id="b1", text="TODO rewrite this with a real accomplishment")],
    )
    with pytest.raises(MasterResumeError) as exc_info:
        validate_master(_master(entries=[entry]))
    assert exc_info.value.reason is GateReason.TEMPLATE_ARTIFACT


# --- load_resume integration: a broken master aborts loudly, a valid one proceeds ------


def test_load_resume_rejects_a_master_missing_contact_info(tmp_path: Path) -> None:
    p = tmp_path / "resume.yaml"
    p.write_text(
        """\
header: []
education: []
skill_groups: []
entries:
  - entry_id: "e1"
    heading: "Senior Engineer"
    bullets:
      - bullet_id: "b1"
        text: "Did a thing"
""",
        encoding="utf-8",
    )
    with pytest.raises(MasterResumeError) as exc_info:
        load_resume(p)
    assert exc_info.value.reason is GateReason.CONTACT_BLOCK_MISSING_NAME
    assert isinstance(exc_info.value, ResumeLoadError)


def test_load_resume_rejects_a_master_with_no_email(tmp_path: Path) -> None:
    # A single header line with a name but no email anywhere is a real rejection, on the
    # EMAIL reason — mirrors the unit-level no-email case above, exercised through the full
    # load_resume() path.
    p = tmp_path / "resume.yaml"
    p.write_text(
        """\
header:
  - "Ada Lovelace"
education: []
skill_groups: []
entries:
  - entry_id: "e1"
    heading: "Senior Engineer"
    bullets:
      - bullet_id: "b1"
        text: "Did a thing"
""",
        encoding="utf-8",
    )
    with pytest.raises(MasterResumeError) as exc_info:
        load_resume(p)
    assert exc_info.value.reason is GateReason.CONTACT_BLOCK_INVALID_EMAIL


def test_load_resume_rejects_a_master_with_a_template_artifact(tmp_path: Path) -> None:
    p = tmp_path / "resume.yaml"
    p.write_text(
        """\
header:
  - "Ada Lovelace"
  - "ada@example.com"
education: []
skill_groups: []
entries:
  - entry_id: "e1"
    heading: "Senior Engineer"
    bullets:
      - bullet_id: "b1"
        text: "TODO rewrite this bullet"
""",
        encoding="utf-8",
    )
    with pytest.raises(MasterResumeError) as exc_info:
        load_resume(p)
    assert exc_info.value.reason is GateReason.TEMPLATE_ARTIFACT


def test_load_resume_accepts_a_valid_master_with_a_seven_bullet_entry(tmp_path: Path) -> None:
    bullets = "\n".join(
        f'      - bullet_id: "b{i}"\n        text: "Did thing number {i}"' for i in range(7)
    )
    p = tmp_path / "resume.yaml"
    p.write_text(
        f"""\
header:
  - "Ada Lovelace"
  - "ada@example.com"
education: []
skill_groups: []
entries:
  - entry_id: "e1"
    heading: "Senior Engineer"
    bullets:
{bullets}
""",
        encoding="utf-8",
    )
    r = load_resume(p)
    assert len(r.entries[0].bullets) == 7
