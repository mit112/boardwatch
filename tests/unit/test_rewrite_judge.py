import pytest

from boardwatch.tailor.rewrite.judge import parse_verdict


# NOT_ENTAILED and UNSURE are both non-accepting — the lane drops on either verdict — so
# where a row below returns UNSURE for a reply that looks like a negation, that is not a
# regression: exact-equality no longer distinguishes "clean negation token" from "negation
# buried in prose" the way the old blocklist's word-scan did, and safety does not require
# it to. Only ENTAILED is an accept; NOT_ENTAILED vs UNSURE only affects the recorded
# reason, never whether the bullet is kept.
@pytest.mark.parametrize("reply,expected", [
    ("ENTAILED", "ENTAILED"),
    ("  entailed  ", "ENTAILED"),
    ("NOT_ENTAILED", "NOT_ENTAILED"),
    ("not entailed", "NOT_ENTAILED"),
    # Prose wrapped around a negation token: no longer an exact token, so UNSURE.
    ("The claim is NOT_ENTAILED by the source.", "UNSURE"),
    # Prose acceptance is exactly what regressed three times running — no longer trusted.
    ("Yes, ENTAILED.", "UNSURE"),
    ("maybe?", "UNSURE"),
    ("", "UNSURE"),
    ("NOTENTAILED", "NOT_ENTAILED"),
    ("not-entailed", "NOT_ENTAILED"),
    ("NOT  ENTAILED", "NOT_ENTAILED"),
    ("UNENTAILED", "NOT_ENTAILED"),
    ("NON-ENTAILED", "NOT_ENTAILED"),
    ('{"verdict": "not_entailed"}', "UNSURE"),
    ("NOT ENTAILED because it is ENTAILED in spirit", "UNSURE"),
    ("Verdict: ENTAILED", "ENTAILED"),
    ("The candidate is NOT really entailed by the source", "UNSURE"),
    ("This claim is definitely not fully entailed here", "UNSURE"),
    ("No, that is entailed only loosely", "UNSURE"),
    ("cannot be entailed", "UNSURE"),
    ("Fully ENTAILED by the source bullet", "UNSURE"),
    ("UNSURE - possibly ENTAILED", "UNSURE"),
    ("UNSURE, leaning ENTAILED", "UNSURE"),
    ("I am unsure but it may be ENTAILED", "UNSURE"),
    ("Probably ENTAILED, but unsure", "UNSURE"),
    ("UNCERTAIN", "UNSURE"),
    ("maybe ENTAILED", "UNSURE"),
    ("ENTAILED (probably)", "UNSURE"),
    # --- regression: hedged/annotated replies that a blocklist-shaped parser has, in
    # practice, accepted at least once each across three prior fix rounds. None of these
    # is an exact ENTAILED token, so all must be non-accepting under the allowlist.
    ("Partially entailed", "UNSURE"),
    ("Mostly ENTAILED", "UNSURE"),
    ("Largely entailed", "UNSURE"),
    ("Somewhat entailed", "UNSURE"),
    ("ENTAILED (low confidence)", "UNSURE"),
    ("Overstated but entailed", "UNSURE"),
    ("This is unlikely to be entailed", "UNSURE"),
    ("Arguably entailed", "UNSURE"),
    ("borderline entailed", "UNSURE"),
    ("ENTAILED*", "UNSURE"),
    # Canonical UNSURE: the judge's own system prompt offers this exact token, so it
    # deserves a pinned row hitting the `squashed == "UNSURE"` return directly, not just
    # falling through to the same result via the final `return "UNSURE"`.
    ("UNSURE", "UNSURE"),
    ("unsure", "UNSURE"),
    ("Verdict: UNSURE", "UNSURE"),
])
def test_parse_verdict(reply, expected):
    assert parse_verdict(reply) == expected


# The invariant that keeps regressing: a reply need only contain the substring ENTAILED
# to have been wrongly accepted by a blocklist-shaped parser. Pin it directly, separate
# from the table above, so a future edit that reintroduces "contains ENTAILED" as an
# accept condition fails immediately and obviously.
_PROSE_CONTAINING_ENTAILED = [
    "Partially entailed",
    "Mostly ENTAILED",
    "Largely entailed",
    "Somewhat entailed",
    "ENTAILED (low confidence)",
    "Overstated but entailed",
    "This is unlikely to be entailed",
    "Arguably entailed",
    "borderline entailed",
    "ENTAILED*",
    "Yes, ENTAILED.",
    "Fully ENTAILED by the source bullet",
    "NOT ENTAILED because it is ENTAILED in spirit",
    "The claim is NOT_ENTAILED by the source.",
    "UNSURE - possibly ENTAILED",
    "maybe ENTAILED",
    "ENTAILED (probably)",
]


@pytest.mark.parametrize("reply", _PROSE_CONTAINING_ENTAILED)
def test_prose_containing_entailed_never_accepts(reply):
    assert parse_verdict(reply) != "ENTAILED"
