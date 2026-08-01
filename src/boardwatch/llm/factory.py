"""Build the configured LLM adapter, or opt the caller out of the lane entirely.

The opt-in LLM tier (D11, §5.1) is off by default and degrades to nothing rather than
raising whenever a prerequisite is missing at RUNTIME (disabled, or no credential in
the environment): callers get `None` back and fall through to the deterministic lane
alone. A missing `model`/`base_url` while the tier is explicitly enabled is a
CONFIGURATION mistake, not a runtime absence, so that path raises instead of degrading
silently.
"""

from __future__ import annotations

from boardwatch.core.secrets import LLM_API_KEY_ENV, resolve_secret
from boardwatch.core.settings import Settings
from boardwatch.llm.anthropic import AnthropicClient
from boardwatch.llm.client import ModelClient
from boardwatch.llm.openai_compat import OpenAICompatClient


def build_client(settings: Settings) -> ModelClient | None:
    """Construct the provider adapter named by `settings.llm`, or None to skip the lane.

    Returns None when `settings.llm.enabled` is False, or when no credential is
    available via `resolve_secret(LLM_API_KEY_ENV)` (BOARDWATCH_LLM_API_KEY unset or
    blank). Both are ordinary runtime states, not errors. Once enabled with a
    credential present, a missing `model` (or, for a non-Anthropic provider, a missing
    `base_url`) is a configuration error and raises rather than degrading, so a
    misconfigured opt-in tier fails loudly instead of silently never calling out.
    """
    if not settings.llm.enabled:
        return None
    api_key = resolve_secret(LLM_API_KEY_ENV)
    if api_key is None:
        return None
    if settings.llm.provider == "anthropic":
        if settings.llm.model is None:
            raise ValueError(
                "llm.model is required when llm.enabled and llm.provider == 'anthropic'"
            )
        return AnthropicClient(settings.llm.model, api_key)
    if settings.llm.base_url is None or settings.llm.model is None:
        raise ValueError(
            "llm.base_url and llm.model are required when llm.enabled and "
            "llm.provider is not 'anthropic'"
        )
    return OpenAICompatClient(settings.llm.base_url, settings.llm.model, api_key)
