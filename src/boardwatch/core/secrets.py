"""Secret resolution (secrets contract, P0-3 D-P0-3-2/3).

Credentials come only from the environment. config.toml is the shareable config and
never holds secrets. resolve_secret is the single documented read point so the
opt-in LLM tier and other credential-consuming features never scatter os.environ
access.

A persistent-secret file is reserved at {config_dir}/secrets.toml but is not read yet;
when it lands, a nonblank env value overrides the file and a blank/unset env value
falls through to it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

# Provider-neutral env var for the opt-in LLM tier's credential.
LLM_API_KEY_ENV = "BOARDWATCH_LLM_API_KEY"


def resolve_secret(env_var: str, *, env: Mapping[str, str] | None = None) -> str | None:
    """Return the secret value for env_var, or None if unset.

    os.environ is read at call time (never bound at import). A missing variable, or a
    value that is empty or whitespace-only, is treated as unset. env is injectable for
    tests.
    """
    source = os.environ if env is None else env
    value = source.get(env_var)
    if value is None:
        return None
    value = value.strip()
    return value or None
