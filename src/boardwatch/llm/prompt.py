"""Versioned extraction prompt and payload construction for LLM processing.

This module provides the instruction set and rendering logic for extracting
requirement patterns from job descriptions. The prompt version allows safe
evolution of extraction rules without breaking backward compatibility.
"""

from __future__ import annotations

# Version identifier for the extraction prompt. Increment when changing the
# instruction logic or response format expectations.
PROMPT_VERSION: str = "p3-extract-2"

# System instruction for the extraction task. Instructs the model to identify
# and return requirement patterns found in a job description.
EXTRACTION_SYSTEM: str = """You extract requirement patterns from job descriptions.
Return a JSON array. Each element has exactly two keys:
- "family": one of work_auth, experience_years, clearance, degree, contract_not_fte,
  internship, student_status, other
- "span_quote": a verbatim substring from the job description

Rules:
- Return only the JSON array, no prose or explanation
- "span_quote" must be copied exactly from the posting, word for word
- Include only patterns you find in the text; do not invent or paraphrase
- Use the correct family for each pattern
- If the posting has no matching patterns, return an empty array []

Example:
Input: "Must have 10 years of software experience and US work authorization"
Output:
[
  {"family": "experience_years", "span_quote": "10 years of software experience"},
  {"family": "work_auth", "span_quote": "US work authorization"}
]
"""


def render_user(jd_text: str) -> str:
    """Wrap the job description for the user message.

    Args:
        jd_text: The job description text to extract patterns from.

    Returns:
        A prompt string wrapping the JD for the user turn.
    """
    return f"""Extract requirement patterns from this job description:

{jd_text}"""
