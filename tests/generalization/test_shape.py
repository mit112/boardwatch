"""Group 1 shape rules. Violating fixtures are assembled at runtime so the
literals never exist on disk."""

from __future__ import annotations

from pathlib import Path

from tools.generalization import allowlists as al
from tools.generalization.discovery import Repo, RepoFile
from tools.generalization.shape import PROFILE_URL_RE, check_artifact_files, check_shapes

_HOME = "/Us" + "ers/someone/Desktop/notes.txt"
# HOME_PATH_RE stops at the first path separator after the leading component, so the
# text an exception entry must key on is this truncated prefix, not the full path above.
_HOME_HIT = "/Us" + "ers/someone"
_HOME_LOWER = "/us" + "ers/someone/x"
_HOME_UPPER = "/HOME" + "/someone/x"
_HOME_WINDOWS_UPPER = "C:" + "\\USERS\\someone"
_MAIL = "person" + "@" + "realdomain.dev"
_LINKEDIN = "https://www.linked" + "in.com/in/someone"
_MAILTO = "mail" + "to:"
# The identifying tail is part of the match, so the exception table keys on the full address,
# never on the bare "mailto:" prefix.
_MAILTO_HIT = _MAILTO + "security@example.com"
_PHONE_NANP = "415-555" + "-0134"
# Neither fragment below is itself a complete PHONE_RE match: "+91 " and "+91-" carry no
# digit groups on their own, and the remaining digit runs carry neither a "+" nor a
# separator, so they do not qualify under any alternative either.
_PHONE_INTL_SPACED = "+91 " + "98765 43210"
_PHONE_INTL_CC_HYPHEN = "+91-" + "9876543210"
_PHONE_UK = "07700" + " 900123"
# Compact E.164 forms (country code directly followed by 10-15 digits with no separators)
# are the machine-readable canonical form found in vCard, tel: URI, and harvest vectors.
_PHONE_E164_IN = "+91" + "9876543210"
_PHONE_E164_US = "+1" + "4155550134"
_PHONE_E164_UK = "+44" + "2079460958"
_PHONE_TEL_URI = "tel:" + "+91" + "9876543210"


def _repo(text: str, path: str = "docs/thing.md") -> Repo:
    entry = RepoFile(path=path, abspath=Path(path), is_text=True, text=text)
    return Repo(root=Path("/tmp/fake"), files=(entry,))


def _named(path: str, *, text: str = "x", is_text: bool = True) -> Repo:
    entry = RepoFile(path=path, abspath=Path(path), is_text=is_text, text=text)
    return Repo(root=Path("/tmp/fake"), files=(entry,))


def test_home_path_is_rejected() -> None:
    found = check_shapes(_repo(f"see {_HOME} for details"))
    assert [v.rule for v in found] == ["R1"]
    assert found[0].line == 1


def test_windows_home_path_is_rejected() -> None:
    found = check_shapes(_repo("C:" + "\\Users\\someone\\config"))
    assert [v.rule for v in found] == ["R1"]


def test_windows_home_path_is_rejected_case_insensitively() -> None:
    found = check_shapes(_repo(_HOME_WINDOWS_UPPER))
    assert [v.rule for v in found] == ["R1"]


def test_case_variant_unix_home_prefixes_are_an_accepted_bypass() -> None:
    """Real macOS output is always "/Users/" and real Linux output always "/home/", so a
    case-varied prefix is not real OS output. The false-positive class this buys back is
    ordinary REST routes and URL paths, which a blanket IGNORECASE also matched."""
    assert check_shapes(_repo(_HOME_LOWER)) == []
    assert check_shapes(_repo(_HOME_UPPER)) == []


def test_rest_and_url_paths_are_not_home_paths() -> None:
    """The v1 bar died by firing on legitimate content. /v1/users/{id} is a documented API
    route on a provider this project integrates."""
    for text in (
        "GET /users/me returns the caller",
        "POST /api/v1/users/123",
        "https://example.com/Home/Index",
        "run /usr/bin/env python",
    ):
        assert check_shapes(_repo(text)) == [], text


def test_tilde_path_is_allowed() -> None:
    assert check_shapes(_repo("store it in ~/Library/boardwatch")) == []


def test_allowlisted_home_path_is_accepted_and_marks_the_entry_used() -> None:
    original = dict(al.HOME_PATH_EXCEPTIONS)
    al.HOME_PATH_EXCEPTIONS[_HOME_HIT] = "fixture path documented as a known exception"
    try:
        assert check_shapes(_repo(f"see {_HOME} for details")) == []
    finally:
        al.HOME_PATH_EXCEPTIONS.clear()
        al.HOME_PATH_EXCEPTIONS.update(original)


def test_stale_home_path_exception_is_reported() -> None:
    original = dict(al.HOME_PATH_EXCEPTIONS)
    al.HOME_PATH_EXCEPTIONS[_HOME_HIT] = "no longer present"
    try:
        found = check_shapes(_repo("nothing here"))
        assert [v.rule for v in found] == ["R1"]
        assert "stale exception" in found[0].detail
    finally:
        al.HOME_PATH_EXCEPTIONS.clear()
        al.HOME_PATH_EXCEPTIONS.update(original)


def test_email_is_rejected() -> None:
    found = check_shapes(_repo(f"contact {_MAIL} please"))
    assert [v.rule for v in found] == ["R2"]


def test_reserved_example_domains_are_allowed() -> None:
    assert check_shapes(_repo("use you@example.com or you@example.org")) == []


def test_allowlisted_email_is_accepted_and_marks_the_entry_used() -> None:
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
    found = check_shapes(_repo(f"call {_PHONE_NANP} now"))
    assert [v.rule for v in found] == ["R3"]


def test_international_phone_formats_are_rejected() -> None:
    for phone in (_PHONE_INTL_SPACED, _PHONE_INTL_CC_HYPHEN, _PHONE_UK, _PHONE_E164_IN, _PHONE_E164_US, _PHONE_E164_UK, _PHONE_TEL_URI):
        found = check_shapes(_repo(f"call {phone} now"))
        assert [v.rule for v in found] == ["R3"], phone


def test_dates_and_digests_are_not_phone_numbers() -> None:
    text = "released 2026-07-27, digest 8df3b3809bba, port 5000, id 4155550134"
    assert check_shapes(_repo(text)) == []


def test_versions_and_grouped_digit_runs_are_not_phone_numbers() -> None:
    text = "version 1.234.567.8901, sha 123 456 7890, range 100 200 3000"
    assert check_shapes(_repo(text)) == []


def test_plus_prefixed_prose_deltas_are_not_phone_numbers() -> None:
    for text in (
        "Coverage improved: +150 statements",
        "latency +250 ms",
        "increase of +100%",
        "3 files changed, +153 -11",
        "Price delta +1.50 USD",
        "delta +12 345 678 bytes",
        "+1 000 000 rows",
        "+123 456 789 events",
        "budget +12.345.678 EUR",
    ):
        assert check_shapes(_repo(text)) == [], text


def test_decimals_and_digit_pairs_are_not_phone_numbers() -> None:
    for text in (
        "float 12345.678901",
        "throughput 65536 131072 bytes",
        "Elapsed 12345 678901 ns",
        "port range 30000-32767",
        "salary band 85000-95000 USD",
        "ephemeral ports 49152-65535",
        "linux ports 32768-60999",
    ):
        assert check_shapes(_repo(text)) == [], text


def test_local_format_numbers_with_no_country_code_are_an_accepted_bypass() -> None:
    """Bare digit pairs without country code are an accepted bypass."""
    local_number = "98765" + "-43210"
    assert check_shapes(_repo(f"call {local_number} now")) == []


def test_short_intl_exception_is_used_and_not_reported_stale() -> None:
    """An exception below the digit threshold is consulted before filtering."""
    original = dict(al.PHONE_EXCEPTIONS)
    short_hit = "+1 " + "234 567"
    al.PHONE_EXCEPTIONS[short_hit] = "fixture exception below digit threshold"
    try:
        found = check_shapes(_repo(f"dial {short_hit} now"))
        assert found == []
    finally:
        al.PHONE_EXCEPTIONS.clear()
        al.PHONE_EXCEPTIONS.update(original)


def test_allowlisted_phone_is_accepted_and_marks_the_entry_used() -> None:
    original = dict(al.PHONE_EXCEPTIONS)
    al.PHONE_EXCEPTIONS[_PHONE_NANP] = "fixture number documented as a known exception"
    try:
        assert check_shapes(_repo(f"call {_PHONE_NANP} now")) == []
    finally:
        al.PHONE_EXCEPTIONS.clear()
        al.PHONE_EXCEPTIONS.update(original)


def test_stale_phone_exception_is_reported() -> None:
    original = dict(al.PHONE_EXCEPTIONS)
    al.PHONE_EXCEPTIONS[_PHONE_NANP] = "no longer present"
    try:
        found = check_shapes(_repo("nothing here"))
        assert [v.rule for v in found] == ["R3"]
        assert "stale exception" in found[0].detail
    finally:
        al.PHONE_EXCEPTIONS.clear()
        al.PHONE_EXCEPTIONS.update(original)


def test_profile_url_is_rejected() -> None:
    found = check_shapes(_repo(f"profile at {_LINKEDIN}"))
    assert [v.rule for v in found] == ["R4"]


def test_mailto_with_an_address_is_rejected() -> None:
    found = check_shapes(_repo(f"contact us at {_MAILTO_HIT}"))
    assert [v.rule for v in found] == ["R4"]


def test_bare_mailto_with_no_tail_is_an_accepted_bypass() -> None:
    """A "mailto:" with nothing after it identifies nobody, so it is not a match: the
    identifying tail is part of the match, on purpose."""
    assert check_shapes(_repo(f"see {_MAILTO} for the format")) == []


def test_a_trailing_period_is_not_part_of_a_profile_url() -> None:
    """A SECURITY.md contact line ending a sentence with a period must not fold that period
    into the match: an exception keyed on the clean address has to actually match."""
    punctuated = _MAILTO_HIT + "."
    match = PROFILE_URL_RE.search(f"contact us at {punctuated} for reports")
    assert match is not None
    assert match.group(0) == _MAILTO_HIT


def test_allowlisted_profile_url_is_accepted_and_marks_the_entry_used() -> None:
    original = dict(al.PROFILE_URL_EXCEPTIONS)
    al.PROFILE_URL_EXCEPTIONS[_MAILTO_HIT] = "security contact published in SECURITY.md"
    try:
        assert check_shapes(_repo(f"contact us at {_MAILTO_HIT}")) == []
    finally:
        al.PROFILE_URL_EXCEPTIONS.clear()
        al.PROFILE_URL_EXCEPTIONS.update(original)


def test_an_allowlisted_profile_url_does_not_exempt_a_different_address() -> None:
    """The key is match-level, so allowlisting one address must not blanket-exempt R4: the
    old bare "mailto:" pattern meant the only possible entry disabled half the rule repo-wide."""
    original = dict(al.PROFILE_URL_EXCEPTIONS)
    al.PROFILE_URL_EXCEPTIONS[_MAILTO_HIT] = "security contact published in SECURITY.md"
    other = _MAILTO + "someone-else@example.com"
    try:
        found = check_shapes(_repo(f"contact us at {other}"))
        # The allowlisted address is unused by this scan, so it is also reported stale;
        # the property under test is that the unexempted address is rejected at all.
        offender = [v for v in found if other in v.detail]
        assert [v.rule for v in offender] == ["R4"]
    finally:
        al.PROFILE_URL_EXCEPTIONS.clear()
        al.PROFILE_URL_EXCEPTIONS.update(original)


def test_stale_profile_url_exception_is_reported() -> None:
    original = dict(al.PROFILE_URL_EXCEPTIONS)
    al.PROFILE_URL_EXCEPTIONS[_MAILTO_HIT] = "no longer present"
    try:
        found = check_shapes(_repo("nothing here"))
        assert [v.rule for v in found] == ["R4"]
        assert "stale exception" in found[0].detail
    finally:
        al.PROFILE_URL_EXCEPTIONS.clear()
        al.PROFILE_URL_EXCEPTIONS.update(original)


def test_a_blank_exception_reason_is_rejected_across_all_six_tables() -> None:
    """The entry IS the justification, so membership alone would be a rubber stamp. Same
    rule check_inventory already applies to a blank SHIPPED_DATA reason (R7)."""
    shape_cases: list[tuple[dict[str, str], str, Repo, str]] = [
        (al.HOME_PATH_EXCEPTIONS, _HOME_HIT, _repo(f"see {_HOME} for details"), "R1"),
        (al.EMAIL_EXCEPTIONS, _MAIL, _repo(f"contact {_MAIL} please"), "R2"),
        (al.PHONE_EXCEPTIONS, _PHONE_NANP, _repo(f"call {_PHONE_NANP} now"), "R3"),
        (al.PROFILE_URL_EXCEPTIONS, _MAILTO_HIT, _repo(f"contact us at {_MAILTO_HIT}"), "R4"),
    ]
    for table, key, repo, rule in shape_cases:
        original = dict(table)
        table[key] = ""
        try:
            found = [v for v in check_shapes(repo) if v.rule == rule]
            assert len(found) == 1, found
            assert "blank reason" in found[0].detail
        finally:
            table.clear()
            table.update(original)

    artifact_path = "docs/" + "resume" + ".yaml"
    binary_path = "docs/" + "guide" + ".pdf"
    artifact_cases: list[tuple[dict[str, str], str, Repo, str]] = [
        (al.ARTIFACT_NAME_EXCEPTIONS, artifact_path, _named(artifact_path), "R5"),
        (
            al.BINARY_DOC_EXCEPTIONS,
            binary_path,
            _named(binary_path, is_text=False, text=""),
            "R6",
        ),
    ]
    for table, key, repo, rule in artifact_cases:
        original = dict(table)
        table[key] = ""
        try:
            found = [v for v in check_artifact_files(repo) if v.rule == rule]
            assert len(found) == 1, found
            assert "blank reason" in found[0].detail
        finally:
            table.clear()
            table.update(original)


def test_allowlisted_artifact_name_is_accepted_and_marks_the_entry_used() -> None:
    original = dict(al.ARTIFACT_NAME_EXCEPTIONS)
    path = "docs/" + "resume" + ".yaml"
    al.ARTIFACT_NAME_EXCEPTIONS[path] = "fixture path documented as a known exception"
    try:
        assert check_artifact_files(_named(path)) == []
    finally:
        al.ARTIFACT_NAME_EXCEPTIONS.clear()
        al.ARTIFACT_NAME_EXCEPTIONS.update(original)


def test_binary_files_are_not_scanned() -> None:
    entry = RepoFile(path="a.bin", abspath=Path("a.bin"), is_text=False, text=_HOME)
    assert check_shapes(Repo(root=Path("/tmp/fake"), files=(entry,))) == []


def test_the_checker_does_not_scan_itself() -> None:
    found = check_shapes(_repo(f"see {_HOME}", path="tools/generalization/shape.py"))
    assert found == []
    found = check_shapes(_repo(f"see {_HOME}", path="tests/generalization/test_shape.py"))
    assert found == []


def test_line_numbers_are_reported() -> None:
    found = check_shapes(_repo(f"line one\nline two\n{_HOME}\n"))
    assert found[0].line == 3


def test_resume_data_file_is_rejected() -> None:
    found = check_artifact_files(_named("docs/" + "resume" + ".yaml"))
    assert [v.rule for v in found] == ["R5"]


def test_resume_directory_segment_is_rejected() -> None:
    found = check_artifact_files(_named("data/" + "cover_letter" + "/one.json"))
    assert [v.rule for v in found] == ["R5"]


def test_python_modules_are_never_stem_checked() -> None:
    """Banning personal VALUES must not ban work-authorization CONCEPTS."""
    for name in ("resume", "work_auth", "eeo", "cv"):
        assert check_artifact_files(_named(f"src/boardwatch/{name}.py")) == []


def test_neutral_data_file_is_allowed() -> None:
    assert check_artifact_files(_named("tests/fixtures/lever/normal.json")) == []


def test_binary_document_is_rejected() -> None:
    found = check_artifact_files(_named("docs/" + "guide" + ".pdf", is_text=False, text=""))
    assert [v.rule for v in found] == ["R6"]


def test_stale_artifact_exception_is_reported() -> None:
    original = dict(al.ARTIFACT_NAME_EXCEPTIONS)
    al.ARTIFACT_NAME_EXCEPTIONS["docs/gone.yaml"] = "removed last release"
    try:
        found = check_artifact_files(_named("tests/fixtures/lever/normal.json"))
        assert [v.rule for v in found] == ["R5"]
        assert "stale exception" in found[0].detail
    finally:
        al.ARTIFACT_NAME_EXCEPTIONS.clear()
        al.ARTIFACT_NAME_EXCEPTIONS.update(original)


def test_hidden_artifact_data_file_is_rejected() -> None:
    found = check_artifact_files(_named("." + "resume" + ".yaml"))
    assert [v.rule for v in found] == ["R5"]


def test_stale_binary_doc_exception_is_reported() -> None:
    original = dict(al.BINARY_DOC_EXCEPTIONS)
    al.BINARY_DOC_EXCEPTIONS["docs/gone.pdf"] = "removed last release"
    try:
        found = check_artifact_files(_named("tests/fixtures/lever/normal.json"))
        assert [v.rule for v in found] == ["R6"]
        assert "stale exception" in found[0].detail
    finally:
        al.BINARY_DOC_EXCEPTIONS.clear()
        al.BINARY_DOC_EXCEPTIONS.update(original)
