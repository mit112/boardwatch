"""Escalate a run's soft alerts to an external endpoint — the absent-owner channel.

The heartbeat next door solves the opposite half of the problem and only that half. It is a
dead-man's switch: the monitor alerts when a ping does NOT arrive, so a run that crashed, or a
machine that was asleep all day, becomes visible. What it cannot make visible is the run that
SUCCEEDED while degraded. The gate that sends it is satisfied by `fatal is None` plus a written
funnel and digest, so a run that raised every soft alert in the finalize block still pings, and
still pings GREEN.

That is fine while somebody is at the machine: the alerts render into the morning digest, which
is the channel D-374 built for them. It stops being fine the moment the owner is not at the
machine — the digest is a file under `~/boardwatch-applications/<date>/`, on local disk, in no
synced folder. Over a fortnight of unattended running, an intake death, a scan outage or a
collapsed corpus would be recorded faithfully every morning and read by nobody, while the
monitor stayed green the whole time.

So this posts the alert text somewhere the owner actually reads. Presence-gated on its own env
var exactly like the heartbeat URL, and unset by default: it is off for every user who never
configured it, and generic for whatever endpoint they choose. Setting it to a healthchecks.io
`/fail` URL turns the check already watching for silence into one that also reports degradation;
any endpoint that accepts a POST with a text body works the same way.

**Why a separate variable rather than the heartbeat URL with a suffix.** `heartbeat.py` is
deliberately monitor-agnostic — healthchecks.io, cronitor, anything that answers a GET — and the
failure path is spelled differently by each of them (`/fail` for one, a query parameter for
another). Deriving it here would hardcode one vendor's URL shape into a module that documents
itself as generic. The user knows their own endpoint; asking for it is one line of config and
costs nothing.

`boardwatch notify`'s webhook channel is a different feature and not a substitute: it pushes new
matching POSTINGS to Slack/Discord on its own command, and nothing schedules it on the unattended
path. This carries the RUN's warnings, from inside the run.

Telemetry can never fail a run (D-076): every transport error and non-2xx is swallowed into a
returned alert string, the caller wraps the call as well, and there is no retry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import httpx

from boardwatch.core.secrets import resolve_secret

ALERT_URL_ENV = "BOARDWATCH_ALERT_URL"
_TIMEOUT = httpx.Timeout(10.0)

#: Endpoints cap what they keep — healthchecks.io stores the first 10 KB of a POST body and
#: discards the rest silently. Truncating HERE, below that, is what makes the cut visible: the
#: body says how many alerts it dropped and where the full list lives, rather than ending
#: mid-sentence at a boundary the operator cannot see. Same contract as the digest's own
#: `MARKDOWN_ALERT_LIMIT`: never truncate without saying so.
MAX_BODY_CHARS = 8_000


def build_alert_body(run_id: int, alerts: Sequence[str]) -> str:
    """Render the POST body: a count line, then one line per alert, truncated announcedly."""
    header = f"boardwatch run {run_id}: {len(alerts)} alert(s)"
    lines = [header, *(f"- {alert}" for alert in alerts)]
    body = "\n".join(lines)
    if len(body) <= MAX_BODY_CHARS:
        return body
    kept: list[str] = [header]
    used = len(header)
    for line in lines[1:]:
        # +1 for the newline this line would add. The note below is always affordable because
        # MAX_BODY_CHARS is far larger than it.
        if used + len(line) + 1 > MAX_BODY_CHARS - 120:
            break
        kept.append(line)
        used += len(line) + 1
    withheld = len(alerts) - (len(kept) - 1)
    kept.append(f"- ...and {withheld} more, in this run's morning digest and runs.errors_json.")
    return "\n".join(kept)


def escalate_alerts(
    run_id: int,
    alerts: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
) -> str | None:
    """POST `alerts` to the configured endpoint; return a soft alert if the POST did not land.

    `None` covers all three quiet outcomes, because the caller's only question is whether it has
    something to record: the run raised no alerts (nothing to escalate — a clean run must never
    POST, or the endpoint learns nothing from a message arriving), no URL is configured (the
    default for every user), or the POST was accepted.

    A string comes back only when a POST was ATTEMPTED and did not succeed. Like the heartbeat,
    it names the HTTP status or the exception CLASS and never the URL or the exception's message:
    this string is persisted to `runs.errors_json` and reprinted by the CLI, and the URL embeds a
    token. A status IS the diagnosis when the endpoint answered (401 a rotated token, 404 a
    deleted check, 5xx the endpoint itself).

    Note the asymmetry with the heartbeat, which is deliberate: a heartbeat is withheld to signal
    trouble, so it pings only on success. This is the inverse — it fires only when there IS
    trouble, so silence from it means a clean run.
    """
    if not alerts:
        return None
    url = resolve_secret(ALERT_URL_ENV, env=env)
    if url is None:
        return None
    owned = client is None
    http = client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
    try:
        response = http.post(url, content=build_alert_body(run_id, alerts).encode("utf-8"))
        if response.is_success:
            return None
        return f"alert escalation: the endpoint refused the report (HTTP {response.status_code})"
    except httpx.HTTPError as exc:
        return f"alert escalation: the report never reached the endpoint ({type(exc).__name__})"
    finally:
        if owned:
            http.close()
