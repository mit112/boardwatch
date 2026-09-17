import { describe, expect, it } from "vitest";

import type { QueueRow } from "../api/types";
import { matchesQuery, sortRows } from "../lib/sort";
import type { SortState } from "../lib/sort";
import { queueRow, withoutFields } from "../test/rows";

/*
 * `lib/sort` is pure, so these tests need no DOM — but the file is `.test.tsx` because the vitest
 * gate's `include` is `src/**\/*.test.tsx` (see `vitest.config.ts`); a `.test.ts` would never run.
 *
 * The one invariant with teeth here is the null-last rule (`sort.ts` line 12): a null is ABSENCE,
 * not a low value, so it sorts to the END in BOTH directions. A comparator that folded null into
 * "smallest" would float every unscored lead to the top of an ascending sort, which is the worst
 * place for "we could not measure this". Every ordering assertion below supplies exactly one null
 * and checks it stays LAST whichever way the column is sorted — so inverting the null branch breaks
 * it, and a plain numeric mistake cannot pass it either.
 */

const ASC: SortState = { key: "score", direction: "asc" };
const DESC: SortState = { key: "score", direction: "desc" };

// Rank never decides these cases: the sort key is `score`, so `rankOf` only breaks a tie that the
// fixtures never create. A constant keeps it from being mistaken for the thing under test.
const rankOf = () => 1;

function scores(rows: { score: number | null }[]): (number | null)[] {
  return rows.map((row) => row.score);
}

describe("sortRows keeps a null value last in both directions", () => {
  it("ascending sorts the measured values up and leaves the null at the end", () => {
    const rows = [
      queueRow({ score: 5 }),
      queueRow({ score: null }),
      queueRow({ score: 9 }),
      queueRow({ score: 1 }),
    ];
    // Ascending by value, then the unmeasured one — NOT `[null, 1, 5, 9]`, which is what treating
    // null as the smallest number would produce.
    expect(scores(sortRows(rows, ASC, rankOf))).toEqual([1, 5, 9, null]);
  });

  it("descending sorts the measured values down and STILL leaves the null at the end", () => {
    const rows = [
      queueRow({ score: 5 }),
      queueRow({ score: null }),
      queueRow({ score: 9 }),
      queueRow({ score: 1 }),
    ];
    // The direction flips the measured order but NOT the null's place — absence is never the
    // "largest" value either.
    expect(scores(sortRows(rows, DESC, rankOf))).toEqual([9, 5, 1, null]);
  });

  it("does not mutate the array it was handed", () => {
    const rows = [queueRow({ score: 9 }), queueRow({ score: 1 })];
    const before = scores(rows);
    sortRows(rows, ASC, rankOf);
    expect(scores(rows)).toEqual(before);
  });
});

describe("matchesQuery searches only what the reader can see on the row", () => {
  const row = queueRow({
    company: "Globex",
    title: "Backend Engineer",
    location: "Austin, TX",
    remote_policy: "hybrid",
    apply_url: "https://jobs.acme.test/openings/42",
  });

  it("an empty query matches every row", () => {
    expect(matchesQuery(row, "")).toBe(true);
  });

  it("matches on company, title and location, case-insensitively", () => {
    expect(matchesQuery(row, "globex")).toBe(true);
    expect(matchesQuery(row, "BACKEND")).toBe(true);
    expect(matchesQuery(row, "austin")).toBe(true);
  });

  it("does not match a substring that lives only in an unsearched field", () => {
    // `acme` is in `apply_url` and nowhere the reader can read, so a match on it would be a
    // duplicate group the free-text box claims to distinguish but cannot show. `hybrid` is the
    // remote policy, which is likewise not one of the three searched fields.
    expect(matchesQuery(row, "acme")).toBe(false);
    expect(matchesQuery(row, "hybrid")).toBe(false);
    expect(matchesQuery(row, "zzz")).toBe(false);
  });

  it("does not throw when the location is absent", () => {
    const noWhere = queueRow({ location: null, company: "Initech", title: "Analyst" });
    expect(matchesQuery(noWhere, "initech")).toBe(true);
    expect(matchesQuery(noWhere, "austin")).toBe(false);
  });
});

it("matches the text filter against a secondary location, not only the primary", () => {
  const row = queueRow({ location: "New York, NY", locations: ["New York, NY", "Boston, MA"] });
  expect(matchesQuery(row, "boston")).toBe(true);
  expect(matchesQuery(row, "chicago")).toBe(false);
});

/*
 * Sorting by the ATS the posting sits on. The owner applies in batches by provider — every
 * Greenhouse form is the same form — so the thing under test is that the sort produces BLOCKS
 * and that each block is still in the order the ranker put it in. A comparator that only
 * compared the provider string would pass the grouping half and shuffle every block.
 */
describe("sortRows groups by provider and keeps rank order inside each block", () => {
  const workdayLate = queueRow({ provider: "workday" });
  const greenhouseLate = queueRow({ provider: "greenhouse" });
  const workdayEarly = queueRow({ provider: "workday" });
  const greenhouseEarly = queueRow({ provider: "greenhouse" });
  // Deliberately the REVERSE of the array order below, so a sort that returned its input
  // unchanged — or one that ignored the rank tiebreak — cannot read as green.
  const ranks = new Map([
    [workdayLate.posting_id, 4],
    [greenhouseLate.posting_id, 3],
    [workdayEarly.posting_id, 2],
    [greenhouseEarly.posting_id, 1],
  ]);
  const byRank = (row: { posting_id: number }) => ranks.get(row.posting_id) ?? 0;
  const unsorted = [workdayLate, greenhouseLate, workdayEarly, greenhouseEarly];

  function blocks(rows: QueueRow[]): [string | null | undefined, number][] {
    return rows.map((row) => [row.provider, byRank(row)]);
  }

  it("ascending: the providers block alphabetically and each block reads in rank order", () => {
    expect(blocks(sortRows(unsorted, { key: "provider", direction: "asc" }, byRank))).toEqual([
      ["greenhouse", 1],
      ["greenhouse", 3],
      ["workday", 2],
      ["workday", 4],
    ]);
  });

  it("descending: the BLOCKS reverse, the rank order inside one does not", () => {
    // Rank is the reading order within a provider, not a second sort direction: flipping it
    // would hand the reader the worst lead of a block first.
    expect(blocks(sortRows(unsorted, { key: "provider", direction: "desc" }, byRank))).toEqual([
      ["workday", 2],
      ["workday", 4],
      ["greenhouse", 1],
      ["greenhouse", 3],
    ]);
  });

  it("a row the server named no provider for sorts LAST in both directions", () => {
    // `withoutFields` and not `provider: null`: an older server omits the key entirely, so the
    // value is `undefined`, and a comparator guarded `=== null` would let it through to
    // `localeCompare` and throw. Absence is not a low value and not a high one — it is last.
    const unnamed = withoutFields(queueRow({ provider: "greenhouse" }), ["provider"]);
    const rows = [unnamed, workdayLate, greenhouseLate];
    const providers = (sorted: QueueRow[]) => sorted.map((row) => row.provider);
    expect(providers(sortRows(rows, { key: "provider", direction: "asc" }, byRank))).toEqual([
      "greenhouse",
      "workday",
      undefined,
    ]);
    expect(providers(sortRows(rows, { key: "provider", direction: "desc" }, byRank))).toEqual([
      "workday",
      "greenhouse",
      undefined,
    ]);
  });
});
