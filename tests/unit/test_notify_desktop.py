"""Tests for the desktop delivery channel (P5). Injects a fake runner + explicit platform —
never spawns a real subprocess, so CI (incl. Windows) stays green."""

from __future__ import annotations

from boardwatch.notify.desktop import DesktopChannel, build_argv
from boardwatch.reports.notify import NotifyItem

_ITEM = NotifyItem(1, "Backend Engineer", "Acme", None, 0.7, None)


def test_argv_macos() -> None:
    argv = build_argv("darwin", "3 new matches")
    assert argv is not None
    assert argv[0] == "osascript" and any("display notification" in a for a in argv)


def test_argv_linux() -> None:
    argv = build_argv("linux", "3 new matches")
    assert argv is not None
    assert argv[0] == "notify-send"


def test_argv_linux_variant() -> None:
    # brief: any "linux*" platform string (e.g. some historical "linux2") is supported too
    argv = build_argv("linux2", "3 new matches")
    assert argv is not None
    assert argv[0] == "notify-send"


def test_argv_unsupported() -> None:
    assert build_argv("win32", "x") is None


def test_argv_escapes_quotes() -> None:
    # A title/body containing a double-quote or backslash must not be able to break out of
    # the AppleScript string literal `display notification "<body>" with title "boardwatch"`.
    body = 'Sr "Staff" Engineer'
    argv = build_argv("darwin", body)
    assert argv is not None
    script = argv[-1]
    # the escaped quotes must appear in the script...
    assert '\\"Staff\\"' in script
    # ...and the raw unescaped title must NOT appear (i.e. it was not injected verbatim)
    assert '"Staff"' not in script.replace('\\"Staff\\"', "")


def test_argv_escapes_backslash_before_quote() -> None:
    # Escaping order matters: backslash must be escaped BEFORE quotes, otherwise a body like
    # `\"` would produce `\\"` incorrectly (an escaped backslash followed by an unescaped
    # quote that breaks out of the string) instead of the correct `\\\"`.
    body = '\\"'
    argv = build_argv("darwin", body)
    assert argv is not None
    script = argv[-1]
    assert '\\\\\\"' in script


def test_deliver_calls_runner_on_supported() -> None:
    seen: dict[str, list[str]] = {}

    def runner(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    r = DesktopChannel(runner=runner, platform="darwin").deliver((_ITEM,))
    assert r.ok is True and seen["argv"][0] == "osascript"


def test_deliver_unsupported_no_subprocess() -> None:
    called = {"n": 0}

    def runner(argv: list[str]) -> int:
        called["n"] += 1
        return 0

    r = DesktopChannel(runner=runner, platform="win32").deliver((_ITEM,))
    assert r.ok is False and called["n"] == 0 and "unsupported" in r.detail.lower()


def test_deliver_absent_binary_non_fatal() -> None:
    def runner(argv: list[str]) -> int:
        raise FileNotFoundError("notify-send")

    r = DesktopChannel(runner=runner, platform="linux").deliver((_ITEM,))
    assert r.ok is False and "absent" in r.detail.lower()


def test_deliver_nonzero_exit_is_not_ok() -> None:
    def runner(argv: list[str]) -> int:
        return 1

    r = DesktopChannel(runner=runner, platform="linux").deliver((_ITEM,))
    assert r.ok is False and "1" in r.detail


def test_default_platform_and_runner_are_injectable_not_required() -> None:
    # constructing with no args must not raise / must not spawn (we don't call deliver here)
    ch = DesktopChannel()
    assert ch.name == "desktop"
