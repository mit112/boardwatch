"""How long a non-blocking lock acquire keeps re-asking the OS before believing a refusal.

Boardwatch takes two independent `filelock` locks — the bundle writer lock
(`profile_bundle/locking.py`) and the scan lock (`scan/coordinator.py`) — and both are
contractually non-blocking: contention is reported at once rather than queued. Both therefore
inherit the same platform defect, which is why the window lives here rather than in either of them.

`filelock`'s `WindowsFileLock._acquire` swallows the `EACCES` that Windows returns while a killed
holder's file handles are still being torn down, returning without setting its file descriptor. The
caller then sees `Timeout` and cannot tell that transient apart from real contention. Re-asking for
a bounded window fixes it without any heuristic: the kernel stays the only authority, whereas ageing
or deleting the lockfile would move that authority into Boardwatch. See D-224 for the bundle lock
and D-227 for the scan lock.

**The window is a judgement, not a measurement.** No figure for the real teardown window exists. Too
short a window fails exactly the way an unwindowed acquire already fails — a false refusal — so it
can be widened on evidence without changing what either lock guarantees.

**POSIX is not exempt, and a zero window here does not claim otherwise.** `UnixFileLock` unlinks the
lockfile before releasing the `flock`, and discards an already-unlinked inode, so a handoff between
two *live* holders can also produce a refusal nobody is holding. That is recorded in D-224 and left
standing by the owner's ruling, because closing it would mean waiting on the platforms Boardwatch is
actually run on. Do not widen this to POSIX without that decision.

**Consumers bind these by name at import.** Patching an attribute here does *not* reach
`locking.RECLAIM_WINDOW_SECONDS` or `coordinator.RECLAIM_WINDOW_SECONDS` — a test must patch the
consumer it is exercising. Two bindings is the deliberate cost of leaving each lock's own module the
place its behaviour is read and documented.
"""

from __future__ import annotations

import sys

#: Zero wherever the killed-holder case needs no window, which is everywhere but Windows.
RECLAIM_WINDOW_SECONDS = 1.0 if sys.platform == "win32" else 0.0

#: Short enough that the common Windows case — a window that has already closed — costs one poll.
RECLAIM_POLL_SECONDS = 0.025


__all__ = ["RECLAIM_POLL_SECONDS", "RECLAIM_WINDOW_SECONDS"]
