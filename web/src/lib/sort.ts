import type { QueueRow } from "../api/types";

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
