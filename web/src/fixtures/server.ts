/*
 * The fixture server. It answers exactly the paths in the HTTP contract, with the same shapes, so
 * the application code has no fixture-specific branches beyond the single switch in `api/client`.
 *
 * Three behaviours here exist to make failure paths demonstrable rather than theoretical:
 *   - a posting id divisible by 13 makes `applied` and `skipped` return HTTP 500, so the error
 *     toast and the row-restore path can be exercised deliberately;
 *   - up to four extra leads (ineligible ones are drained, not listed) arrive 30 seconds after load, so the quiet "N new — refresh" line
 *     appears without needing a real run to land;
 *   - `reveal` reports `ok: false` for one posting, which is what a platform with no file-manager
 *     handler looks like on the wire.
 */
import type { QueueCounts, QueueResponse, QueueRow } from "../api/types";
import { ANSWERS } from "./answers";
import { LATE_ROWS, QUEUE_ROWS, REVIEW_TITLES, byRank, detailFor } from "./data";
import { FUNNELS, RUNS } from "./runs";

const HOLD_MS = 30_000;
const LATENCY_MS = 140;

const ALL_ROWS = [...QUEUE_ROWS, ...LATE_ROWS].sort(byRank);

const bootedAt = Date.now();
const appliedJobIds = new Set<number>();
const skippedPostingIds = new Set<number>();

function pool(): QueueRow[] {
  const released = Date.now() - bootedAt > HOLD_MS;
  return released ? ALL_ROWS : QUEUE_ROWS;
}

/**
 * Mirrors the server: an ineligible lead is drained, so it is never a row. Filtering it here is
 * what keeps the fixture band honest — the corpus generates ~65 ineligible leads, so listing them
 * while reporting a hardcoded count put the reconciliation `in_queue == eligible + uncertain` out
 * by ~65 on the one surface a reviewer actually looks at.
 */
function visibleRows(): QueueRow[] {
  return pool().filter(
    (row) =>
      row.verdict !== "ineligible" &&
      !appliedJobIds.has(row.job_id) &&
      !skippedPostingIds.has(row.posting_id),
  );
}

/*
 * The D-332 lane split, mirroring the server: `rows` is the APPLY lane and `review` is a SECOND
 * LIST, not an exclusion. The real split is `review_gate.lane`, which reads the raw location list
 * and the role gate; the fixture has neither, so it keys off the authored title set instead —
 * which is why `REVIEW_TITLES` is authored rather than derived from `off_target`. Deriving it
 * from the badge would have made the fixture agree with a claim that is FALSE on the wire, that
 * a review lead is a badged lead.
 */
function isReviewLane(row: QueueRow): boolean {
  // `off_target` is `facts.role == "not_swe"`, and `lane()` demotes anything the role gate will
  // not positively call `swe` — so on the real wire a non-ineligible off-target lead is ALWAYS in
  // review. Without this clause the AUTHORED "Data Analyst, Growth" row (off_target, uncertain)
  // sat in the apply lane, which the wire cannot produce: the fixture would have been showing a
  // badged lead inside the list `types.ts` calls a blind-apply list. `REVIEW_TITLES` still carries
  // the case the badge CANNOT express — a role-`uncertain` title, in review wearing no flag.
  return row.off_target || REVIEW_TITLES.has(row.title);
}

function applyRows(): QueueRow[] {
  return visibleRows().filter((row) => !isReviewLane(row));
}

function reviewRows(): QueueRow[] {
  return visibleRows().filter(isReviewLane);
}

/** Counted from the pool, the way the server counts before filtering — never a constant. */
function ineligibleCount(): number {
  return pool().filter(
    (row) =>
      row.verdict === "ineligible" &&
      !appliedJobIds.has(row.job_id) &&
      !skippedPostingIds.has(row.posting_id),
  ).length;
}

function counts(rows: QueueRow[]): QueueCounts {
  const lastRun = RUNS[0];
  return {
    in_queue: rows.length,
    // Affirmatively eligible only. `uncertain` is counted separately and never added in.
    eligible: rows.filter((row) => row.verdict === "eligible").length,
    uncertain: rows.filter((row) => row.verdict === "uncertain").length,
    // Drained, not listed: `rows` never carries an ineligible lead, so this counts the pool.
    ineligible: ineligibleCount(),
    // Listed under `review`, not dropped — so unlike `ineligible` this counts a list the reader
    // can actually open. `in_queue` above is the apply lane alone, so the two together account
    // for every delivered lead.
    review: reviewRows().length,
    applied_ever: appliedJobIds.size,
    skipped: skippedPostingIds.size,
    delivered_last_run: rows.filter((row) => row.delivered_run_id === (lastRun?.id ?? -1)).length,
    last_run_finished: lastRun?.finished ?? null,
  };
}

export class FixtureError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function queueResponse(): QueueResponse {
  const rows = applyRows();
  // `counts` is computed over the APPLY lane, exactly as the server does: `in_queue`,
  // `eligible` and `uncertain` describe what is blindly appliable, and `review` is its own cell.
  return { rows, review: reviewRows(), counts: counts(rows) };
}

function findRow(postingId: number): QueueRow {
  const row = ALL_ROWS.find((candidate) => candidate.posting_id === postingId);
  if (row === undefined) throw new FixtureError(404, `no posting ${String(postingId)}`);
  return row;
}

function route(method: string, path: string): unknown {
  if (method === "GET" && path === "/api/queue") return queueResponse();
  if (method === "GET" && path === "/api/answers") return ANSWERS;
  if (method === "GET" && path === "/api/runs") return { runs: RUNS };

  const runMatch = /^\/api\/runs\/(\d+)$/.exec(path);
  if (method === "GET" && runMatch) {
    const funnel = FUNNELS[Number(runMatch[1])];
    if (funnel === undefined) throw new FixtureError(404, "no funnel artifact for that run");
    return funnel;
  }

  const detailMatch = /^\/api\/queue\/(\d+)$/.exec(path);
  if (method === "GET" && detailMatch) return detailFor(findRow(Number(detailMatch[1])));

  const actionMatch = /^\/api\/queue\/(\d+)\/(applied|skipped|unskip|reveal)$/.exec(path);
  if (method === "POST" && actionMatch) {
    const row = findRow(Number(actionMatch[1]));
    const action = actionMatch[2];
    if (action === "reveal") {
      return row.posting_id === 40012
        ? { ok: false, reason: "no file-manager handler on this platform" }
        : { ok: true };
    }
    if (row.posting_id % 13 === 0) {
      throw new FixtureError(500, "fixture: this posting id always fails, on purpose");
    }
    if (action === "applied") {
      const already = appliedJobIds.has(row.job_id);
      appliedJobIds.add(row.job_id);
      return { outcome: already ? "unchanged" : "created", job_id: row.job_id };
    }
    if (action === "skipped") {
      skippedPostingIds.add(row.posting_id);
      return { outcome: "skipped" };
    }
    skippedPostingIds.delete(row.posting_id);
    return { outcome: "unskipped" };
  }

  throw new FixtureError(404, `${method} ${path} is not in the contract`);
}

export async function fixtureFetch(path: string, method: string): Promise<unknown> {
  await new Promise((resolve) => window.setTimeout(resolve, LATENCY_MS));
  try {
    return route(method, path);
  } catch (error) {
    if (error instanceof FixtureError) throw error;
    throw new FixtureError(500, error instanceof Error ? error.message : "fixture failure");
  }
}
