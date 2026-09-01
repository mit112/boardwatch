"""boardwatch config show|set (§2.3, D17). Validates against the supported-key table;
writes config.toml via tomli-w (stdlib has no writer), round-tripping the raw dict so a
user's unknown-but-harmless keys survive a set."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from typing import Any

import tomli_w
import typer
from pydantic import BaseModel, ValidationError
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.core.features import FEATURE_BY_KEY, SETTABLE_FEATURE_KEYS
from boardwatch.core.secrets import LLM_API_KEY_ENV, resolve_secret
from boardwatch.core.settings import LLMTier, NotifyTier, Settings, load_settings
from boardwatch.notify.webhook import WEBHOOK_URL_ENV

config_app = typer.Typer(no_args_is_help=True, help="Show or change settings.")
console = Console()


def _lane_names(raw: str) -> list[str]:
    """`lanes_enabled` from one CLI string. A LIST, not a tuple: this value is written straight
    into config.toml by `tomli_w`, which has no tuple form. Pydantic coerces it back on load.

    Blank (and any all-whitespace entry) disarms every lane rather than registering a lane
    named "", which would then be reported as unknown on every run.
    """
    return [part.strip() for part in raw.split(",") if part.strip()]


def _search_hubs(raw: str) -> list[str]:
    """`lane_search_hubs` from one CLI string, as a JSON array.

    **NOT comma-separated, unlike `lanes_enabled`, and that difference is the whole point.** A
    hub is a human place name and the ones LinkedIn's `location=` accepts CONTAIN a comma —
    "Austin, TX". Cast through `_lane_names` this value split into two hubs, "Austin" and "TX",
    and the lane searched two places the user never named while reporting that it had searched
    theirs. `"Austin, TX,Boston, MA"` became four. There is no separator a place name cannot
    contain, so the fix is a representation that QUOTES its elements rather than a different
    delimiter to split on.

    A LIST, not a tuple, for the same reason `_lane_names` returns one: the value is written
    straight into config.toml by `tomli_w`, which has no tuple form, and pydantic coerces it back
    to a tuple on load. That also makes the round trip exact — TOML's array of strings is the
    same shape as the JSON array accepted here.

    Blank disables hub nets, matching the inert default, rather than registering a hub named "".
    """
    text = raw.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "expected a JSON array of hub names, e.g. "
            '\'["Austin, TX", "Boston, MA"]\' (a hub name contains a comma, so a bare '
            "comma-separated list cannot express one)"
        ) from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError(
            'expected a JSON ARRAY OF STRINGS, e.g. \'["Austin, TX", "Boston, MA"]\', '
            f"got {parsed!r}"
        )
    return [item.strip() for item in parsed if item.strip()]


# key → (caster, "takes effect", units note). weights.* are nested under [weights].
# Every scalar `Settings` field except the two paths, which are CLI/env-level and not settable
# here. `test_every_scalar_setting_is_reachable_from_the_cli` asserts that exhaustively, because
# this is a hand-maintained mirror of `Settings` and it silently drifted once: `seen_ttl_days`,
# `location_filter_mode`, `reap_stale_after_hours`, `zero_skill_coverage_prior` and
# `recency_half_life_days` all shipped invisible to `config show` and unsettable by `config set`,
# while the README promised the command "prints every key". Range and enum validation happens by
# constructing a `Settings` with the new value, so a caster here only has to parse.
# Annotated because the lane-list casters return lists while every other one is a scalar type;
# without this mypy joins them to `object` and the call below stops type-checking.
def _str_to_bool(raw: str) -> bool:
    v = raw.strip().lower()
    if v in {"true", "1", "yes", "on"}:
        return True
    if v in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"expected a boolean (true/false), got {raw!r}")


_SCALAR_KEYS: dict[str, tuple[Callable[[str], Any], str, str]] = {
    "per_host_delay_seconds": (float, "next scan", "seconds, floor 0.25"),
    "pace_from_request_start": (
        _str_to_bool,
        "next scan",
        "true measures the per-host delay between request STARTS (a true 1/delay ceiling); "
        "false, the default, measures it from the previous request's END",
    ),
    "retry_attempts": (int, "next scan", "total attempts 1–10 (1 = no retry)"),
    "scan_workers": (int, "next scan", "1–8"),
    "detail_fetch_budget": (
        int, "next scan", "per-posting detail fetches per board per scan, 1–1000"
    ),
    "validator_max_age_hours": (
        int,
        "next scan",
        "hours after which a board's cached ETag/Last-Modified is dropped and refetched "
        "unconditionally, ≥1",
    ),
    "seen_ttl_days": (
        int, "next top/run", "days a surfaced-but-unbuilt lead stays suppressed, ≥1"
    ),
    "reap_stale_after_hours": (
        int, "next run", "age at which an unfinished run row is treated as crashed, ≥1"
    ),
    "location_filter_mode": (str, "next top", "soft (rank only) or hard (veto)"),
    "zero_skill_coverage_prior": (
        float, "next top", "score given when a posting lists no detectable skills, [0,1]"
    ),
    "recency_half_life_days": (float, "next top", "days at which the recency score halves"),
    "busy_timeout_ms": (int, "next command", "SQLite busy timeout in milliseconds"),
    "lanes_enabled": (
        _lane_names, "next run", "comma-separated lane names; blank disarms every lane"
    ),
    "lane_search_hubs": (
        _search_hubs,
        "next run",
        'JSON array of LinkedIn search hubs, e.g. \'["Austin, TX", "Boston, MA"]\'; '
        "blank disables hub nets",
    ),
    "lane_new_companies_per_run": (
        int, "next run", "companies one lane may ADD per run, ≥0 (already-known ones are free)"
    ),
    "lane_posting_budget": (int, "next run", "JD-body requests one lane may make per run, ≥0"),
    "lane_search_pages": (
        int,
        "next run",
        "search pages one lane requests per facet, ≥1 (1 = the single page that shipped)",
    ),
    "lane_hub_combos_per_run": (
        int, "next run", "LinkedIn term/hub combinations searched per run, ≥0"
    ),
    "lane_hub_distance_miles": (
        int, "next run", "LinkedIn hub search radius in miles, ≥0"
    ),
    # `str` and not `Path`: the value is written straight into `config.toml`, and a `Path` is not
    # TOML-serializable. `Settings` coerces it back to a `Path` on load.
    "jobapps_discovery_dir": (
        str,
        "next run",
        "absolute path to job-apps' discovery output (its APPLY_QUEUE); the jobapps lane "
        "reports an error without it",
    ),
    "jobapps_queue_dir": (
        str,
        "next run",
        "absolute path to job-apps' PROMOTED queue (APPLY_QUEUE); read in addition to "
        "jobapps_discovery_dir, because a promoted posting leaves the discovery tree",
    ),
    "death_probe_budget": (
        int,
        "next run",
        "liveness probes per run against postings no board scan enumerates, ≥0 (0 disarms it)",
    ),
    "death_probe_ttl_hours": (
        int, "next run", "hours before such a posting may be probed again, ≥1"
    ),
}
_WEIGHT_KEYS = {"skill_coverage", "title_match", "recency", "location_fit"}


# notify.* live under [notify]; both are booleans, take effect on next notify.
_NOTIFY_KEYS = {
    "notify.desktop_enabled": "next notify",
    "notify.webhook_enabled": "next notify",
}

_SECRET_LEAF_NAMES = frozenset({"api_key", "token", "secret", "password", "webhook_url"})


def _is_secret_key(name: str) -> bool:
    return name in _SECRET_LEAF_NAMES or name.endswith("_api_key")


def _find_secret_key(raw: dict[str, Any], prefix: str = "") -> str | None:
    """Dotted path of the first reserved secret key at any depth in raw, or None.
    Recurses through nested tables (dict) and arrays-of-tables (list). Returns a PATH
    only, never a value (secrets contract, P0-3 D-P0-3-5)."""
    for key, value in raw.items():
        path = f"{prefix}{key}"
        if _is_secret_key(key):
            return path
        found = _find_secret_in_value(value, path)
        if found is not None:
            return found
    return None


def _find_secret_in_value(value: Any, path: str) -> str | None:
    """Walk a config value for a reserved secret key; returns a PATH or None, never a value."""
    if isinstance(value, dict):
        return _find_secret_key(value, f"{path}.")
    if isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_secret_in_value(item, f"{path}[{index}]")
            if found is not None:
                return found
    return None


_TIER_MODELS: dict[str, type[BaseModel]] = {"llm": LLMTier, "notify": NotifyTier}


class SecretInConfig(Exception):
    """config.toml already contains a reserved secret key; refuse to reserialize it."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


def toggle_feature(settings: Settings, key: str, on: bool) -> tuple[bool, bool]:
    """Persist a boolean feature toggle to config.toml. Shared by `config set` and
    `settings toggle` so the secret guard, validation, and build_context side effect never
    diverge. Returns (old, new). Raises SecretInConfig if config.toml already holds a secret."""
    config_file = settings.config_dir / "config.toml"
    raw = tomllib.loads(config_file.read_text(encoding="utf-8")) if config_file.is_file() else {}
    existing = _find_secret_key(raw)
    if existing is not None:
        raise SecretInConfig(existing)
    table, leaf = key.split(".", 1)
    old = FEATURE_BY_KEY[key].read(settings)
    _TIER_MODELS[table](**{**getattr(settings, table).model_dump(), leaf: on})  # validation
    raw.setdefault(table, {})[leaf] = on
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_bytes(tomli_w.dumps(raw).encode("utf-8"))  # round-trips unknown keys
    build_context(settings.data_dir)  # parity with other commands
    return old, on


@config_app.command("show")
def show(ctx: typer.Context) -> None:
    settings = load_settings(data_dir=ctx.obj)
    defaults = Settings(data_dir=settings.data_dir, config_dir=settings.config_dir)
    for key, (_caster, effect, units) in _SCALAR_KEYS.items():
        cur, dflt = getattr(settings, key), getattr(defaults, key)
        console.print(f"{key} = {cur} (default {dflt}; {units}; {effect})")
    for key in sorted(_WEIGHT_KEYS):
        cur, dflt = getattr(settings.weights, key), getattr(defaults.weights, key)
        console.print(f"weights.{key} = {cur} (default {dflt}; [0,1]; next top)")
    llm = settings.llm
    console.print(
        f"llm.enabled = {llm.enabled} (opt-in LLM tier; provider={llm.provider}, model={llm.model})"
    )
    console.print(f"llm.eligibility_extraction = {llm.eligibility_extraction}")
    console.print(f"llm.resume_tailoring = {llm.resume_tailoring}")
    console.print(f"llm.resume_tailoring_via_agent = {llm.resume_tailoring_via_agent}")
    console.print(f"llm.max_calls_per_run = {llm.max_calls_per_run} (default 50; ≥1)")
    present = "set" if resolve_secret(LLM_API_KEY_ENV) is not None else "unset"
    console.print(f"llm.api_key: {present} (via {LLM_API_KEY_ENV})")
    for key, effect in _NOTIFY_KEYS.items():
        leaf = key.split(".", 1)[1]
        cur = getattr(settings.notify, leaf)
        dflt = getattr(defaults.notify, leaf)
        console.print(f"{key} = {cur} (default {dflt}; true/false; {effect})")
    present = "set" if resolve_secret(WEBHOOK_URL_ENV) is not None else "unset"
    console.print(f"notify.webhook_url: {present} (via {WEBHOOK_URL_ENV})")


@config_app.command("set")
def set_(ctx: typer.Context, key: str, value: str) -> None:
    settings = load_settings(data_dir=ctx.obj)
    config_file = settings.config_dir / "config.toml"
    raw = tomllib.loads(config_file.read_text(encoding="utf-8")) if config_file.is_file() else {}

    existing_secret = _find_secret_key(raw)
    if existing_secret is not None:
        console.print(
            f"[red]refusing to write: config.toml must not contain secrets; found "
            f"reserved key {existing_secret!r}. Remove it and put credentials in the "
            f"environment instead (e.g. {LLM_API_KEY_ENV} or {WEBHOOK_URL_ENV}).[/red]"
        )
        raise typer.Exit(code=1)
    if _is_secret_key(key.rsplit(".", 1)[-1]):
        console.print(
            f"[red]secrets do not belong in config.toml; set the matching environment "
            f"variable instead of {key!r} (e.g. {LLM_API_KEY_ENV} or {WEBHOOK_URL_ENV}).[/red]"
        )
        raise typer.Exit(code=1)
    # Settable boolean features (the four live llm.* booleans + notify.*): one shared writer.
    if key in SETTABLE_FEATURE_KEYS:
        try:
            new_bool = _str_to_bool(value)
        except ValueError as exc:
            console.print(f"[red]invalid value for {key}: {exc}[/red]")
            raise typer.Exit(code=1) from exc
        try:
            old_bool, new_bool = toggle_feature(settings, key, new_bool)
        except SecretInConfig as exc:
            console.print(
                f"[red]refusing to write: config.toml must not contain secrets; found "
                f"reserved key {exc.path!r}. Put credentials in the environment instead "
                f"(e.g. {LLM_API_KEY_ENV} or {WEBHOOK_URL_ENV}).[/red]"
            )
            raise typer.Exit(code=1) from exc
        console.print(f"{key}: {old_bool} → {new_bool}")
        return

    if key == "llm.max_calls_per_run":
        old = settings.llm.max_calls_per_run
        try:
            # `list[str]` is here for the list-valued lane keys in `_SCALAR_KEYS`.
            new: int | float | list[str] = int(value)
            LLMTier(**{**settings.llm.model_dump(), "max_calls_per_run": new})  # ge=1 check
        except (ValueError, ValidationError) as exc:
            console.print(f"[red]invalid value for {key}: {exc}[/red]")
            raise typer.Exit(code=1) from exc
        raw.setdefault("llm", {})["max_calls_per_run"] = new
    elif key == "llm" or key.startswith("llm."):
        console.print(
            f"[red]{key!r} is not a toggle; edit config.toml directly "
            f"(provider/model/base_url).[/red]"
        )
        raise typer.Exit(code=1)
    elif key in _SCALAR_KEYS:
        caster, _e, _u = _SCALAR_KEYS[key]
        old = getattr(settings, key)
        try:
            new = caster(value)
            # construct Settings with the new value → the Field(ge/le) range check fires
            Settings(data_dir=settings.data_dir, config_dir=settings.config_dir, **{key: new})
        except (ValueError, ValidationError) as exc:
            console.print(f"[red]invalid value for {key}: {exc}[/red]")
            raise typer.Exit(code=1) from exc
        raw[key] = new
    elif key.startswith("weights.") and key.split(".", 1)[1] in _WEIGHT_KEYS:
        from boardwatch.core.settings import RankWeights

        leaf = key.split(".", 1)[1]
        old = getattr(settings.weights, leaf)
        try:
            new = float(value)
            RankWeights(**{**settings.weights.model_dump(), leaf: new})  # [0,1] range check
        except (ValueError, ValidationError) as exc:
            console.print(f"[red]invalid value for {key}: {exc}[/red]")
            raise typer.Exit(code=1) from exc
        raw.setdefault("weights", {})[leaf] = new
    else:
        console.print(f"[red]unknown key {key!r}[/red]")
        raise typer.Exit(code=1)

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_bytes(tomli_w.dumps(raw).encode("utf-8"))  # round-trips unknown keys
    console.print(f"{key}: {old} → {new}")
    build_context(ctx.obj)  # ensure the data dir/schema exist (parity with other commands)
