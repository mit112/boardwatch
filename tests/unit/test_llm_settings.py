from boardwatch.core.settings import LLMTier, Settings


def test_llmtier_defaults_are_off_and_keyless():
    t = LLMTier()
    assert t.enabled is False and t.eligibility_extraction is False
    assert t.base_url is None and t.max_calls_per_run == 50


def test_llmtier_carries_no_secret_field():
    # the credential must never be a config field (P0-3)
    assert "api_key" not in LLMTier.model_fields and "key" not in LLMTier.model_fields


def test_agent_tier_b_flag_defaults_false_and_needs_no_api_key(tmp_path):
    s = Settings(data_dir=tmp_path, config_dir=tmp_path)
    assert s.llm.resume_tailoring_via_agent is False
    s2 = Settings(data_dir=tmp_path, config_dir=tmp_path, llm={"resume_tailoring_via_agent": True})
    assert s2.llm.resume_tailoring_via_agent is True
    assert s2.llm.enabled is False  # agent lane independent of API-key lane
