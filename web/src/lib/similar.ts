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

/** What a group of similar postings contains, in the facts a reader decides on. */
export interface SimilarGroup {
  /** Postings in the group, this one included. */
  count: number;
  /** Distinct locations across the group, compared case-insensitively. */
  locations: number;
  /** Distinct job boards (`provider`) across the group. */
  boards: number;
}

/** The key's group for each row that has a similar lead in `rows`, with what the group holds.
 *  Nothing is merged, and nothing here decides what is a
 *  duplicate — a group is "same company, same title once formatting is folded away", no more. */
export function similarGroups(rows: readonly QueueRow[]): Map<number, SimilarGroup> {
  const byKey = new Map<string, QueueRow[]>();
  for (const row of rows) {
    const key = similarKey(row);
    const group = byKey.get(key);
    if (group === undefined) byKey.set(key, [row]);
    else group.push(row);
  }
  const groups = new Map<number, SimilarGroup>();
  for (const members of byKey.values()) {
    if (members.length < 2) continue;
    const info: SimilarGroup = {
      count: members.length,
      locations: new Set(members.map((row) => (row.location ?? "").trim().toLowerCase())).size,
      boards: new Set(members.map((row) => row.provider ?? "")).size,
    };
    for (const row of members) groups.set(row.posting_id, info);
  }
  return groups;
}

/** The OTHER postings of a row's group, in the order given — the ones "Collapse similar roles"
 *  folds under it. Every one stays an opening the reader can open; none is discarded. */
export function relatedPostings(row: QueueRow, rows: readonly QueueRow[]): QueueRow[] {
  const key = similarKey(row);
  return rows.filter((candidate) => candidate.posting_id !== row.posting_id && similarKey(candidate) === key);
}

/** How a group reads on a row: what it contains, never a claim that its members are the same job. */
export function describeGroup(group: SimilarGroup): string {
  const parts = [`${String(group.count)} related postings`];
  if (group.locations > 1) parts.push(`${String(group.locations)} locations`);
  if (group.boards > 1) parts.push(`${String(group.boards)} job boards`);
  return parts.join(" · ");
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
