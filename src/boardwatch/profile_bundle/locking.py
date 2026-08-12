"""The one exclusive-writer lock for a bundle root (design §6).

Every command that mutates a bundle — `rebase-draft` now, `promote` next — takes *this* lock. A
second implementation of one lock is not a duplication nit: two lockfiles, or one lockfile taken
two different ways, is two writers who each believe they are alone.

Three properties are contractual rather than incidental.

**Non-blocking.** §6 and §21 both say contention returns `bundle_lock_held` with "no wait or
mutation". A blocking acquire would turn a second operator's mistake into a hung terminal, and a
retry loop would turn it into a hung terminal that also writes.

**The operating system is the only authority.** The kernel drops a dead process's `flock`
immediately, and a killed holder leaves its lockfile behind. §6 is explicit that Boardwatch "must
never break or remove a lock based only on PID age, timestamp, or file existence" — so a leftover
`career-profile.lock` means nothing at all, and nothing here reads it, ages it, or deletes it. That
is what makes a stale file harmless: the next acquire succeeds because the kernel says the lock is
free, not because a heuristic decided the file was old enough. It also means the file's presence is
not a signal that anybody holds it, and no caller may treat it as one. Nothing here depends on *who*
unlinks the file, or on whether anybody does — that differs between `filelock` versions the declared
floor admits, and it is exactly the kind of detail a lock must not rest on.

Absence is not symmetric with presence, and saying so matters: exclusion is by path, so deleting the
lockfile *while a holder is inside its critical section* lets the next acquire create a new file and
succeed, and two writers proceed. That is inherent to a path-named lock rather than a defect here —
nothing in `src/` unlinks the file while holding it, and `filelock`'s own release does so only after
the critical section — but no future caller may unlink it as a repair.

**`filelock`, not `flock`.** §6 names Boardwatch's existing cross-platform dependency, which the
scan coordinator already uses. Introducing a POSIX-only primitive here would contradict the
portability contract for the sake of one subsystem.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

from boardwatch.profile_bundle.errors import BundleIoError, ProfileBundleError
from boardwatch.profile_bundle.paths import LOCK_FILE, lock_path


class BundleLockHeldError(ProfileBundleError):
    """The bundle's writer lock is already held.

    Typed rather than signalled by a return value because every caller's answer is the same — refuse
    with `bundle_lock_held`, exit 3 — and a caller that forgot to check a boolean would proceed to
    write.

    Not "another process": `bundle_lock` builds a fresh `FileLock` per call, so a second acquire
    inside *this* process fails identically, and a composite command that took the lock twice would
    otherwise send its operator hunting for a process that does not exist.
    """


@contextmanager
def bundle_lock(bundle_root: Path) -> Iterator[Path]:
    """Hold the bundle's exclusive writer lock for the duration of the block.

    Yields the lockfile path so a caller can name it in a message. Raises `BundleLockHeldError`
    immediately on contention and `BundleIoError` when the lockfile cannot be opened at all — the
    two are different situations for the operator ("wait for the other command" versus "this is not
    a bundle root"), and collapsing them would send one of them to the wrong fix.
    """
    path = lock_path(bundle_root)
    lock = FileLock(str(path))
    try:
        # `Timeout` derives from `TimeoutError`, which derives from `OSError`, so it must be caught
        # first or contention would be reported as an I/O failure.
        lock.acquire(blocking=False)
    except Timeout as exc:
        raise BundleLockHeldError(
            f"this bundle's {LOCK_FILE} is already held, by another command or by this one holding "
            "it twice; nothing was waited for and nothing was changed"
        ) from exc
    except OSError as exc:
        # `strerror` rather than `str(exc)`: the stringified error embeds the absolute lockfile
        # path, and a diagnostic that reached `report_json` would carry the operator's home
        # directory into anything they pasted.
        raise BundleIoError(f"{LOCK_FILE} could not be opened: {exc.strerror}") from exc
    try:
        yield path
    finally:
        lock.release()


__all__ = ["BundleLockHeldError", "bundle_lock"]
