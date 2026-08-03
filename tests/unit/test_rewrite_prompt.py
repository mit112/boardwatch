from boardwatch.tailor.rewrite.prompt import (
    JUDGE_PROMPT_VERSION,
    REWRITE_PROMPT_VERSION,
    build_judge_payload,
    build_rewrite_payload,
)


def test_rewrite_payload_carries_bullet_and_skills():
    p = build_rewrite_payload("Built the service in Python", {"Kubernetes", "Go"})
    assert "system" in p and "user" in p
    assert "Built the service in Python" in p["user"]
    assert "Go" in p["user"] and "Kubernetes" in p["user"]


def test_judge_payload_is_blind_to_jd():
    p = build_judge_payload("Built the service in Python", "Shipped the service in Python")
    assert "Built the service in Python" in p["user"]
    assert "Shipped the service in Python" in p["user"]
    # The judge must never see JD context — only A and B.
    assert "jd" not in p["user"].lower() and "job description" not in p["user"].lower()


def test_rewrite_payload_renders_empty_skills():
    p = build_rewrite_payload("Built it", set())
    assert "(none)" in p["user"]


def test_version_strings_locked():
    assert REWRITE_PROMPT_VERSION == "p7b-rewrite-1"
    assert JUDGE_PROMPT_VERSION == "p7b-judge-1"
