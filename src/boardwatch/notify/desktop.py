"""Best-effort native desktop notification for `boardwatch notify` (P5). Zero new deps:
shells out to the OS's own notifier via an injectable runner (tests inject a fake, so this
never spawns a real process in CI and Windows stays green). macOS→osascript, Linux→notify-send.
Any other platform, or an absent binary, is a non-fatal DeliveryResult(ok=False): webhook is
the cross-platform channel. Desktop toasts are a nudge to run `boardwatch top --new`, not a
full report."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

from boardwatch.notify.channel import DeliveryResult
from boardwatch.reports.notify import NotifyItem

Runner = Callable[[list[str]], int]

_TITLE = "boardwatch"


def _default_runner(argv: list[str]) -> int:
    return subprocess.run(argv, check=False, capture_output=True).returncode


def _body(items: tuple[NotifyItem, ...]) -> str:
    n = len(items)
    lead = f"{n} new match{'es' if n != 1 else ''}"
    if not items:
        return lead
    top = items[0]
    return f"{lead} — top: {top.title} @ {top.company}"


def _escape(body: str) -> str:
    """Escape a string for safe interpolation into an AppleScript double-quoted string
    literal. Backslash MUST be escaped before double-quote, else a body ending in a
    backslash (e.g. `\\"`) would produce an escaped backslash followed by an unescaped
    quote that breaks out of the string."""
    return body.replace("\\", "\\\\").replace('"', '\\"')


def build_argv(platform: str, body: str) -> list[str] | None:
    if platform == "darwin":
        escaped = _escape(body)
        return ["osascript", "-e", f'display notification "{escaped}" with title "{_TITLE}"']
    if platform.startswith("linux"):
        return ["notify-send", _TITLE, body]
    return None


class DesktopChannel:
    name = "desktop"

    def __init__(self, runner: Runner | None = None, platform: str | None = None) -> None:
        self._runner = runner or _default_runner
        self._platform = platform or sys.platform

    def deliver(self, items: tuple[NotifyItem, ...]) -> DeliveryResult:
        argv = build_argv(self._platform, _body(items))
        if argv is None:
            return DeliveryResult(
                self.name,
                False,
                f"desktop notifications unsupported on {self._platform}; use webhook",
            )
        try:
            code = self._runner(argv)
        except FileNotFoundError:
            return DeliveryResult(self.name, False, f"{argv[0]} absent; use webhook")
        if code == 0:
            return DeliveryResult(self.name, True, f"notified ({argv[0]})")
        return DeliveryResult(self.name, False, f"{argv[0]} exit {code}")
