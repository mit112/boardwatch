from boardwatch.core.identity import PostingKey, posting_key
from boardwatch.core.normalize import content_hash


def test_identity_is_company_and_provider_posting_id_only() -> None:
    assert PostingKey._fields == ("company_id", "provider_posting_id")  # D10: nothing else


def test_identical_bodies_under_distinct_ids_are_distinct_identities() -> None:
    body = "<p>Same body text for two simultaneous openings.</p>"
    key_a = posting_key(company_id=7, provider_posting_id="100")
    key_b = posting_key(company_id=7, provider_posting_id="200")
    assert content_hash(body) == content_hash(body)
    assert key_a != key_b  # same content never merges identities (D10)


def test_same_id_same_company_is_the_same_identity() -> None:
    assert posting_key(1, "42") == posting_key(1, "42")
