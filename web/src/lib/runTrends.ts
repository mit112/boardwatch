/*
 * Reading the run-trend series. Pure, so the arithmetic is tested without a DOM.
 *
 * A series is `(number | null)[]` in run order, oldest first. `null` is "not measured" and is
 * skipped by every statistic here; it is never read as 0, which would drag a median down and draw
 * a dip for a run that was merely not timed.
 */

import type { RunTrendPoint } from "../api/types";

export function median(values: readonly (number | null)[]): number | null {
  const present = values.filter((value): value is number => value != null).sort((a, b) => a - b);
  if (present.length === 0) return null;
  const middle = Math.floor(present.length / 2);
  return present.length % 2 === 1
    ? (present[middle] as number)
    : ((present[middle - 1] as number) + (present[middle] as number)) / 2;
}

/** A wall clock, in the largest unit that keeps the number short. */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)} s`;
  const minutes = seconds / 60;
  if (minutes < 10) return `${minutes.toFixed(1)} min`;
  if (minutes < 120) return `${minutes.toFixed(0)} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}

/** How much slower than usual the newest run was, and which stage added the most. */
export interface SlowReadout {
  runId: number;
  seconds: number;
  usual: number;
  ratio: number;
  slow: boolean;
  /** The stage furthest over its own median, when the newest run was timed per stage. */
  stage: { name: string; seconds: number; usual: number } | null;
}

/** Runs of history needed before "usual" means anything. */
export const MIN_HISTORY = 3;
/** The newest run is called slow at this multiple of the median of the runs before it. */
export const SLOW_RATIO = 1.25;

export function slowReadout(runs: readonly RunTrendPoint[]): SlowReadout | null {
  const latest = runs[runs.length - 1];
  if (latest?.seconds == null) return null;
  const before = runs.slice(0, -1);
  const usual = median(before.map((run) => run.seconds));
  if (usual == null || usual <= 0) return null;
  if (before.filter((run) => run.seconds != null).length < MIN_HISTORY) return null;
  const ratio = latest.seconds / usual;
  const slow = ratio >= SLOW_RATIO;

  let stage: SlowReadout["stage"] = null;
  if (slow && latest.stage_seconds != null) {
    let best = 0;
    for (const [name, seconds] of Object.entries(latest.stage_seconds)) {
      const stageUsual = median(before.map((run) => run.stage_seconds?.[name] ?? null));
      if (stageUsual == null) continue;
      const excess = seconds - stageUsual;
      if (excess > best) {
        best = excess;
        stage = { name, seconds, usual: stageUsual };
      }
    }
  }
  return { runId: latest.id, seconds: latest.seconds, usual, ratio, slow, stage };
}

/**
 * Runs of consecutive measured points as `[x, y]` pairs in a `width` x `height` box, scaled from
 * zero to the series maximum. Breaks at every `null`, so a gap is a gap in the drawn line.
 */
export function segments(
  values: readonly (number | null)[],
  width: number,
  height: number,
  pad: number,
): [number, number][][] {
  const top = Math.max(0, ...values.filter((value): value is number => value != null));
  const step = values.length > 1 ? (width - 2 * pad) / (values.length - 1) : 0;
  const result: [number, number][][] = [];
  let open: [number, number][] | null = null;
  values.forEach((value, index) => {
    if (value == null) {
      open = null;
      return;
    }
    const x = values.length > 1 ? pad + index * step : width / 2;
    const y = top === 0 ? height - pad : height - pad - (value / top) * (height - 2 * pad);
    if (open === null) {
      open = [];
      result.push(open);
    }
    open.push([x, y]);
  });
  return result;
}
