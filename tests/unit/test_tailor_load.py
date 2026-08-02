import pytest

from boardwatch.tailor.load import ResumeLoadError, load_resume, scaffold_template
from boardwatch.tailor.model import Resume


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
