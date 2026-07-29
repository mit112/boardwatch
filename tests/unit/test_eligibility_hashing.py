"""One canonical JSON form backs all three hashes, matching the shape at
extract/taxonomy.py:95-103. Formatting and key order must never change a hash;
content always must."""

from boardwatch.eligibility.hashing import canonical, digest


def test_key_order_never_changes_the_canonical_form() -> None:
    assert canonical({"b": 1, "a": 2}) == canonical({"a": 2, "b": 1}) == '{"a":2,"b":1}'


def test_canonical_form_is_compact() -> None:
    assert canonical({"a": [1, 2]}) == '{"a":[1,2]}'


def test_nested_key_order_never_changes_the_canonical_form() -> None:
    left = {"outer": {"z": 1, "a": {"q": 2, "b": 3}}}
    right = {"outer": {"a": {"b": 3, "q": 2}, "z": 1}}
    assert canonical(left) == canonical(right)


def test_digest_is_stable_across_calls() -> None:
    assert digest({"a": 1}) == digest({"a": 1})


def test_digest_changes_on_content() -> None:
    assert digest({"a": 1}) != digest({"a": 2})


def test_digest_distinguishes_null_from_absent() -> None:
    """A vanishing key must not collide with an explicit null, or "fact never set" and
    "fact set then cleared" become the same fingerprint."""
    assert digest({"a": None}) != digest({})


def test_digest_is_hex_sha256() -> None:
    value = digest({"a": 1})
    assert len(value) == 64
    assert set(value) <= set("0123456789abcdef")


def test_list_order_does_change_the_canonical_form() -> None:
    """Only MAPPING key order is insignificant. A list is ordered data, so reordering it
    is a content change and must move the hash, or a reordered evidence span list would
    silently reuse a stale fingerprint."""
    assert canonical({"a": [1, 2]}) != canonical({"a": [2, 1]})
    assert digest({"a": [1, 2]}) != digest({"a": [2, 1]})


def test_digest_distinguishes_string_from_number() -> None:
    """`1` and `"1"` are different facts. json.dumps keeps them apart, and this pins it so
    a future switch to a stringifying serialiser cannot collapse them unnoticed."""
    assert digest({"a": 1}) != digest({"a": "1"})
