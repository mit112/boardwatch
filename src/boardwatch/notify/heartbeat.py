"""Success heartbeat for `boardwatch run` — a dead-man's-switch ping.

On a successful run the pipeline GETs a monitor URL read only from the environment
(never config.toml — the URL embeds a token, exactly like the webhook URL). An external
cron-monitor (healthchecks.io, cronitor, …) is configured to alert when the ping does
NOT arrive within its window, which is the only way a run that never fired — the machine
off or asleep the whole day — becomes visible. Presence-gated: an unset URL is a no-op,
so it is off by default and generic for any user.

The ping is telemetry and can never fail the run: every transport error and non-2xx is
swallowed into a returned alert string, and the runner wraps the call as well (D-076).

The ping's OWN success has to be observable, though, and that is a separate problem from
the one the monitor solves. The monitor can only see pings that arrive; a ping that is sent
and refused — a rotated token, a deleted check, an endpoint answering 500 — looks to it
exactly like a machine that was asleep, and looks to the operator like nothing at all. The
whole unattended safety net rests on this one request, so an unsuccessful ping returns a
soft alert its caller records. An UNSET url stays silent: it is the default for every other
user, and a "your heartbeat failed" line for a heartbeat nobody configured is noise.
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
) -> str | None:
    """Ping the monitor URL if one is set; return a soft alert if the ping did not land.

    `None` means there is nothing for the operator to act on, and it deliberately covers
    BOTH quiet outcomes: the ping was acknowledged (2xx — redirects are followed, since
    monitor endpoints often answer a ping with a 302), or no URL is configured at all. The
    caller's only question is whether to raise an alert, and the answer for those two is the
    same. A string comes back only when a ping was ATTEMPTED and did not succeed.

    Same `str | None` soft-alert shape as `notify/intake_death.py`, and for the same reason:
    the caller prints it, records it, and carries on. This never raises and never pings more
    than once — no retry, no second GET — because telemetry can never fail a run (D-076) and
    a duplicate ping would manufacture a green the run did not earn.

    Neither branch interpolates the URL or the exception's message into the alert. The URL
    embeds a token and this string is persisted to `runs.errors_json` and reprinted by the
    CLI. What is left is enough to act on: an HTTP status IS the diagnosis when the monitor
    answered (401 a rotated token, 404 a deleted check, 5xx the monitor itself), and the
    exception CLASS separates the families that are worth telling apart when it did not
    (`ConnectError` from `ReadTimeout` from `TooManyRedirects`).

    `client` and `env` are injectable for tests, which must never ping a real monitor URL:
    a test ping registers as a successful run on the live check and destroys the signal.
    """
    url = resolve_secret(HEARTBEAT_URL_ENV, env=env)
    if url is None:
        return None
    owned = client is None
    http = client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
    try:
        response = http.get(url)
        if response.is_success:
            return None
        return f"heartbeat: the monitor refused the ping (HTTP {response.status_code})"
    except httpx.HTTPError as exc:
        return f"heartbeat: the ping never reached the monitor ({type(exc).__name__})"
    finally:
        if owned:
            http.close()
