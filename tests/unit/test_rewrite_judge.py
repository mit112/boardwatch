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
    ("NOTENTAILED", "NOT_ENTAILED"),
    ("not-entailed", "NOT_ENTAILED"),
    ("NOT  ENTAILED", "NOT_ENTAILED"),
    ("UNENTAILED", "NOT_ENTAILED"),
    ("NON-ENTAILED", "NOT_ENTAILED"),
    ('{"verdict": "not_entailed"}', "NOT_ENTAILED"),
    ("NOT ENTAILED because it is ENTAILED in spirit", "NOT_ENTAILED"),
    ("Verdict: ENTAILED", "ENTAILED"),
])
def test_parse_verdict(reply, expected):
    assert parse_verdict(reply) == expected
