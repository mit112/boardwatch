import type { AppliedRow, QueueRow } from "../api/types";

/** Only user-initiated sorting changes the order; a background refresh never does.
 *
 * The runtime lists are the source and the types are derived from them, rather than the other way
 * round: a sort restored from `sessionStorage` has to be checked against the catalog at runtime,
 * and a hand-written second copy of the members is exactly how the two drift apart. */
export const SORT_KEYS = [
  "rank",
  "title",
  "company",
  "location",
  "age",
  "score",
  "coverage",
  "provider",
  "follow_up",
] as const;
export type SortKey = (typeof SORT_KEYS)[number];

export const SORT_DIRECTIONS = ["asc", "desc"] as const;
export type SortDirection = (typeof SORT_DIRECTIONS)[number];

export interface SortState {
  key: SortKey;
  direction: SortDirection;
}

/**
 * A sort read back out of storage, or `null` when it is not one.
 *
 * The catalogs are CLOSED, so an out-of-catalog key is a failure and is discarded whole — never
 * repaired into a partly-valid sort and never allowed through as a new key. Storage is untrusted
 * input: it survives a bundle upgrade that removed a column.
 */
export function parseSortState(raw: string | null): SortState | null {
  if (raw === null) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const { key, direction } = parsed as { key?: unknown; direction?: unknown };
  if (!(SORT_KEYS as readonly unknown[]).includes(key)) return null;
  if (!(SORT_DIRECTIONS as readonly unknown[]).includes(direction)) return null;
  return { key: key as SortKey, direction: direction as SortDirection };
}

/** `null` always sorts last, in both directions: absence is not a low value. */
function compareNullable(a: number | null, b: number | null, direction: SortDirection): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return direction === "asc" ? a - b : b - a;
}

function compareText(a: string | null, b: string | null, direction: SortDirection): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  const result = a.localeCompare(b);
  return direction === "asc" ? result : -result;
}

/**
 * Sort the leads into ATS BLOCKS, each block still in rank order.
 *
 * The owner applies in batches by ATS — every Greenhouse form is the same form — so what this
 * key has to produce is blocks, and a block the reader works down from the best lead. Rank is
 * therefore the tiebreak and it is ALWAYS ascending: the direction reverses which block comes
 * first, never the reading order inside one.
 *
 * `?? null` and not `=== null`: an older server omits `provider` entirely (see the type), so the
 * value is `undefined`, and `compareText` — which is what puts an absent value LAST in both
 * directions — checks for `null`. Absence is not an ATS and never heads the list.
 */
function compareProvider(
  a: QueueRow,
  b: QueueRow,
  direction: SortDirection,
  rankOf: (row: QueueRow) => number,
): number {
  const byProvider = compareText(a.provider ?? null, b.provider ?? null, direction);
  return byProvider === 0 ? rankOf(a) - rankOf(b) : byProvider;
}

export function sortRows(
  rows: QueueRow[],
  sort: SortState,
  rankOf: (row: QueueRow) => number,
): QueueRow[] {
  const copy = [...rows];
  copy.sort((a, b) => {
    switch (sort.key) {
      case "rank":
        return compareNullable(rankOf(a), rankOf(b), sort.direction);
      case "title":
        return compareText(a.title, b.title, sort.direction);
      case "company":
        return compareText(a.company, b.company, sort.direction);
      case "location":
        return compareText(a.location, b.location, sort.direction);
      case "age":
        return compareNullable(a.posted_days, b.posted_days, sort.direction);
      case "score":
        return compareNullable(a.score, b.score, sort.direction);
      case "coverage":
        return compareNullable(a.coverage, b.coverage, sort.direction);
      case "provider":
        return compareProvider(a, b, sort.direction, rankOf);
      /* ISO-8601 dates sort lexicographically exactly as they sort chronologically, so this is
         `compareText` and not a `Date` parse per comparison. `?? null` because an older server
         omits the field, and `compareText` is what puts an absent value LAST in BOTH directions:
         a lead with no follow-up is not the soonest one. */
      case "follow_up":
        return compareText(a.follow_up ?? null, b.follow_up ?? null, sort.direction);
    }
  });
  return copy;
}

/** The free-text box searches company, title and location — the three fields a duplicate group
 * differs by, and nothing else, so a match is always something the reader can see on the row. */
export function matchesQuery(row: QueueRow, query: string): boolean {
  if (query === "") return true;
  const needle = query.toLowerCase();
  return (
    row.company.toLowerCase().includes(needle) ||
    row.title.toLowerCase().includes(needle) ||
    (row.location ?? "").toLowerCase().includes(needle) ||
    // Every location, not only the primary: `location` is now the first of `locations`, and a
    // posting listed as "New York, NY / Boston, MA" must answer to "boston". `?? []` because an
    // older server omits the list (see `format.ts`).
    (row.locations ?? []).some((entry) => entry.toLowerCase().includes(needle))
  );
}

/*
 * The applied page's sort. Its own CLOSED catalog rather than a widening of `SORT_KEYS`: the two
 * lists share no column but company, and a single catalog would let a queue-only key be restored
 * onto a table that cannot sort by it. The comparators below are the same two, so "null sorts
 * last in both directions" is one rule and not two.
 */
export const APPLIED_SORT_KEYS = ["date", "company", "posting_status", "follow_up"] as const;
export type AppliedSortKey = (typeof APPLIED_SORT_KEYS)[number];

export interface AppliedSortState {
  key: AppliedSortKey;
  direction: SortDirection;
}

/**
 * When the application was MADE, as a sortable number, or `null` when nothing can say.
 *
 * `submitted_at` first and `created_at` only as the fallback: the first is the date the owner is
 * looking for, and it is absent exactly for an attempt that never reached `applied`, where when
 * boardwatch learned of the row is the only date there is. `?? null` at both reads because an
 * older server omits a key entirely, and `Number.isNaN` because an unparseable string must sort
 * as absence rather than as `NaN`, which compares false against everything.
 */
export function appliedAt(row: AppliedRow): number | null {
  const stamp = row.submitted_at ?? row.created_at ?? null;
  if (stamp == null) return null;
  const parsed = Date.parse(stamp);
  return Number.isNaN(parsed) ? null : parsed;
}

export function sortAppliedRows(rows: AppliedRow[], sort: AppliedSortState): AppliedRow[] {
  const copy = [...rows];
  copy.sort((a, b) => {
    switch (sort.key) {
      case "date":
        return compareNullable(appliedAt(a), appliedAt(b), sort.direction);
      case "company":
        return compareText(a.company ?? null, b.company ?? null, sort.direction);
      case "posting_status":
        return compareText(a.posting_status ?? null, b.posting_status ?? null, sort.direction);
      /* The same comparator the queue's `follow_up` uses, for the same two reasons: ISO-8601
         dates sort lexicographically exactly as they sort chronologically, and `compareText` is
         what puts an absent value LAST in BOTH directions — an application with no follow-up is
         not the soonest one. */
      case "follow_up":
        return compareText(a.follow_up ?? null, b.follow_up ?? null, sort.direction);
    }
  });
  return copy;
}

/** The applied page's search box: company, title and location, the same three the queue's box
 *  reads, so a match is always something the reader can see on the row. */
export function matchesAppliedQuery(row: AppliedRow, query: string): boolean {
  if (query === "") return true;
  const needle = query.toLowerCase();
  return [row.company, row.title, row.location].some(
    (field) => field != null && field.toLowerCase().includes(needle),
  );
}
