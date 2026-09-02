import type { QueueCounts, QueueResponse, QueueRow } from "../api/types";

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
