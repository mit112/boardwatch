import type { QueueRow } from "../api/types";

/** Only user-initiated sorting changes the order; a background refresh never does. */
export type SortKey = "rank" | "title" | "company" | "location" | "age" | "score" | "coverage";
export type SortDirection = "asc" | "desc";

export interface SortState {
  key: SortKey;
  direction: SortDirection;
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
    (row.location ?? "").toLowerCase().includes(needle)
  );
}
