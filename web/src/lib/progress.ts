/*
 * "Applications recorded today" and "in the past 7 days", counted from the application ledger the
 * Applied page already reads — never from a second counter.
 *
 * What counts: an attempt in a SUBMITTED status (`store/applications.APPLIED_STATUSES`) whose
 * `submitted_at` falls in the window. A recorded application that was later answered — an
 * interview, an offer, a rejection — is still an application the owner made, so those stay in the
 * count; a `withdrawn` attempt is the undo of a record, so it leaves. That is also what makes undo
 * correct for free: withdrawing a record removes it from the count with no bookkeeping of its own.
 *
 * What does NOT count: a link that was opened, a job that was merely viewed, an attempt that never
 * reached a submitted status. Opening an employer page records nothing.
 *
 * The calendar is the BROWSER's local one, which is the server's: the viewer only ever talks to
 * loopback. Never `toISOString().slice(0, 10)` — that is UTC, and west of Greenwich it moves
 * "today" at the wrong hour of the evening (`lib/format.todayIso` says the same).
 */

/** Mirrors `store/applications.APPLIED_STATUSES`. A status outside it never counts. */
export const SUBMITTED_STATUSES: readonly string[] = ["applied", "interviewing", "offer", "rejected"];

/** The 7 local calendar days ending today: today and the six before it. */
export const WEEK_DAYS = 7;

export interface Recorded {
  today: number;
  week: number;
}

export interface Countable {
  status: string;
  /** An ISO instant with an offset, or `null` for an attempt that never reached `applied`. */
  submitted_at: string | null;
}

/** Local midnight at the start of the day `daysAgo` days before `now`. */
function startOfLocalDay(now: Date, daysAgo: number): number {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() - daysAgo).getTime();
}

export function countRecorded(rows: readonly Countable[], now: Date = new Date()): Recorded {
  const todayStart = startOfLocalDay(now, 0);
  const weekStart = startOfLocalDay(now, WEEK_DAYS - 1);
  let today = 0;
  let week = 0;
  for (const row of rows) {
    if (!SUBMITTED_STATUSES.includes(row.status) || row.submitted_at == null) continue;
    const at = new Date(row.submitted_at).getTime();
    // An unparseable instant is absence, not "now": counting it would invent an application.
    if (Number.isNaN(at)) continue;
    // `<= now`: a clock-skewed future stamp is not an application made today.
    if (at > now.getTime()) continue;
    if (at >= weekStart) week += 1;
    if (at >= todayStart) today += 1;
  }
  return { today, week };
}
