"""The one exclusive-writer lock for a bundle root (design §6).

Every command that mutates a bundle — `rebase-draft` now, `promote` next — takes *this* lock. A
second implementation of one lock is not a duplication nit: two lockfiles, or one lockfile taken
two different ways, is two writers who each believe they are alone.

Three properties are contractual rather than incidental.

**Non-blocking, with one bounded exception.** §6 and §21 both say contention returns
`bundle_lock_held` with "no wait or mutation". A blocking acquire would turn a second operator's
mistake into a hung terminal, and an unbounded retry loop would turn it into a hung terminal that
also writes. On POSIX that is literal — `RECLAIM_WINDOW_SECONDS` is zero, the lock is asked once,
and a refusal is reported as it arrives. Windows pays the reclaim window before a genuine refusal,
which is a departure from §21 recorded as such (D-224) and bounded by a deadline on purpose.

**The operating system is the only authority.** A killed holder leaves its lockfile behind, and §6
is explicit that Boardwatch "must never break or remove a lock based only on PID age, timestamp, or
file existence" — so a leftover `career-profile.lock` means nothing at all, and nothing here reads
it, ages it, or deletes it. That is what makes a stale file harmless: the next acquire succeeds
because the kernel says the lock is free, not because a heuristic decided the file was old enough.
It also means the file's presence is not a signal that anybody holds it, and no caller may treat it
as one. Nothing here depends on *who* unlinks the file, or on whether anybody does — that differs
between `filelock` versions the declared floor admits, and it is exactly the kind of detail a lock
must not rest on.

What this property does *not* get to assume is that the OS answers correctly on the first ask.
POSIX drops a *dead* process's `flock` as the process dies, so no window is needed for the
killed-holder case. Windows tears a killed holder's handles down asynchronously, and `filelock`'s
`WindowsFileLock._acquire` swallows the `EACCES` that window produces without setting its file
descriptor, so `acquire` reports `Timeout` and this module would report `bundle_lock_held` for a
lock nobody holds. `RECLAIM_WINDOW_SECONDS` answers that by asking the OS **again**, briefly, and
by nothing else: re-asking leaves the kernel as the sole authority, whereas ageing the file would
move that authority here, which §6 forbids. A window too short to cover the teardown fails the way
this module already failed — a false refusal — so it can be widened on evidence without changing
what the property means.

**A zero window is not the same as no false refusals, and POSIX is not exempt.** `UnixFileLock`
unlinks the lockfile *before* it releases the `flock`, and discards a lock whose inode is already
unlinked (`st_nlink == 0`) by returning without setting its descriptor. So a second writer that
opened the inode before the holder released it can win the `flock`, find the inode doomed, and be
reported as contention while nobody holds the lock — a live-holder *handoff* race, distinct from
Windows' dead-holder one, reproducible on local disk with no network filesystem. It is left standing
deliberately: closing it means a wait on the platforms Boardwatch is actually run on, which is a
departure §21 does not grant and the owner has not. Recorded, with a reproduction, in D-224. Do not
"fix" it here by widening the window without that decision.

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

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

from boardwatch.core.lock_reclaim import RECLAIM_POLL_SECONDS, RECLAIM_WINDOW_SECONDS
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

    Yields the lockfile path so a caller can name it in a message. Raises `BundleLockHeldError` on
    contention — at once where `RECLAIM_WINDOW_SECONDS` is zero, otherwise once the window closes —
    and `BundleIoError` when the lockfile cannot be opened at all. The two are different situations
    for the operator ("wait for the other command" versus "this is not a bundle root"), and
    collapsing them would send one of them to the wrong fix; an I/O failure is never re-asked.
    """
    path = lock_path(bundle_root)
    lock = FileLock(str(path))
    # Each pass is a whole non-blocking acquire, so the wait is this loop's and stays bounded by the
    # deadline. Delegating to `filelock`'s own `timeout=` would put the wait inside the library,
    # where no test here can reach either arm of it.
    deadline = time.monotonic() + RECLAIM_WINDOW_SECONDS
    while True:
        try:
            # `Timeout` derives from `TimeoutError`, which derives from `OSError`, so it must be
            # caught first or contention would be reported as an I/O failure.
            lock.acquire(blocking=False)
        except Timeout as exc:
            if time.monotonic() >= deadline:
                # Not "nothing was waited for", which this message used to claim: on Windows the
                # reclaim window is a real if brief wait, and denying it would be false there.
                raise BundleLockHeldError(
                    f"this bundle's {LOCK_FILE} is already held, by another command or by this one "
                    "holding it twice; nothing was changed"
                ) from exc
            time.sleep(RECLAIM_POLL_SECONDS)
            continue
        except OSError as exc:
            # `strerror` rather than `str(exc)`: the stringified error embeds the absolute lockfile
            # path, and a diagnostic that reached either rendering would carry the operator's home
            # directory into anything they pasted.
            raise BundleIoError(f"{LOCK_FILE} could not be opened: {exc.strerror}") from exc
        break
    try:
        yield path
    finally:
        lock.release()


__all__ = ["RECLAIM_WINDOW_SECONDS", "BundleLockHeldError", "bundle_lock"]
