import pytest

from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("greenhouse:acme", ("greenhouse", "acme")),
        ("lever:globex", ("lever", "globex")),
        ("https://job-boards.greenhouse.io/acme", ("greenhouse", "acme")),
        ("https://boards.greenhouse.io/acme/jobs/123", ("greenhouse", "acme")),
        ("https://jobs.lever.co/globex/", ("lever", "globex")),
        ("https://jobs.eu.lever.co/globex/abc-123-def", ("lever", "globex")),
        ("https://jobs.ashbyhq.com/initech?utm=x", ("ashby", "initech")),
        ("https://jobs.ashbyhq.com/initech/job/abc", ("ashby", "initech")),
    ],
)
def test_parses_known_targets(value, expected) -> None:
    assert parse_board_target(value) == expected

def test_unknown_url_is_rejected_with_supported_forms() -> None:
    with pytest.raises(UnknownBoardURL) as exc:
        parse_board_target("https://workday.com/acme")
    assert "greenhouse" in str(exc.value) and "provider:slug" in str(exc.value)

def test_help_text_enumerates_all_registry_providers() -> None:
    from boardwatch.providers.registry import PROVIDER_NAMES

    with pytest.raises(UnknownBoardURL) as exc:
        parse_board_target("workday:acme")
    msg = str(exc.value)
    for name in PROVIDER_NAMES:
        assert name in msg


def test_board_urls_never_imports_store_transitively() -> None:
    # a SOURCE-STRING check misses transitive imports; assert the real import graph in a
    # clean subprocess: importing board_urls must not pull in any boardwatch.store.* module
    import subprocess
    import sys

    code = (
        "import boardwatch.core.board_urls; import sys; "
        "bad=[m for m in sys.modules if m.startswith('boardwatch.store')]; "
        "assert not bad, bad"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
