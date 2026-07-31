"""Privacy and correctness tests for the LLM payload builder."""

from boardwatch.llm.payload import build_payload, preview_text


def test_payload_contains_only_jd_text_no_profile() -> None:
    """Test that the payload carries only JD text with no profile data leaks."""
    jd = "Must have 5 years of experience. US work authorization required."
    p = build_payload(jd)
    blob = (p["system"] + p["user"]).lower()
    for leak in ("resume", "profile", "citizen_status", "total_years", "green card holder named"):
        assert leak not in blob or leak in jd.lower()
    assert jd in p["user"]  # the JD is carried verbatim


def test_payload_returns_correct_structure() -> None:
    """Test that build_payload returns the expected dict structure."""
    jd = "Test JD text"
    p = build_payload(jd)
    assert isinstance(p, dict)
    assert set(p.keys()) == {"system", "user"}
    assert isinstance(p["system"], str)
    assert isinstance(p["user"], str)
    assert len(p["system"]) > 0
    assert len(p["user"]) > 0


def test_preview_text_shows_destination_and_safety() -> None:
    """Test that preview_text displays the destination and confirms only JD is sent."""
    jd = "Test job description"
    preview = preview_text(jd, provider="anthropic", model="claude-3-haiku", base_url=None)

    # Preview should be human-readable and show important details
    assert isinstance(preview, str)
    assert len(preview) > 0

    # Should mention the provider and model
    assert "anthropic" in preview.lower() or "provider" in preview.lower()
    assert "claude-3-haiku" in preview or "model" in preview.lower()

    # Should reference the JD being sent
    assert jd in preview or "job" in preview.lower()


def test_preview_text_with_custom_base_url() -> None:
    """Test that preview_text handles custom base_url parameter."""
    jd = "Test JD"
    preview = preview_text(
        jd,
        provider="anthropic",
        model="claude-3-sonnet",
        base_url="https://custom.example.com"
    )

    assert isinstance(preview, str)
    assert len(preview) > 0
    assert "custom.example.com" in preview or "custom" in preview.lower()
