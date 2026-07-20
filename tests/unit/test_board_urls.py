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
