"""Pinned defaults. Changing any value here is a deliberate, reviewed act.

The class labels are reviewer guidance, not a filter: everything is snapshotted,
because letting the author classify a field decides whether it gets scrutiny, and
that is the judgment call this system is designed not to rely on. A 'preference'
change deserves the question "is this neutral, or is it one user's taste?".
"""

from __future__ import annotations

EXPECTED_SETTINGS_DEFAULTS: dict[str, object] = {
    "Settings.data_dir": "REQUIRED",
    "Settings.config_dir": "REQUIRED",
    "Settings.per_host_delay_seconds": 1.0,
    "Settings.retry_attempts": 3,
    "Settings.busy_timeout_ms": 5000,
    "Settings.scan_workers": 4,
    "Settings.recency_half_life_days": 14.0,
    "Settings.location_filter_mode": "soft",
    "Settings.weights": {
        "skill_coverage": 0.5,
        "title_match": 0.25,
        "recency": 0.15,
        "location_fit": 0.1,
    },
    "Settings.llm": {
        "enabled": False,
        "provider": None,
        "model": None,
        "base_url": None,
        "eligibility_extraction": False,
        "max_calls_per_run": 50,
    },
    "RankWeights.skill_coverage": 0.5,
    "RankWeights.title_match": 0.25,
    "RankWeights.recency": 0.15,
    "RankWeights.location_fit": 0.1,
    "LLMTier.enabled": False,
    "LLMTier.provider": None,
    "LLMTier.model": None,
    "LLMTier.base_url": None,
    "LLMTier.eligibility_extraction": False,
    "LLMTier.max_calls_per_run": 50,
}

SETTINGS_FIELD_CLASS: dict[str, str] = {
    "Settings.data_dir": "path",
    "Settings.config_dir": "path",
    "Settings.per_host_delay_seconds": "operational",
    "Settings.retry_attempts": "operational",
    "Settings.busy_timeout_ms": "operational",
    "Settings.scan_workers": "operational",
    "Settings.recency_half_life_days": "preference",
    "Settings.location_filter_mode": "preference",
    "Settings.weights": "preference",
    "Settings.llm": "capability",
    "RankWeights.skill_coverage": "preference",
    "RankWeights.title_match": "preference",
    "RankWeights.recency": "preference",
    "RankWeights.location_fit": "preference",
    "LLMTier.enabled": "capability",
    "LLMTier.provider": "capability",
    "LLMTier.model": "capability",
    "LLMTier.base_url": "capability",
    "LLMTier.eligibility_extraction": "capability",
    "LLMTier.max_calls_per_run": "operational",
}

# Preference-bearing parameter defaults, which live outside the settings models.
# score_posting.half_life_days duplicates Settings.recency_half_life_days.
EXPECTED_PARAM_DEFAULTS: dict[str, str] = {
    "score_posting.half_life_days": "14.0",
}

# The init wizard's prompt defaults, in source order. Every profile and filter
# prompt must stay empty: a default here would be one user's answer shipped to all.
# Each entry is the LITERAL source spelling of the prompt/default (via
# ast.get_source_segment), not an ast.unparse rendering: unparse re-quotes nested-quote
# f-strings differently across CPython patch releases and made this snapshot flake on CI.
EXPECTED_INIT_PROMPTS: tuple[tuple[str, str, str | None], ...] = (
    ("prompt", '"Companies: [1] Starter set  [2] Search registry  [3] Paste slugs/URLs"', '"1"'),
    ("prompt", '"Search registry"', None),
    ("confirm", 'f"Watch {e.name} ({e.provider}:{e.slug})?"', "True"),
    ("prompt", '"Paste slugs or board URLs (comma/newline separated)"', None),
    ("prompt", '"Profile text (paste resume text or a short profile)"', None),
    ("prompt", '"Target titles (comma separated, blank for none)"', '""'),
    ("prompt", '"Exclude titles (comma separated, blank for none)"', '""'),
    ("prompt", '"Locations (comma separated, blank for none)"', '""'),
    ("confirm", '"Remote only?"', "False"),
    # Task 11: the three catalog-driven eligibility prompts. Two prompt call sites plus one
    # confirm cover every family, so this count stays constant as the catalog grows (D-P2-8).
    # The policy default is the NAME family.default_policy, so no user value is pinned here.
    ("confirm", '"Set up eligibility checks now?"', "False"),
    ("prompt", 'f"{family.question} [{field_spec.name}: {choice_hint}]"', '""'),
    ("prompt", 'f"How should {family.label} affect your results?"', "family.default_policy"),
)
