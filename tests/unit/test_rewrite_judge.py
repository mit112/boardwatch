import pytest
from boardwatch.tailor.rewrite.judge import parse_verdict


@pytest.mark.parametrize("reply,expected", [
    ("ENTAILED", "ENTAILED"),
    ("  entailed  ", "ENTAILED"),
    ("NOT_ENTAILED", "NOT_ENTAILED"),
    ("not entailed", "NOT_ENTAILED"),
    ("The claim is NOT_ENTAILED by the source.", "NOT_ENTAILED"),
    ("Yes, ENTAILED.", "ENTAILED"),
    ("maybe?", "UNSURE"),
    ("", "UNSURE"),
])
def test_parse_verdict(reply, expected):
    assert parse_verdict(reply) == expected
