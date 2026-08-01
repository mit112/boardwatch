from boardwatch.core.settings import LLMTier


def test_llmtier_defaults_are_off_and_keyless():
    t = LLMTier()
    assert t.enabled is False and t.eligibility_extraction is False
    assert t.base_url is None and t.max_calls_per_run == 50


def test_llmtier_carries_no_secret_field():
    # the credential must never be a config field (P0-3)
    assert "api_key" not in LLMTier.model_fields and "key" not in LLMTier.model_fields
