"""Group 1 shape rules. Violating fixtures are assembled at runtime so the
literals never exist on disk (spec section 9.1)."""

from __future__ import annotations

from pathlib import Path

from tools.generalization import allowlists as al
from tools.generalization.discovery import Repo, RepoFile
from tools.generalization.shape import check_shapes

_HOME = "/Us" + "ers/someone/Desktop/notes.txt"
_MAIL = "person" + "@" + "realdomain.dev"
_LINKEDIN = "https://www.linked" + "in.com/in/someone"


def _repo(text: str, path: str = "docs/thing.md") -> Repo:
    entry = RepoFile(path=path, abspath=Path(path), is_text=True, text=text)
    return Repo(root=Path("/tmp/fake"), files=(entry,))


def test_home_path_is_rejected() -> None:
    found = check_shapes(_repo(f"see {_HOME} for details"))
    assert [v.rule for v in found] == ["R1"]
    assert found[0].line == 1


def test_windows_home_path_is_rejected() -> None:
    found = check_shapes(_repo("C:" + "\\Users\\someone\\config"))
    assert [v.rule for v in found] == ["R1"]


def test_tilde_path_is_allowed() -> None:
    assert check_shapes(_repo("store it in ~/Library/boardwatch")) == []


def test_email_is_rejected() -> None:
    found = check_shapes(_repo(f"contact {_MAIL} please"))
    assert [v.rule for v in found] == ["R2"]


def test_reserved_example_domains_are_allowed() -> None:
    assert check_shapes(_repo("use you@example.com or you@example.org")) == []


def test_allowlisted_email_is_accepted_and_marks_the_entry_used(
    monkeypatch: object,
) -> None:
    address = "sec" + "@" + "boardwatch.dev"
    original = dict(al.EMAIL_EXCEPTIONS)
    al.EMAIL_EXCEPTIONS[address] = "security contact published in SECURITY.md"
    try:
        assert check_shapes(_repo(f"report to {address}")) == []
    finally:
        al.EMAIL_EXCEPTIONS.clear()
        al.EMAIL_EXCEPTIONS.update(original)


def test_stale_email_exception_is_reported() -> None:
    original = dict(al.EMAIL_EXCEPTIONS)
    al.EMAIL_EXCEPTIONS["never" + "@" + "seen.dev"] = "no longer present"
    try:
        found = check_shapes(_repo("nothing here"))
        assert [v.rule for v in found] == ["R2"]
        assert "stale exception" in found[0].detail
    finally:
        al.EMAIL_EXCEPTIONS.clear()
        al.EMAIL_EXCEPTIONS.update(original)


def test_phone_number_is_rejected() -> None:
    found = check_shapes(_repo("call 415-555-0134 now"))
    assert [v.rule for v in found] == ["R3"]


def test_dates_and_digests_are_not_phone_numbers() -> None:
    text = "released 2026-07-27, digest 8df3b3809bba, port 5000, id 4155550134"
    assert check_shapes(_repo(text)) == []


def test_profile_url_is_rejected() -> None:
    found = check_shapes(_repo(f"profile at {_LINKEDIN}"))
    assert [v.rule for v in found] == ["R4"]


def test_binary_files_are_not_scanned() -> None:
    entry = RepoFile(path="a.bin", abspath=Path("a.bin"), is_text=False, text="")
    assert check_shapes(Repo(root=Path("/tmp/fake"), files=(entry,))) == []


def test_the_checker_does_not_scan_itself() -> None:
    found = check_shapes(_repo(f"see {_HOME}", path="tools/generalization/shape.py"))
    assert found == []
    found = check_shapes(_repo(f"see {_HOME}", path="tests/generalization/test_shape.py"))
    assert found == []


def test_line_numbers_are_reported() -> None:
    found = check_shapes(_repo(f"line one\nline two\n{_HOME}\n"))
    assert found[0].line == 3
