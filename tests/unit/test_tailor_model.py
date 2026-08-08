import pytest
from pydantic import ValidationError

from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup


def _resume(**over):
    base = dict(
        header=["Ada Lovelace", "ada@example.com"],
        education=["BSc Mathematics, Example University"],
        skill_groups=[SkillGroup(label="Languages", items=["Python", "Rust"])],
        entries=[Entry(entry_id="e1", heading="Engineer — Acme — 2020",
                       bullets=[Bullet(bullet_id="b1", text="Built the Python API")])],
    )
    base.update(over)
    return Resume(**base)


def test_resume_is_frozen():
    r = _resume()
    with pytest.raises(ValidationError):
        r.header = ["x"]


def test_duplicate_bullet_id_rejected():
    with pytest.raises(ValidationError):
        _resume(entries=[Entry(entry_id="e1", heading="h",
            bullets=[Bullet(bullet_id="b1", text="one"), Bullet(bullet_id="b1", text="two")])])


def test_duplicate_entry_id_rejected():
    with pytest.raises(ValidationError):
        _resume(entries=[Entry(entry_id="e1", heading="h", bullets=[Bullet(bullet_id="b1", text="x")]),
                         Entry(entry_id="e1", heading="h2", bullets=[Bullet(bullet_id="b2", text="y")])])


def test_bullet_newlines_normalized_to_space():
    b = Bullet(bullet_id="b1", text="line one\nline two")
    assert b.text == "line one line two"


def test_entry_structured_fields_optional_and_frozen():
    from boardwatch.tailor.model import Bullet, Entry
    e = Entry(entry_id="e1", heading="X", kind="project", title="Knowledge Forge",
              dates="Sep 2023 – Dec 2023", subtitle="Python, Django",
              bullets=[Bullet(bullet_id="b1", text="Built it")])
    assert e.kind == "project" and e.title == "Knowledge Forge" and e.location is None
    # defaults on a heading-only entry (back-compat)
    e2 = Entry(entry_id="e2", heading="Y", bullets=[Bullet(bullet_id="b2", text="Did it")])
    assert e2.kind == "experience" and e2.title is None
