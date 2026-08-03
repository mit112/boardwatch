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
    ("The candidate is NOT really entailed by the source", "NOT_ENTAILED"),
    ("This claim is definitely not fully entailed here", "NOT_ENTAILED"),
    ("No, that is entailed only loosely", "NOT_ENTAILED"),
    ("cannot be entailed", "NOT_ENTAILED"),
    ("Fully ENTAILED by the source bullet", "ENTAILED"),
])
def test_parse_verdict(reply, expected):
    assert parse_verdict(reply) == expected
