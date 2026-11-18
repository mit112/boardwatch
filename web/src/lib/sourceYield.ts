import type { FunnelSource, SourceYieldResponse } from "../api/types";

/*
 * T306: discovery yield per source. Two scopes, kept apart because they are not one funnel:
 *
 *   - `open` and `eligible`: the run's own snapshot (the funnel's per-board rows, summed);
 *   - `built` and `applied`: all time, from `/api/source-yield`.
 *
 * The only ratio is applied / built, whose two sides share a scope. Dividing an all-time count
 * by a snapshot would be a number with no meaning, so the page does not.
 */

export interface SourceYieldRow {
  source: string;
  open: number | null;
  eligible: number | null;
  built: number | null;
  applied: number | null;
  /** applied / built; `null` when nothing was built. */
  applyRate: number | null;
}

export function sourceYield(
  boards: FunnelSource[] | null,
  allTime: SourceYieldResponse["sources"] | null,
): SourceYieldRow[] {
  const snap = new Map<string, { open: number; eligible: number }>();
  for (const b of boards ?? []) {
    const row = snap.get(b.provider) ?? { open: 0, eligible: 0 };
    row.open += b.open_postings;
    row.eligible += b.eligible;
    snap.set(b.provider, row);
  }
  const names = new Set([...snap.keys(), ...Object.keys(allTime ?? {})]);
  return [...names]
    .map((source) => {
      const s = snap.get(source);
      const a = allTime?.[source];
      return {
        source,
        open: boards === null ? null : (s?.open ?? 0),
        eligible: boards === null ? null : (s?.eligible ?? 0),
        built: allTime === null ? null : (a?.built ?? 0),
        applied: allTime === null ? null : (a?.applied ?? 0),
        applyRate:
          a === undefined || a.built === 0 ? null : a.applied / a.built,
      };
    })
    .sort(
      (x, y) =>
        (y.built ?? 0) - (x.built ?? 0) ||
        (y.open ?? 0) - (x.open ?? 0) ||
        x.source.localeCompare(y.source),
    );
}
