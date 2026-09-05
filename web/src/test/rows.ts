import type {
  FunnelStage,
  QueueCounts,
  QueueResponse,
  QueueRow,
  RunFunnel,
  RunSummary,
} from "../api/types";

/*
 * Queue rows for the frontend tests, built here rather than imported from `src/fixtures/`.
 *
 * Two reasons, and both matter. `src/fixtures/` may only ever be reached through a dynamic
 * `import()` behind a literal `import.meta.env.DEV` (see `api/client.ts`), and adding a second
 * kind of importer would make that rule two rules. And these rows are typed as `QueueRow`, so a
 * field added to or removed from the wire contract fails `tsc --noEmit` here — the drift the row
 * shapes exist to catch cannot pass silently.
 *
 * Deliberately anonymous: a title and a company that name nobody, because everything tracked in
 * this repository is scanned for personal data.
 */

let counter = 0;

export function queueRow(overrides: Partial<QueueRow> = {}): QueueRow {
  counter += 1;
  const id = counter;
  return {
    posting_id: id,
    job_id: 1000 + id,
    title: `Software Engineer ${String(id)}`,
    company: `Example Company ${String(id)}`,
    location: "Remote",
    // `[]`, deliberately: an older server sends no `locations` at all, so the default row is the
    // one that has to render without a `+N` rather than the one that exercises it.
    locations: [],
    remote_policy: "remote",
    posted_days: 3,
    first_seen: "2026-08-20T12:00:00Z",
    status: "open",
    verdict: "eligible",
    apply_url: "https://boards.example.invalid/apply",
    delivered_run_id: 1,
    tex_uri: "file:///queue/example/resume.tex",
    pdf_uri: "file:///queue/example/resume.pdf",
    target_flag: null,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: 7.5,
    coverage: 0.62,
    why: null,
    off_target_reason: null,
    review_reason: null,
    ...overrides,
  };
}

export function queueResponse(rows: QueueRow[], review: QueueRow[] = []): QueueResponse {
  const counts: QueueCounts = {
    in_queue: rows.length,
    eligible: rows.length,
    uncertain: 0,
    ineligible: 0,
    review: review.length,
    closed: 0,
    applied_ever: 0,
    skipped: 0,
    reported: 0,
    delivered_last_run: rows.length + review.length,
    last_run_finished: "2026-08-28T09:00:00Z",
  };
  return { rows, review, counts };
}

/**
 * A field the server sent and this bundle has never heard of.
 *
 * `boardwatch web` serves its JavaScript from DISK while answering from the Python it imported at
 * STARTUP, so the two halves drift in BOTH directions (D-360). The `== null` guards cover the half
 * where the server is older and omits a field. This is the other half: the server is newer and
 * sends a member that is not in the bundle's closed catalog, so the lookup yields `undefined` and
 * reading a property off it throws during render. No guard can fix that one — only containment.
 */
export function fromANewerServer<T>(member: string): T {
  return member as unknown as T;
}

/** A field an older server never learned to send, which arrives as `undefined`, not `null`. */
export function absent<T>(): T {
  return undefined as unknown as T;
}

/** Drops keys from a row the way an older server's JSON simply would not carry them. */
export function withoutFields(row: QueueRow, fields: readonly (keyof QueueRow)[]): QueueRow {
  const copy: Record<string, unknown> = { ...row };
  for (const field of fields) delete copy[field];
  return copy as unknown as QueueRow;
}

/*
 * Run fixtures for the runs page, built here for the same two reasons the rows above are: no test
 * may import `src/fixtures/`, and typing them as the wire contract makes a field that moves a
 * `tsc --noEmit` failure rather than a silently-skipped assertion.
 */

export function runSummary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    id: 5,
    started: "2026-09-05T06:00:04+00:00",
    finished: "2026-09-05T06:31:52+00:00",
    status: "complete",
    boards_attempted: 124,
    boards_complete: 121,
    boards_partial: 0,
    boards_unchanged: 0,
    boards_failed: 3,
    postings_seen: 19844,
    new_count: 231,
    leads: 8,
    ...overrides,
  };
}

export function funnelStage(overrides: Partial<FunnelStage> = {}): FunnelStage {
  return {
    name: "scan",
    entered: 19844,
    advanced: 19617,
    drops: [],
    reconciled: true,
    instrumented: true,
    derived: false,
    note: "",
    run_scoped_attribution: null,
    ...overrides,
  };
}

export function runFunnel(overrides: Partial<RunFunnel> = {}): RunFunnel {
  return {
    artifact_version: 6,
    run_id: 5,
    started_at: "2026-09-05T06:00:04+00:00",
    finished_at: "2026-09-05T06:31:52+00:00",
    reconciles: true,
    fatal: null,
    errors: [],
    gate: {
      instrumented: true,
      judged: 8,
      eligible: 5,
      ineligible: 2,
      uncertain: 1,
      failed_open_batches: 0,
    },
    stage_durations: null,
    lanes: [],
    stages: [funnelStage()],
    coverage: {
      leads_measured: 8,
      leads_with_fraction: 5,
      mean_fraction: 0.61,
      median_fraction: 0.64,
      top_missing: [],
    },
    scan: {
      ran: true,
      boards_attempted: 124,
      boards_complete: 121,
      boards_partial: 0,
      boards_unchanged: 0,
      boards_failed: 3,
      postings_seen: 19844,
    },
    sources: [],
    ...overrides,
  };
}
