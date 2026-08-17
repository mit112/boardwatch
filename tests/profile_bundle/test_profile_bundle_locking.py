"""The bundle writer lock's acquire contract, including the bounded reclaim window.

The four tests that exercise the Windows stale-lock race can only run on Windows, so none of them
can verify the window that fixes it. These can: they drive `bundle_lock` against a scripted stand-in
for `FileLock`, so both arms of the window — a refusal that clears and one that does not — are
observable on every platform.

The stand-in honours exactly the part of `FileLock` this module depends on: `acquire(blocking=False)`
either returns or raises `Timeout`. It deliberately does not model `filelock`'s own polling, because
a fake that reimplemented the retry would be testing itself rather than `bundle_lock`.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from filelock import FileLock, Timeout

from boardwatch.profile_bundle import locking
from boardwatch.profile_bundle.errors import BundleIoError
from boardwatch.profile_bundle.locking import BundleLockHeldError, bundle_lock
from boardwatch.profile_bundle.paths import lock_path


@dataclass
class _ScriptedLock:
    """A `FileLock` stand-in that refuses a scripted number of asks before it yields.

    Doubles as the factory `bundle_lock` calls, so one instance records every ask made through it.
    """

    refusals: int
    error: type[OSError] = Timeout
    attempts: list[float] = field(default_factory=list)
    releases: int = 0

    #: A wait that lost its deadline would poll until the test run was killed, and a hang is not a
    #: failure. Refusing to be asked past a ceiling turns "bounded" into something a test can catch.
    ceiling: int = 1_000

    def __call__(self, path: str) -> _ScriptedLock:
        return self

    def acquire(self, *, blocking: bool) -> None:
        assert blocking is False, "the acquire must stay non-blocking; the window is bundle_lock's"
        self.attempts.append(time.monotonic())
        if len(self.attempts) > self.ceiling:
            raise AssertionError(
                f"bundle_lock asked {len(self.attempts)} times: the wait has lost its deadline"
            )
        if len(self.attempts) <= self.refusals:
            raise self.error("scripted refusal")

    def release(self) -> None:
        self.releases += 1


def _install(
    monkeypatch: pytest.MonkeyPatch, lock: _ScriptedLock, *, window: float, poll: float = 0.001
) -> None:
    monkeypatch.setattr(locking, "FileLock", lock)
    monkeypatch.setattr(locking, "RECLAIM_WINDOW_SECONDS", window)
    monkeypatch.setattr(locking, "RECLAIM_POLL_SECONDS", poll)


def test_a_refusal_that_clears_inside_the_window_is_retried_not_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The whole point: a lock nobody holds must not be reported as held.

    Two refusals then a grant is the Windows handle-teardown window in miniature.
    """
    lock = _ScriptedLock(refusals=2)
    _install(monkeypatch, lock, window=1.0)

    with bundle_lock(tmp_path) as held:
        assert held == lock_path(tmp_path)

    assert len(lock.attempts) == 3, "the window must re-ask, not believe the first refusal"
    assert lock.releases == 1


def test_a_refusal_that_stands_is_reported_after_the_window_and_the_wait_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A real holder still gets a refusal, and the window bounds the wait rather than the holder."""
    lock = _ScriptedLock(refusals=10_000)
    _install(monkeypatch, lock, window=0.05)

    started = time.monotonic()
    with pytest.raises(BundleLockHeldError):
        with bundle_lock(tmp_path):
            pass
    elapsed = time.monotonic() - started

    assert len(lock.attempts) > 1, "a window that asks once is not a window"
    assert elapsed < 1.0, "the wait is bounded by the window, never by the holder"
    assert lock.releases == 0, "nothing was acquired, so nothing may be released"


def test_without_a_window_the_lock_is_asked_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """POSIX's contract, unchanged: one ask, no wait, and a refusal is reported as it arrives.

    Pinned separately from the platform constant because this is the behaviour design §21's "no wait
    or mutation" names, and the window is a departure from it that Windows alone is meant to pay.
    """
    lock = _ScriptedLock(refusals=1)
    _install(monkeypatch, lock, window=0.0)

    with pytest.raises(BundleLockHeldError):
        with bundle_lock(tmp_path):
            pass

    assert len(lock.attempts) == 1


def test_the_window_is_asked_for_on_windows_only() -> None:
    """The departure is Windows-only; turning it on generally would widen it silently."""
    if sys.platform == "win32":  # pragma: win32 cover
        assert locking.RECLAIM_WINDOW_SECONDS > 0
    else:  # pragma: win32 no cover
        assert locking.RECLAIM_WINDOW_SECONDS == 0.0


def test_an_io_failure_is_reported_at_once_rather_than_waited_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The window is for contention only.

    `Timeout` derives from `OSError`, so the two arms are one `except` order apart: a window that
    caught the wrong one would turn "this is not a bundle root" into a wait and then the wrong
    diagnostic.
    """
    lock = _ScriptedLock(refusals=10_000, error=PermissionError)
    _install(monkeypatch, lock, window=1.0)

    with pytest.raises(BundleIoError):
        with bundle_lock(tmp_path):
            pass

    assert len(lock.attempts) == 1


def test_a_holder_that_releases_inside_the_window_hands_the_lock_over(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The grant arm, against the real `FileLock` rather than the stand-in.

    The stand-in cannot witness this: it models `acquire`/`release` but not `lock_counter`, so a
    library that left the counter incremented on a *failed* ask would grant the lock here and then
    have its `release()` decrement to a non-zero count — leaving the lock held for the rest of the
    process while `_ScriptedLock.releases == 1` still looked correct. The final acquire below is what
    proves the handover actually completed.
    """
    monkeypatch.setattr(locking, "RECLAIM_WINDOW_SECONDS", 5.0)
    monkeypatch.setattr(locking, "RECLAIM_POLL_SECONDS", 0.01)

    held = threading.Event()
    holder = FileLock(str(lock_path(tmp_path)))

    def hold_briefly() -> None:
        holder.acquire(blocking=False)
        held.set()
        time.sleep(0.2)
        holder.release()

    thread = threading.Thread(target=hold_briefly)
    thread.start()
    try:
        assert held.wait(timeout=5.0), "the holder never took the lock"
        with bundle_lock(tmp_path) as path:
            assert path == lock_path(tmp_path)
    finally:
        thread.join(timeout=5.0)

    # Genuinely released, not merely granted: a zero-window acquire must succeed at once.
    monkeypatch.setattr(locking, "RECLAIM_WINDOW_SECONDS", 0.0)
    with bundle_lock(tmp_path):
        pass


def test_a_live_holder_is_refused_even_with_a_window_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Against the real `FileLock`: re-asking must never win a lock somebody holds.

    The one failure mode that would matter — a window that eventually breaks a live lock — cannot be
    seen through a stand-in, so this arm keeps the library in the loop.
    """
    monkeypatch.setattr(locking, "RECLAIM_WINDOW_SECONDS", 0.1)
    monkeypatch.setattr(locking, "RECLAIM_POLL_SECONDS", 0.01)

    with bundle_lock(tmp_path):
        with pytest.raises(BundleLockHeldError):
            with bundle_lock(tmp_path):
                pass
