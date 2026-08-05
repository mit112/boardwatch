"""Feature registry (P11): the single source of truth for user-facing opt-in features —
what backs each one (a config key), what it does, and what it sends anywhere.

Pure data + typed accessors. No I/O, no console. `read`/`met` are typed lambdas rather than
getattr(...) so mypy --strict does not see Any. NOTE: this module must NOT be listed in
tools/generalization/defaults.py:SCOPED_MODULES — the copy here is generic product text, and
R9 would otherwise flag the module-level FEATURES tuple as a preference default.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from boardwatch.core.secrets import LLM_API_KEY_ENV, resolve_secret
from boardwatch.core.settings import Settings
from boardwatch.notify.webhook import WEBHOOK_URL_ENV


@dataclass(frozen=True)
class Prereq:
    """One prerequisite that must hold for a feature to actually run. `met` is checked
    against Settings (config keys) or the environment (secrets); it returns a plain bool."""

    label: str
    met: Callable[[Settings], bool]


@dataclass(frozen=True)
class Feature:
    """A user-facing opt-in feature backed by one boolean config key."""

    key: str
    name: str
    description: str
    sends: str
    read: Callable[[Settings], bool]
    requires: tuple[Prereq, ...] = field(default_factory=tuple)


# Shared prerequisites. Secret checks ignore the Settings arg (secrets live in the env).
_LLM_ENABLED = Prereq("llm.enabled on", lambda s: s.llm.enabled)
_LLM_KEY = Prereq(f"{LLM_API_KEY_ENV} set", lambda s: resolve_secret(LLM_API_KEY_ENV) is not None)
_LLM_MODEL = Prereq("llm.model in config.toml", lambda s: s.llm.model is not None)
_WEBHOOK_URL = Prereq(
    f"{WEBHOOK_URL_ENV} set", lambda s: resolve_secret(WEBHOOK_URL_ENV) is not None
)

_API_LANE = (_LLM_ENABLED, _LLM_KEY, _LLM_MODEL)

FEATURES: tuple[Feature, ...] = (
    Feature(
        key="llm.enabled",
        name="LLM API tier",
        description="Master switch for the API-based LLM features below.",
        sends=(
            "Off = the API features below don't call out. On, they may send text to the LLM "
            "endpoint you configure (llm.provider/llm.base_url). Does NOT cover the agent lane, "
            "scan, or webhook delivery."
        ),
        read=lambda s: s.llm.enabled,
    ),
    Feature(
        key="llm.eligibility_extraction",
        name="LLM eligibility assist",
        description="Uses an LLM to judge hard eligibility cases.",
        sends="Sends posting text to the LLM endpoint you configure.",
        read=lambda s: s.llm.eligibility_extraction,
        requires=_API_LANE,
    ),
    Feature(
        key="llm.resume_tailoring",
        name="Resume tailoring, API (Tier B)",
        description="Rewords your resume bullets for a posting via your configured LLM API.",
        sends="Sends your resume bullets and the posting to your configured LLM endpoint.",
        read=lambda s: s.llm.resume_tailoring,
        requires=_API_LANE,
    ),
    Feature(
        key="llm.resume_tailoring_via_agent",
        name="Resume tailoring, agent (Tier B)",
        description="Rewords your resume bullets using the Claude Code agent in your terminal.",
        sends=(
            "boardwatch itself makes no API call and needs no API key — but your resume bullets "
            "and the posting are handed to the Claude Code agent in your terminal, which sends "
            "them to Anthropic under your subscription."
        ),
        read=lambda s: s.llm.resume_tailoring_via_agent,
        # B1: verified against tailor_cmd.py:246/297/351 — the agent lane gates ONLY on this
        # flag and never calls build_client, so it needs neither llm.enabled nor a key.
        requires=(),
    ),
    Feature(
        key="notify.desktop_enabled",
        name="Desktop notifications",
        description="Shows a local OS notification when notify runs.",
        sends="Local OS notification. Sends nothing off your machine.",
        read=lambda s: s.notify.desktop_enabled,
    ),
    Feature(
        key="notify.webhook_enabled",
        name="Webhook notifications",
        description="POSTs your digest to a webhook (e.g. Slack/Discord) when notify runs.",
        sends=(
            f"POSTs your digest to the URL in {WEBHOOK_URL_ENV} (e.g. Slack/Discord). "
            "That URL receives your shortlist."
        ),
        read=lambda s: s.notify.webhook_enabled,
        requires=(_WEBHOOK_URL,),
    ),
)

FEATURE_BY_KEY: dict[str, Feature] = {f.key: f for f in FEATURES}
SETTABLE_FEATURE_KEYS: frozenset[str] = frozenset(FEATURE_BY_KEY)


def feature_state(feature: Feature, settings: Settings) -> bool:
    """Current on/off state of a feature (typed; no Any)."""
    return feature.read(settings)


def unmet_prerequisites(feature: Feature, settings: Settings) -> list[str]:
    """Labels of prerequisites not currently satisfied (names only, never secret values)."""
    return [p.label for p in feature.requires if not p.met(settings)]
