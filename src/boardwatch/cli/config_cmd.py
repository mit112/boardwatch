"""boardwatch config show|set (§2.3, D17). Validates against the supported-key table;
writes config.toml via tomli-w (stdlib has no writer), round-tripping the raw dict so a
user's unknown-but-harmless keys survive a set."""

from __future__ import annotations

import tomllib
from typing import Any

import tomli_w
import typer
from pydantic import ValidationError
from rich.console import Console

from boardwatch.cli.context import build_context
from boardwatch.core.secrets import LLM_API_KEY_ENV, resolve_secret
from boardwatch.core.settings import Settings, load_settings

config_app = typer.Typer(no_args_is_help=True, help="Show or change settings.")
console = Console()

# key → (caster, "takes effect", units note). weights.* are nested under [weights].
_SCALAR_KEYS = {
    "per_host_delay_seconds": (float, "next scan", "seconds, floor 0.25"),
    "retry_attempts": (int, "next scan", "total attempts 1–10 (1 = no retry)"),
    "scan_workers": (int, "next scan", "1–8"),
    "detail_fetch_budget": (
        int, "next scan", "per-posting detail fetches per board per scan, 1–1000"
    ),
}
_WEIGHT_KEYS = {"skill_coverage", "title_match", "recency", "location_fit"}

_SECRET_LEAF_NAMES = frozenset({"api_key", "token", "secret", "password"})


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
        f"llm: reserved (opt-in; ships v1.1); "
        f"enabled={llm.enabled}, provider={llm.provider}, model={llm.model}"
    )
    present = "set" if resolve_secret(LLM_API_KEY_ENV) is not None else "unset"
    console.print(f"llm.api_key: {present} (via {LLM_API_KEY_ENV})")


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
            f"environment ({LLM_API_KEY_ENV}).[/red]"
        )
        raise typer.Exit(code=1)
    if _is_secret_key(key.rsplit(".", 1)[-1]):
        console.print(
            f"[red]secrets do not belong in config.toml; set {LLM_API_KEY_ENV} in the "
            f"environment instead of {key!r}.[/red]"
        )
        raise typer.Exit(code=1)
    if key == "llm" or key.startswith("llm."):
        console.print(
            f"[red]{key!r} is reserved for the v1.1 LLM tier and is not settable yet.[/red]"
        )
        raise typer.Exit(code=1)

    if key in _SCALAR_KEYS:
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
