import type { Companion } from "../api/types";

/*
 * T296: how many leads are ready to apply to, and for how long at the current pace.
 *
 * The plan comes from any companion (T294) whose `counts` use the apply-plan keys documented in
 * `docs/companions.md`: `fillable:<board>`, `dropped:<reason>`, `waiting:<reason>`. The pace is
 * boardwatch's own (the 7-day average from `applicationPace`), so it works with no companion.
 */

export const LOW_DAYS = 2;

export interface ReadinessEntry {
  label: string;
  count: number;
}

export interface Readiness {
  /** The companion the plan came from, or `null` when none reports one. */
  source: string | null;
  updatedAt: string | null;
  fillable: ReadinessEntry[];
  dropped: ReadinessEntry[];
  waiting: ReadinessEntry[];
  fillableTotal: number;
  /** Applications per day, trailing 7 days. */
  perDay: number;
  /** `fillableTotal / perDay`; `null` with no plan or no applications in the window. */
  days: number | null;
  low: boolean;
}

function pick(
  counts: Record<string, number>,
  prefix: string,
): ReadinessEntry[] {
  return Object.entries(counts)
    .filter(([key]) => key.startsWith(prefix))
    .map(([key, count]) => ({ label: key.slice(prefix.length), count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

const sum = (entries: ReadinessEntry[]): number =>
  entries.reduce((n, e) => n + e.count, 0);

export function applyReadiness(
  companions: Companion[],
  perDay: number,
): Readiness {
  const plan = companions.find(
    (c) =>
      c.state !== "failed" &&
      Object.keys(c.counts).some((k) => k.startsWith("fillable:")),
  );
  const fillable = plan === undefined ? [] : pick(plan.counts, "fillable:");
  const fillableTotal = sum(fillable);
  const days =
    plan === undefined || perDay <= 0 ? null : fillableTotal / perDay;
  return {
    source: plan?.name ?? null,
    updatedAt: plan?.updated_at ?? null,
    fillable,
    dropped: plan === undefined ? [] : pick(plan.counts, "dropped:"),
    waiting: plan === undefined ? [] : pick(plan.counts, "waiting:"),
    fillableTotal,
    perDay,
    days,
    low: days !== null && days < LOW_DAYS,
  };
}
