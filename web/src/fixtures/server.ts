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
import type {
  AppliedHistoryResponse,
  AppliedRow,
  QueueCounts,
  QueueResponse,
  QueueRow,
} from "../api/types";
import { ANSWERS } from "./answers";
import { LATE_ROWS, QUEUE_ROWS, byRank, detailFor } from "./data";
import { FUNNELS, RUNS } from "./runs";

const HOLD_MS = 30_000;
const LATENCY_MS = 140;

const ALL_ROWS = [...QUEUE_ROWS, ...LATE_ROWS].sort(byRank);

const bootedAt = Date.now();
const appliedJobIds = new Set<number>();
const skippedPostingIds = new Set<number>();
const reportedPostingIds = new Set<number>();
/*
 * Follow-up dates, by posting. Seeded relative to TODAY rather than to a fixed date, so the
 * due marker and the "follow-up due" facet are demonstrable on any day the fixtures are opened —
 * a hard-coded 2026-09-20 stops being due the moment the calendar passes it.
 */
const followUpByPosting = new Map<number, string>();

function isoDaysFromToday(days: number): string {
  const when = new Date();
  when.setDate(when.getDate() + days);
  const month = String(when.getMonth() + 1).padStart(2, "0");
  const day = String(when.getDate()).padStart(2, "0");
  return `${String(when.getFullYear())}-${month}-${day}`;
}

/** The row as the API serves it: the follow-up is state this module holds, not a row field. */
function withFollowUp(row: QueueRow): QueueRow {
  return { ...row, follow_up: followUpByPosting.get(row.posting_id) ?? null };
}

// Two seeds, one arrived and one not, so both states are on the page before anything is clicked.
for (const [index, offset] of [
  [0, -2],
  [1, 9],
] as const) {
  const seeded = QUEUE_ROWS[index];
  if (seeded !== undefined) followUpByPosting.set(seeded.posting_id, isoDaysFromToday(offset));
}

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
      !skippedPostingIds.has(row.posting_id) &&
      !reportedPostingIds.has(row.posting_id),
  );
}

/*
 * The D-332 lane split, mirroring the server: `rows` is the APPLY lane and `review` is a SECOND
 * LIST, not an exclusion. On the wire `review_reason` is non-null EXACTLY on a review-lane row, so
 * reading the field is not a fixture-local rule about lanes — it is the same single answer the
 * page renders, which is the property the real split has and a title-keyed guess did not.
 *
 * NEVER `row.off_target` here. That flag is `not_swe` alone, so it misses every lead held for a
 * location or for a role the gate merely could not call software — and it also FIRES on an
 * eligible off-target lead, which `lane()` promotes to the apply queue badge and all.
 */
function isReviewLane(row: QueueRow): boolean {
  return row.review_reason !== null;
}

function applyRows(): QueueRow[] {
  return visibleRows().filter((row) => !isReviewLane(row)).map(withFollowUp);
}

function reviewRows(): QueueRow[] {
  return visibleRows().filter(isReviewLane).map(withFollowUp);
}

/** Counted from the pool, the way the server counts before filtering — never a constant. */
function ineligibleCount(): number {
  return pool().filter(
    (row) =>
      row.verdict === "ineligible" &&
      !appliedJobIds.has(row.job_id) &&
      !skippedPostingIds.has(row.posting_id) &&
      !reportedPostingIds.has(row.posting_id),
  ).length;
}

function counts(rows: QueueRow[]): QueueCounts {
  const lastRun = RUNS[0];
  return {
    in_queue: rows.length,
    // Affirmatively eligible only. `uncertain` is counted separately and never added in.
    eligible: rows.filter((row) => row.verdict === "eligible").length,
    uncertain: rows.filter((row) => row.verdict === "uncertain").length,
    // The final gate's three, counted from the same `rows` and never folded into each other or
    // into the two above. `judge_unjudged` is `judge_verdict == null` exactly — the fixture pool
    // carries rows the gate has not spoken on, and they are not a clear.
    judge_eligible: rows.filter((row) => row.judge_verdict === "eligible").length,
    judge_uncertain: rows.filter((row) => row.judge_verdict === "uncertain").length,
    judge_unjudged: rows.filter((row) => row.judge_verdict == null).length,
    // Drained, not listed: `rows` never carries an ineligible lead, so this counts the pool.
    ineligible: ineligibleCount(),
    // Listed under `review`, not dropped — so unlike `ineligible` this counts a list the reader
    // can actually open. `in_queue` above is the apply lane alone, so the two together account
    // for every delivered lead.
    review: reviewRows().length,
    // Drained like `ineligible` and counted for the same reason, but counted over the whole pool
    // rather than the apply lane: a closed posting leaves the queue without any rule judging it.
    closed: pool().filter((row) => row.status === "closed").length,
    applied_ever: appliedJobIds.size,
    skipped: skippedPostingIds.size,
    reported: reportedPostingIds.size,
    // Over the apply lane, exactly as the server counts it: the cell is a facet, so its number
    // has to be the number of rows clicking it shows.
    follow_up_due: rows.filter(
      (row) => row.follow_up != null && row.follow_up <= isoDaysFromToday(0),
    ).length,
    delivered_last_run: rows.filter((row) => row.delivered_run_id === (lastRun?.id ?? -1)).length,
    last_run_finished: lastRun?.finished ?? null,
  };
}

/*
 * `GET /api/applied`, derived from the same `appliedJobIds` the mark route writes — so marking a
 * lead applied in the queue makes it appear here on the next load, which is the behaviour the page
 * exists for. The seeded set is empty, matching `data.ts`' own note that `applications` has never
 * held a row on the live store: an empty applied page is the honest starting state.
 *
 * `application_id` is synthesised from the job id (one attempt per job is all this fixture models)
 * and `posting_id` is the fixture row's own, because every fixture lead was delivered. The
 * `posting_id: null` case — an application whose job never reached the queue — has no fixture row
 * to hang off and is exercised in `web/src/__tests__/appliedPage.test.tsx` instead.
 */
function appliedResponse(): AppliedHistoryResponse {
  const rows: AppliedRow[] = [...appliedJobIds]
    .map((jobId) => ALL_ROWS.find((candidate) => candidate.job_id === jobId))
    .filter((row): row is QueueRow => row !== undefined)
    .map((row) => ({
      application_id: row.job_id,
      job_id: row.job_id,
      posting_id: row.posting_id,
      company: row.company,
      title: row.title,
      location: row.location,
      apply_url: row.apply_url,
      status: "applied",
      submitted_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      posting_status: row.status,
      closed_at: row.status === "closed" ? row.first_seen : null,
      pdf_available: row.pdf_available,
      pdf_uri: row.pdf_uri,
      source: "web",
    }));
  return {
    rows,
    counts: {
      total: rows.length,
      // The whole catalog every time, zeros included, exactly as the server sends it.
      by_status: {
        interested: 0,
        applied: rows.length,
        interviewing: 0,
        offer: 0,
        rejected: 0,
        withdrawn: 0,
      },
      posting_closed: rows.filter((row) => row.posting_status === "closed").length,
    },
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
  // The fixture platform CAN reveal (one posting answers `ok: false`, which is a per-lead
  // failure rather than a missing handler), so the capability flag is true here.
  return {
    rows,
    review: reviewRows(),
    counts: counts(rows),
    meta: { reveal_supported: true },
  };
}

function findRow(postingId: number): QueueRow {
  const row = ALL_ROWS.find((candidate) => candidate.posting_id === postingId);
  if (row === undefined) throw new FixtureError(404, `no posting ${String(postingId)}`);
  return row;
}

/**
 * The batch skip and its undo. Keyed on `job_id` on the wire, exactly as the real route is, and
 * translated to this module's posting-keyed bookkeeping here — a job id that no fixture row
 * carries is `failed`, which is how the "M failed" toast is demonstrable without a real server.
 */
function batchSkip(body: unknown, skip: boolean): unknown {
  const ids = (body as { job_ids?: unknown } | null)?.job_ids;
  if (!Array.isArray(ids) || ids.some((entry) => typeof entry !== "number")) {
    throw new FixtureError(400, 'expected {"job_ids": [<integer>, ...]}');
  }
  const skipped: number[] = [];
  const failed: number[] = [];
  for (const jobId of ids as number[]) {
    const row = ALL_ROWS.find((candidate) => candidate.job_id === jobId);
    if (row === undefined) {
      failed.push(jobId);
      continue;
    }
    if (skip) skippedPostingIds.add(row.posting_id);
    else skippedPostingIds.delete(row.posting_id);
    skipped.push(jobId);
  }
  return { skipped, failed };
}

function route(method: string, path: string, body: unknown): unknown {
  if (method === "GET" && path === "/api/queue") return queueResponse();
  if (method === "POST" && path === "/api/queue/skip") return batchSkip(body, true);
  if (method === "POST" && path === "/api/queue/unskip") return batchSkip(body, false);
  if (method === "GET" && path === "/api/applied") return appliedResponse();
  if (method === "GET" && path === "/api/answers") return ANSWERS;
  if (method === "GET" && path === "/api/runs") return { runs: RUNS };

  const runMatch = /^\/api\/runs\/(\d+)$/.exec(path);
  if (method === "GET" && runMatch) {
    const funnel = FUNNELS[Number(runMatch[1])];
    if (funnel === undefined) throw new FixtureError(404, "no funnel artifact for that run");
    return funnel;
  }

  const detailMatch = /^\/api\/queue\/(\d+)$/.exec(path);
  if (method === "GET" && detailMatch) {
    return detailFor(withFollowUp(findRow(Number(detailMatch[1]))));
  }

  const actionMatch =
    /^\/api\/queue\/(\d+)\/(applied|unapplied|skipped|unskip|reported|unreport|followup|unfollowup|reveal)$/.exec(
      path,
    );
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
    if (action === "unapplied") {
      // The applied toast's undo. Mirrors `mark_job_unapplied`: the record is withdrawn, so the
      // lead comes back into the pool rather than merely reappearing in this session's list.
      const known = appliedJobIds.delete(row.job_id);
      return { outcome: known ? "transitioned" : "unchanged", job_id: row.job_id };
    }
    if (action === "skipped") {
      skippedPostingIds.add(row.posting_id);
      return { outcome: "skipped" };
    }
    if (action === "unskip") {
      skippedPostingIds.delete(row.posting_id);
      return { outcome: "unskipped" };
    }
    if (action === "reported") {
      reportedPostingIds.add(row.posting_id);
      return { outcome: "reported" };
    }
    if (action === "followup") {
      // The same strict parse the real route makes, so a bundle bug shows up here too rather
      // than only against a live server.
      const date = (body as { date?: unknown } | null)?.date;
      if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        throw new FixtureError(400, 'expected {"date": "YYYY-MM-DD"}');
      }
      followUpByPosting.set(row.posting_id, date);
      return { outcome: "follow_up_set", follow_up: date };
    }
    if (action === "unfollowup") {
      followUpByPosting.delete(row.posting_id);
      return { outcome: "follow_up_cleared", follow_up: null };
    }
    reportedPostingIds.delete(row.posting_id);
    return { outcome: "unreported" };
  }

  throw new FixtureError(404, `${method} ${path} is not in the contract`);
}

export async function fixtureFetch(
  path: string,
  method: string,
  body?: unknown,
): Promise<unknown> {
  await new Promise((resolve) => window.setTimeout(resolve, LATENCY_MS));
  try {
    return route(method, path, body);
  } catch (error) {
    if (error instanceof FixtureError) throw error;
    throw new FixtureError(500, error instanceof Error ? error.message : "fixture failure");
  }
}
