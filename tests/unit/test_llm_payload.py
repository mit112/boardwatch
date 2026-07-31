"""Privacy and correctness tests for the LLM payload builder."""

import inspect

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
    """Test that preview_text threads real provider, model, JD, and safety message."""
    jd = "Senior engineer with Python and distributed systems experience"
    preview = preview_text(
        jd, provider="anthropic", model="claude-3-haiku", base_url=None
    )

    # Preview must be human-readable
    assert isinstance(preview, str)
    assert len(preview) > 0

    # Actual values must be threaded through, not just boilerplate labels
    assert "anthropic" in preview
    assert "claude-3-haiku" in preview
    assert jd in preview  # Distinctive JD content must appear verbatim

    # Safety message must be the exact sentence from preview_text
    assert "No profile, resume, or eligibility data is included." in preview


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


def test_build_payload_signature_admits_only_jd_text() -> None:
    """Lock the privacy contract: build_payload takes ONLY jd_text parameter.

    This structural guard prevents accidental widening (e.g., adding profile=)
    that could leak profile data to the LLM. The signature is the primary
    privacy enforcement mechanism.
    """
    params = list(inspect.signature(build_payload).parameters)
    assert params == ["jd_text"]
