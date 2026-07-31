from pathlib import Path

from boardwatch.llm.cache import ResponseCache


def test_put_then_get_roundtrips_exact_string(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    key = "test_key"
    raw_response = "This is a test response from the model."

    cache.put(key, raw_response)
    result = cache.get(key)

    assert result == raw_response


def test_different_prompt_version_creates_different_key(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    content_hash = "abc123def456"
    model = "claude-3-5-sonnet-20241022"
    raw_response = "Model response here."

    # Store with one prompt version
    key1 = cache.key(content_hash, "v1", model)
    cache.put(key1, raw_response)

    # Try to retrieve with a different prompt version
    key2 = cache.key(content_hash, "v2", model)
    result = cache.get(key2)

    # Should miss because different prompt_version creates different key
    assert result is None


def test_get_never_written_key_returns_none(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    result = cache.get("nonexistent_key")
    assert result is None
