"""Checkpoint-triggered console progress and a stage-local ETA (D-658)."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from rich.console import Console


@dataclass(frozen=True)
class ProgressUpdate:
    stage: str
    total: int
    done: int
    elapsed_seconds: float
    remaining_seconds: float | None
    item: str | None
    finished: bool


class StageProgress:
    """Count terminal attempts; committed batches advance only on the writer side.

    No timer runs between checkpoints. `on_update` receives the same immutable snapshot
    as the console, a narrow seam for T287; this reporter owns no status storage.
    `finish` forces a line with the actual count, even if a stage stopped early.
    """

    def __init__(
        self,
        stage: str,
        total: int,
        *,
        console: Console | None = None,
        every: int = 25,
        clock: Callable[[], float] = monotonic,
        on_update: Callable[[ProgressUpdate], None] | None = None,
    ) -> None:
        self.stage = stage
        self.total = total
        self.done = 0
        self.item: str | None = None
        self._console = console
        self._every = every
        self._clock = clock
        self._on_update = on_update
        self._started = clock()
        self._last_time = self._started
        self._last_done = 0
        self._emit(self._started, finished=False)

    def advance(self, n: int = 1, *, item: str | None = None) -> None:
        self.done += n
        self.item = item
        now = self._clock()
        if self.done - self._last_done >= self._every or now - self._last_time >= 60:
            self._emit(now, finished=False)

    def finish(self) -> None:
        self._emit(self._clock(), finished=True)

    def _emit(self, now: float, *, finished: bool) -> None:
        elapsed = now - self._started
        remaining = elapsed * (self.total - self.done) / self.done if self.done else None
        update = ProgressUpdate(
            self.stage, self.total, self.done, elapsed, remaining, self.item, finished
        )
        label = f" · {self.item}" if self.item else ""
        eta = f" · ETA {remaining / 60:.1f} min remaining" if remaining is not None else ""
        if self._console is not None:
            self._console.print(
                f"{self.stage}: {self.done:,}/{self.total:,}{label}"
                f" · {elapsed / 60:.1f} min elapsed{eta}",
                markup=False,
            )
        self._last_time = now
        self._last_done = self.done
        if self._on_update is not None:
            self._on_update(update)
