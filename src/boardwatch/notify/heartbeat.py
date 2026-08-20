"""Success heartbeat for `boardwatch run` — a dead-man's-switch ping.

On a successful run the pipeline GETs a monitor URL read only from the environment
(never config.toml — the URL embeds a token, exactly like the webhook URL). An external
cron-monitor (healthchecks.io, cronitor, …) is configured to alert when the ping does
NOT arrive within its window, which is the only way a run that never fired — the machine
off or asleep the whole day — becomes visible. Presence-gated: an unset URL is a no-op,
so it is off by default and generic for any user.

The ping is telemetry and can never fail the run: every transport error and non-2xx is
swallowed into a False return, and the runner wraps the call as well (D-076).
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from boardwatch.core.secrets import resolve_secret

HEARTBEAT_URL_ENV = "BOARDWATCH_HEARTBEAT_URL"
_TIMEOUT = httpx.Timeout(10.0)


def send_heartbeat(
    *,
    env: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
) -> bool:
    """Ping the monitor URL if one is set.

    Returns True on a 2xx (redirects are followed — monitor endpoints often answer a
    ping with a 302), False when the URL is unset or the ping did not succeed. Never
    raises. `client` and `env` are injectable for tests.
    """
    url = resolve_secret(HEARTBEAT_URL_ENV, env=env)
    if url is None:
        return False
    owned = client is None
    http = client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
    try:
        return http.get(url).is_success
    except httpx.HTTPError:
        return False
    finally:
        if owned:
            http.close()
