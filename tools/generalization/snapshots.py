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
    "Settings.pace_from_request_start": False,
    "Settings.retry_attempts": 3,
    "Settings.busy_timeout_ms": 5000,
    "Settings.reap_stale_after_hours": 24,
    "Settings.scan_workers": 4,
    "Settings.detail_fetch_budget": 50,
    # A revalidation bound, not a preference: after this many hours a board's cached ETag/
    # Last-Modified is dropped and refetched unconditionally, so a permanently-stale upstream
    # validator cannot freeze a board forever. 24 is neutral — one day caps the silent-staleness
    # window at a natural period and says nothing about roles, geography or field.
    "Settings.validator_max_age_hours": 24,
    "Settings.recency_half_life_days": 14.0,
    # How long a surfaced-but-unbuilt job stays suppressed (P6 slice 2). 7 is neutral: one
    # week is the shortest period that outlives a single work week, so a job shown on Monday
    # is not re-served on Tuesday and is not withheld past the next weekly review. It encodes
    # no preference about roles, seniority, geography or field.
    "Settings.seen_ttl_days": 7,
    "Settings.location_filter_mode": "soft",
    "Settings.zero_skill_coverage_prior": 0.50,
    # Empty ships every lane OFF. Neutral by construction — a lane is an unproven network
    # dependency, and an empty list encodes no view about roles, geography or field.
    "Settings.lanes_enabled": (),
    # How many companies a lane may ADD per run, and how many JD bodies it may fetch. Both are
    # caps on acquisition cost, not preferences: they bound the request budget against a host
    # nobody here operates and say nothing about which postings are wanted.
    "Settings.lane_new_companies_per_run": 10,
    # Per-lane override of the cap above. `jobapps` ships uncapped: its whole source tree caps
    # out around 38-45 companies total, so a cap buys nothing but slows reach for a lane an
    # operator already curates. Not neutral in the "says nothing about roles/geography/field"
    # sense the other lane knobs are — it names a SPECIFIC lane — but it is still an acquisition
    # cost knob, not a ranking preference, which is the axis this table classifies on.
    "Settings.lane_new_companies_per_run_overrides": {"jobapps": "unlimited"},
    "Settings.lane_posting_budget": 60,
    # Search pages per facet. 1 is the neutral default because it is the behaviour that shipped:
    # it adds no request to any existing user's run and encodes no view about roles, seniority,
    # geography or field — only how deep into a result set an operator has chosen to read.
    "Settings.lane_search_pages": 1,
    # D-385. A machine-local path with no neutral default: any value here would be one
    # operator's filesystem. None ships the `jobapps` lane inert, and it encodes no view about
    # roles, seniority, geography or field.
    "Settings.jobapps_discovery_dir": None,
    # D-325. Caps on how much the measured-death sweep may ASK, not on what it may conclude:
    # 50 probes is under a minute of a run, and 24 hours is one natural period between asking
    # the same posting twice. Neutral by construction — neither says anything about roles,
    # seniority, geography or field, and a run reports both sides of the budget either way.
    "Settings.death_probe_budget": 50,
    "Settings.death_probe_ttl_hours": 24,
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
        "resume_tailoring": False,
        "resume_tailoring_via_agent": False,
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
    "LLMTier.resume_tailoring": False,
    "LLMTier.resume_tailoring_via_agent": False,
    "LLMTier.max_calls_per_run": 50,
    "Settings.notify": {
        "desktop_enabled": False,
        "webhook_enabled": False,
    },
    "NotifyTier.desktop_enabled": False,
    "NotifyTier.webhook_enabled": False,
}

SETTINGS_FIELD_CLASS: dict[str, str] = {
    "Settings.data_dir": "path",
    "Settings.config_dir": "path",
    "Settings.per_host_delay_seconds": "operational",
    "Settings.pace_from_request_start": "operational",
    "Settings.retry_attempts": "operational",
    "Settings.busy_timeout_ms": "operational",
    "Settings.reap_stale_after_hours": "operational",
    "Settings.scan_workers": "operational",
    "Settings.detail_fetch_budget": "operational",
    "Settings.validator_max_age_hours": "operational",
    "Settings.recency_half_life_days": "preference",
    "Settings.seen_ttl_days": "preference",
    "Settings.location_filter_mode": "preference",
    "Settings.zero_skill_coverage_prior": "preference",
    "Settings.lanes_enabled": "capability",
    "Settings.lane_new_companies_per_run": "operational",
    "Settings.lane_new_companies_per_run_overrides": "operational",
    "Settings.lane_posting_budget": "operational",
    "Settings.lane_search_pages": "operational",
    "Settings.jobapps_discovery_dir": "path",
    "Settings.death_probe_budget": "operational",
    "Settings.death_probe_ttl_hours": "operational",
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
    "LLMTier.resume_tailoring": "capability",
    "LLMTier.resume_tailoring_via_agent": "capability",
    "LLMTier.max_calls_per_run": "operational",
    "Settings.notify": "capability",
    "NotifyTier.desktop_enabled": "capability",
    "NotifyTier.webhook_enabled": "capability",
}

# Preference-bearing parameter defaults, which live outside the settings models.
# score_posting.half_life_days duplicates Settings.recency_half_life_days.
EXPECTED_PARAM_DEFAULTS: dict[str, str] = {
    "score_posting.half_life_days": "14.0",
    # Duplicates Settings.zero_skill_coverage_prior. Neutral by construction: the midpoint
    # of the component's own range, chosen so it needs no corpus statistic. A 0.0 here would
    # be the punitive default §3.6 forbids, so the value is worth re-reading on any change.
    "score_posting.zero_skill_prior": "0.50",
    # Pseudo-count that shrinks skill_coverage toward zero_skill_prior. Not user-specific and
    # deliberately NOT a Settings field: reports/manifest.py hashes the ranking knobs into the
    # config hash, so a sibling setting would stale every ledger disposition and owe a drain
    # for a change that alters no verdict. 1.0 is add-one smoothing — the smallest value that
    # clears the thin-JD false positives out of the delivered slate; 0.0 restores the raw ratio.
    "score_posting.coverage_pseudo_count": "1.0",
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
    # Task 11: the catalog-driven eligibility prompts. Two prompt call sites plus one confirm
    # cover every family, so this count stays constant as the catalog grows (D-P2-8); the
    # `career_field` prompt below is a single catalog-scalar, likewise constant as its
    # vocabulary grows.
    # The policy default is the NAME family.default_policy, so no user value is pinned here.
    ("confirm", '"Set up eligibility checks now?"', "False"),
    ("prompt", 'f"Your career field [{field_hint}]"', '""'),
    ("prompt", 'f"Your field of study [{study_hint}]"', '""'),
    ("prompt", 'f"{family.question} [{field_spec.name}: {choice_hint}]"', '""'),
    ("prompt", 'f"How should {family.label} affect your results?"', "family.default_policy"),
)
