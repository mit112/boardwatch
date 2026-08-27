"""Settings: config/data locations (§2.4) and documented defaults (D17, §3.4).

Path precedence:
  data_dir:   CLI --data-dir > config.toml data_dir > BOARDWATCH_DATA_DIR > platformdirs
  config_dir: BOARDWATCH_CONFIG_DIR > platformdirs
Config file: {config_dir}/config.toml; weights and politeness knobs are read at call
time per D17, so there is no caching layer to invalidate.

Secrets contract (P0-3): config.toml is the shareable config and never holds secrets.
Credentials come only from the environment (the opt-in LLM tier reads
BOARDWATCH_LLM_API_KEY); see core.secrets.resolve_secret. A persistent-secret file is
reserved at {config_dir}/secrets.toml but is not read yet. The opt-in LLM tier is off
by default; see core.features for the user-facing surface.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from platformdirs import user_config_dir, user_data_dir
from pydantic import BaseModel, ConfigDict, Field

APP_NAME = "boardwatch"


class RankWeights(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_coverage: float = Field(default=0.50, ge=0.0, le=1.0)
    title_match: float = Field(default=0.25, ge=0.0, le=1.0)
    recency: float = Field(default=0.15, ge=0.0, le=1.0)
    location_fit: float = Field(default=0.10, ge=0.0, le=1.0)


class LLMTier(BaseModel):
    """Opt-in LLM tier config (D11, §5.1). Off by default; opt-in.

    Carries only non-secret knobs; the credential is never a field here (it comes from
    the environment via core.secrets), which keeps secrets out of every serialize path.
    Includes extraction knobs (eligibility_extraction, base_url) and call budgets
    (max_calls_per_run). max_calls_per_run bounds calls per invocation of the eligibility
    lane and per résumé in the tailor lane — it is not a per-run total (D-146).
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    provider: str | None = None  # e.g. "anthropic" | "openai"; provider-neutral
    model: str | None = None
    base_url: str | None = None
    eligibility_extraction: bool = False
    resume_tailoring: bool = False
    resume_tailoring_via_agent: bool = False  # gates subscription Tier B; no API key needed
    max_calls_per_run: int = Field(default=50, ge=1)


class NotifyTier(BaseModel):
    """Delivery channels for `boardwatch notify` (P5). Off by default; enabling a
    channel is the user's explicit opt-in to outbound delivery. The webhook URL is
    NOT a field here — it is a secret and comes only from the environment
    (BOARDWATCH_NOTIFY_WEBHOOK_URL) via core.secrets."""

    model_config = ConfigDict(frozen=True)

    desktop_enabled: bool = False
    webhook_enabled: bool = False


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_dir: Path
    config_dir: Path
    per_host_delay_seconds: float = Field(default=1.0, ge=0.25)  # §3.4 floor
    retry_attempts: int = Field(default=3, ge=1, le=10)          # total attempts; 1 = no retry
    busy_timeout_ms: int = 5000
    # A `running` row this old with no terminal status is a crashed/killed run, not one still
    # in flight (P3 slice 2, D-046). Age-based because `runs` carries no pid/heartbeat column.
    reap_stale_after_hours: int = Field(default=24, ge=1)
    scan_workers: int = Field(default=4, ge=1, le=8)
    # Multi-endpoint providers (SmartRecruiters) need one detail request per UNSEEN
    # posting because their list carries no bodies. Bounds a first scan of a large
    # board; exceeding it yields a partial snapshot, never a silent truncation.
    detail_fetch_budget: int = Field(default=50, ge=1, le=1000)
    # Force periodic revalidation of watched boards: a cached conditional-request validator
    # (ETag / Last-Modified) older than this is dropped, so the next scan refetches
    # unconditionally instead of trusting a possibly-stale upstream ETag forever. Without it a
    # server that keeps echoing the same validator yields silent 304s and permanently frozen
    # postings, with no self-healing path.
    validator_max_age_hours: int = Field(default=24, ge=1)
    recency_half_life_days: float = 14.0
    # How long a job stays suppressed after being surfaced as a lead without a deliverable
    # being produced (P6 slice 2). The TTL is itself a drain: a job you were shown and did not
    # act on re-enters the shortlist after this, in case you missed it or the JD moved.
    # `built`/`skipped` are permanent and are not governed by this.
    seen_ttl_days: int = Field(default=7, ge=1)
    location_filter_mode: Literal["soft", "hard"] = "soft"
    # Coverage imputed when a posting has no recognized skills at all (§3.6). Dropping
    # the component instead redistributes its 0.50 weight to whatever else scored well,
    # which is the "free 1" §3.6 forbids just as much as a punitive 0. The midpoint of
    # the component's own range needs no corpus statistic, so it stays D17-compatible.
    zero_skill_coverage_prior: float = Field(default=0.50, ge=0.0, le=1.0)
    # The JD-acquisition lanes the pipeline runs after the scan stage, by name. A LIST rather
    # than a boolean so lanes 2..N need another name here and never another flag.
    #
    # **Empty is not caution, it is Gate P3.** The gate needs 7 consecutive clean SCHEDULED
    # ticks; the live count belongs in STATE.md, not here, because a number in a comment goes
    # stale silently (this one read "0 of 7" while the store said 5). A lane is an unproven
    # network dependency against a host
    # nobody here operates, so arming one in the daily driver puts the streak at risk and buys
    # nothing the gate measures — the lane can be exercised by a manual `boardwatch run`, which
    # does not touch the counter. Arm it after a scratch run proves it, which is the same
    # build-then-arm order every prior network feature used.
    lanes_enabled: tuple[str, ...] = ()
    # How many companies a lane may add to the store per run, matching
    # `lanes.admission.DEFAULT_NEW_COMPANIES_PER_RUN`. "Breadth is last": a lane that reads an
    # aggregator sees thousands of employers, and adding a company's whole board is breadth, so
    # every addition is capped and both sides of the cap are reported. A company the store
    # ALREADY holds is admitted free and is not charged here — the cap counts reach added.
    lane_new_companies_per_run: int = Field(default=10, ge=0)
    # Hard ceiling on JD-body requests one lane may make in one run. A body costs one GET, so
    # this is the lane's whole network cost.
    #
    # Floor of 1, NOT 0. A budget of 0 admits companies and then records every one of their
    # postings `not_attemptable`, which makes `attempted > 0` with `resolved == 0` — the exact
    # signature of `AcquisitionTally.is_silent_outage`. Every run would print SILENT OUTAGE
    # while behaving as configured, which is the cry-wolf failure that predicate's own
    # docstring exists to avoid. Disarming a lane is what `lanes_enabled` is for.
    lane_posting_budget: int = Field(default=60, ge=1)
    # D-325 — the measured-death sweep. `postings` under a company with `watched = 0` get no
    # absence signal from any board scan (D-314), so the only evidence available is the stored
    # URL answering 404/410 twice. Both knobs bound the COST of asking, never the verdict.
    #
    # A probe costs ~0.97 s, so the budget is the sweep's whole run-time contribution: 50 probes
    # is under a minute, and at the daily driver's ~3 h cadence that is ~400 rows a day against
    # a class growing ~182/day. Floor of 0, and 0 is a real setting — it disarms the sweep while
    # still reporting the whole due population as `budget_refused`, so a disarmed check reads as
    # refused work rather than as a clean corpus.
    death_probe_budget: int = Field(default=50, ge=0)
    # How long a probed row is left alone. 24 h means a posting is asked about once a day
    # whatever the run cadence, which is what keeps the budget spread across the class instead
    # of re-asking the same head every three hours.
    death_probe_ttl_hours: int = Field(default=24, ge=1)
    weights: RankWeights = Field(default_factory=RankWeights)
    llm: LLMTier = Field(default_factory=LLMTier)
    notify: NotifyTier = Field(default_factory=NotifyTier)


def default_config_dir() -> Path:
    env = os.environ.get("BOARDWATCH_CONFIG_DIR")
    return Path(env) if env else Path(user_config_dir(APP_NAME))


def default_data_dir() -> Path:
    env = os.environ.get("BOARDWATCH_DATA_DIR")
    return Path(env) if env else Path(user_data_dir(APP_NAME))


def load_settings(data_dir: Path | None = None) -> Settings:
    config_dir = default_config_dir()
    raw: dict[str, Any] = {}
    config_file = config_dir / "config.toml"
    if config_file.is_file():
        raw = tomllib.loads(config_file.read_text(encoding="utf-8"))
    raw.pop("config_dir", None)
    file_data_dir = raw.pop("data_dir", None)
    resolved = data_dir or (Path(str(file_data_dir)) if file_data_dir else default_data_dir())
    return Settings(data_dir=resolved, config_dir=config_dir, **raw)
