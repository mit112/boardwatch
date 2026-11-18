import type { AppliedRow } from "../api/types";
import { applicationSite } from "./applicationSite";

/*
 * The applied page's pace: how many applications went out per day, and through what.
 *
 * Computed here from the rows the page already holds, and not by the server, because a "day" is
 * the READER's calendar day. The server sends UTC instants with an offset; bucketing them on the
 * server would put an application sent at 9 pm Central on the next day's bar.
 *
 * What counts is a SUBMITTED application: a status the server's `APPLIED_STATUSES` holds, with a
 * `submitted_at`. `created_at` is never a stand-in — it is when boardwatch learned of the row, and
 * an imported history would pile every old application onto the import day. A withdrawn attempt is
 * outside the set for the reason `AppliedCounts.submitted` gives.
 *
 * Nothing here judges a quiet day. A day with none is a bar of height 0 and nothing more.
 */

/** Transcribed from `store/applications.APPLIED_STATUSES`; `fixtures/server.ts` carries the same. */
const SUBMITTED_STATUSES: ReadonlySet<string> = new Set([
  "applied",
  "interviewing",
  "offer",
  "rejected",
]);

export const PACE_DAYS = 30;
export const AVERAGE_DAYS = 7;
/** More distinct labels than this fold into one "other" line, so a long tail cannot own the card. */
const MAX_SPLIT_ROWS = 6;

export const NO_BOARD_LABEL = "no link recorded";
export const NO_SOURCE_LABEL = "not recorded";
export const OTHER_LABEL = "other";

export interface PaceDay {
  /** The local calendar day, `YYYY-MM-DD`. */
  key: string;
  /** Local midnight of that day. */
  date: Date;
  count: number;
}

export interface PaceSplitEntry {
  label: string;
  count: number;
}

export interface Pace {
  /** Oldest first, exactly `PACE_DAYS` of them, the last being today. Zeros included. */
  days: PaceDay[];
  /** Submitted applications inside the window. */
  total: number;
  /** The last `AVERAGE_DAYS` days, today included, divided by `AVERAGE_DAYS`. */
  average: number;
  /** The tallest bar, floored at 1 so a window with no applications divides by something. */
  peak: number;
  byBoard: PaceSplitEntry[];
  bySource: PaceSplitEntry[];
}

function dayKey(when: Date): string {
  const month = String(when.getMonth() + 1).padStart(2, "0");
  const day = String(when.getDate()).padStart(2, "0");
  return `${String(when.getFullYear())}-${month}-${day}`;
}

/** Descending by count, then by label so equal counts keep a stable order; the tail folds. */
function toSplit(counts: Map<string, number>): PaceSplitEntry[] {
  const entries = [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  if (entries.length <= MAX_SPLIT_ROWS) return entries;
  const head = entries.slice(0, MAX_SPLIT_ROWS - 1);
  const rest = entries.slice(MAX_SPLIT_ROWS - 1).reduce((sum, entry) => sum + entry.count, 0);
  return [...head, { label: OTHER_LABEL, count: rest }];
}

function bump(counts: Map<string, number>, label: string): void {
  counts.set(label, (counts.get(label) ?? 0) + 1);
}

export function applicationPace(rows: readonly AppliedRow[], now: Date): Pace {
  // `new Date(y, m, d - n)` rolls over month ends and DST shifts, where subtracting 86 400 000 ms
  // per day would land on the wrong calendar day twice a year.
  const days: PaceDay[] = [];
  for (let back = PACE_DAYS - 1; back >= 0; back -= 1) {
    const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() - back);
    days.push({ key: dayKey(date), date, count: 0 });
  }
  const byKey = new Map(days.map((day) => [day.key, day]));
  const boards = new Map<string, number>();
  const sources = new Map<string, number>();
  let total = 0;
  for (const row of rows) {
    if (!SUBMITTED_STATUSES.has(row.status) || row.submitted_at == null) continue;
    const when = new Date(row.submitted_at);
    if (Number.isNaN(when.getTime())) continue;
    const day = byKey.get(dayKey(when));
    if (day === undefined) continue;
    day.count += 1;
    total += 1;
    bump(boards, applicationSite(row.apply_url) ?? NO_BOARD_LABEL);
    // `== null` and not `=== null`: a server older than the field omits it.
    bump(sources, row.provider == null || row.provider === "" ? NO_SOURCE_LABEL : row.provider);
  }
  const recent = days.slice(-AVERAGE_DAYS).reduce((sum, day) => sum + day.count, 0);
  return {
    days,
    total,
    average: recent / AVERAGE_DAYS,
    peak: Math.max(1, ...days.map((day) => day.count)),
    byBoard: toSplit(boards),
    bySource: toSplit(sources),
  };
}
