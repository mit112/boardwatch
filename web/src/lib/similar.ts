import type { QueueRow } from "../api/types";

/*
 * "Similar roles": leads at one company under one title, differing only by city or formatting.
 *
 * About a sixth of each lane is this shape — Stripe's "Software Engineer, New Grad" six times, one
 * per office — and every one is a different canonical job, so the server's job-id dedup cannot
 * merge them (the identity kind that would, `cross_host`, deliberately does not suppress). This
 * groups them for the READER only: nothing is merged, hidden server-side or written.
 *
 * The key is company + title after the variants measured on the live queue are folded away: case,
 * dashes, punctuation, and a parenthetical or trailing work-mode ("(Remote)", "- Hybrid").
 */

const WORK_MODE = "remote|hybrid|on-?site|in-?office";

export function normaliseTitle(title: string): string {
  return title
    .toLowerCase()
    .replace(new RegExp(`\\((?:[^)]*\\b(?:${WORK_MODE})\\b[^)]*)\\)`, "g"), " ")
    .replace(new RegExp(`[-–—,|/]\\s*(?:${WORK_MODE})\\s*$`), " ")
    .replace(/[-–—_/|]/g, " ")
    .replace(/[^\p{L}\p{N}\s]/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function similarKey(row: Pick<QueueRow, "company" | "title">): string {
  return `${row.company.trim().toLowerCase()}\u0000${normaliseTitle(row.title)}`;
}

/** How many rows of `rows` share each row's key, by posting id. Only groups of two or more are
 *  listed, so a lookup that misses means "no similar lead in this list". */
export function similarCounts(rows: readonly QueueRow[]): Map<number, number> {
  const byKey = new Map<string, number[]>();
  for (const row of rows) {
    const key = similarKey(row);
    const group = byKey.get(key);
    if (group === undefined) byKey.set(key, [row.posting_id]);
    else group.push(row.posting_id);
  }
  const counts = new Map<number, number>();
  for (const group of byKey.values()) {
    if (group.length < 2) continue;
    for (const id of group) counts.set(id, group.length);
  }
  return counts;
}

/** The first row of each group, in the order given — so after sorting, the best-placed lead of a
 *  group stands for it and the rest are folded under it. */
export function firstOfEachGroup(rows: readonly QueueRow[]): QueueRow[] {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = similarKey(row);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
