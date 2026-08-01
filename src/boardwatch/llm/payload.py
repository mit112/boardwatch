"""Build and preview LLM payloads for safe JD extraction.

This module constructs the system and user prompts for JD analysis and provides
a human-readable preview for verification. It is the privacy boundary of the
extraction feature: build_payload takes only JD text, never profile data.
"""

from __future__ import annotations

from boardwatch.llm.prompt import EXTRACTION_SYSTEM, render_user


def build_payload(jd_text: str) -> dict[str, str]:
    """Build a system+user payload for JD extraction.

    Takes only the job description text. This signature ensures profile data
    cannot accidentally leak to the LLM.

    Args:
        jd_text: The job description text to extract from.

    Returns:
        A dict with "system" and "user" keys, both strings.
    """
    return {
        "system": EXTRACTION_SYSTEM,
        "user": render_user(jd_text),
    }


def preview_text(
    jd_text: str,
    *,
    provider: str,
    model: str,
    base_url: str | None,
) -> str:
    """Generate a human-readable preview of the extraction request.

    Used for --dry-run and first-use verification to show the user exactly
    what will be sent to the LLM provider.

    Args:
        jd_text: The job description text.
        provider: The LLM provider name (e.g., "anthropic", "openai").
        model: The model identifier (e.g., "claude-3-haiku", "gpt-4-turbo").
        base_url: Optional custom API endpoint, or None for the provider default.

    Returns:
        A formatted string showing the destination and payload summary.
    """
    url_display = base_url if base_url else f"(default {provider} endpoint)"

    lines = [
        "Extraction Request Preview",
        "=" * 50,
        "",
        "Destination:",
        f"  Provider: {provider}",
        f"  Model: {model}",
        f"  URL: {url_display}",
        "",
        "Payload contents:",
        "  - System prompt: Instructs extraction of requirement patterns",
        "  - User message: Job description (copied below)",
        "",
        "Job description:",
        "-" * 50,
        jd_text,
        "-" * 50,
        "",
        "Privacy note: Only the job description above will be sent to the LLM.",
        "No profile, resume, or eligibility data is included.",
    ]
    return "\n".join(lines)
