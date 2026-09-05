/*
 * Run fixtures. `GET /api/runs/{id}` passes the run's own `funnel-<id>.json` straight through, so
 * these are shaped exactly like `reports/run_funnel.funnel_to_dict` — including the two honesty
 * conventions the page has to render: `derived: true` on a stage whose last drop bucket is the
 * remainder of the others, and `entered`/`advanced` of `null` on a stage that was not instrumented
 * (which is NOT the same as a stage that measured zero).
 */
import type { RunFunnel, RunSummary } from "../api/types";

export const RUNS: RunSummary[] = [
  {
    id: 114,
    started: "2026-08-26T06:00:04Z",
    finished: "2026-08-26T06:31:52Z",
    status: "complete",
    boards_attempted: 124,
    boards_complete: 121,
    boards_partial: 0,
    boards_unchanged: 0,
    boards_failed: 3,
    postings_seen: 19844,
    new_count: 231,
    leads: 8,
  },
  {
    id: 113,
    started: "2026-08-25T21:00:03Z",
    finished: "2026-08-25T21:29:11Z",
    status: "complete",
    boards_attempted: 124,
    boards_complete: 124,
    boards_partial: 0,
    boards_unchanged: 0,
    boards_failed: 0,
    postings_seen: 19790,
    new_count: 188,
    leads: 8,
  },
  {
    id: 112,
    started: "2026-08-25T18:00:02Z",
    finished: "2026-08-25T18:26:40Z",
    status: "complete",
    boards_attempted: 124,
    boards_complete: 120,
    boards_partial: 1,
    boards_unchanged: 1,
    boards_failed: 2,
    postings_seen: 19702,
    new_count: 204,
    leads: 7,
  },
  {
    id: 111,
    started: "2026-08-25T15:00:05Z",
    // A failed run is still a CLOSED one: `finish_run` stamps `finished_at` and the status
    // together. `finished: null` belongs to run 110 below, which nothing ever closed.
    finished: "2026-08-25T15:41:18Z",
    status: "failed",
    boards_attempted: 124,
    boards_complete: 63,
    boards_partial: 0,
    boards_unchanged: 0,
    boards_failed: 61,
    postings_seen: 9911,
    new_count: 84,
    leads: 0,
  },
  {
    // `status: running` with `finished_at` NULL means only that nothing ever closed this row —
    // in flight, killed, or a lane that raised. It has no funnel artifact for the same reason,
    // so selecting it is also the fixture's one "no artifact for that run" path.
    id: 110,
    started: "2026-08-25T12:00:02Z",
    finished: null,
    status: "running",
    boards_attempted: 124,
    boards_complete: 38,
    boards_partial: 0,
    boards_unchanged: 0,
    boards_failed: 0,
    postings_seen: 6104,
    new_count: 41,
    leads: 0,
  },
];

const FUNNEL_114: RunFunnel = {
  artifact_version: 6,
  run_id: 114,
  started_at: "2026-08-26T06:00:04Z",
  finished_at: "2026-08-26T06:31:52Z",
  reconciles: true,
  fatal: null,
  errors: [],
  gate: {
    instrumented: true,
    judged: 812,
    eligible: 466,
    ineligible: 291,
    uncertain: 55,
    // Non-zero on this run on purpose: it is the one count that changes what a reader does.
    failed_open_batches: 2,
  },
  // Ordered as the stages RAN, so consecutive marks sum to the run's wall clock.
  stage_durations: [
    { name: "scan", seconds: 604.118 },
    { name: "lanes", seconds: 27.404 },
    { name: "liveness", seconds: 188.72 },
    { name: "eligibility", seconds: 12.345 },
    { name: "shortlist", seconds: 3.017 },
    { name: "tailor", seconds: 1071.884 },
    { name: "delivery", seconds: 4.596 },
  ],
  lanes: [
    {
      name: "hiringcafe",
      // All ten `AcquisitionOutcome` keys, in catalog order, every time: a 0 here is measured.
      counts: {
        body_inline: 1902,
        body_fetched: 0,
        fetch_refused: 0,
        fetch_gone: 0,
        fetch_unavailable: 0,
        dependency_missing: 0,
        extracted_empty: 12,
        rejected_login_wall: 0,
        rejected_quality_gate: 41,
        not_attemptable: 255,
      },
      attempted: 2210,
      resolved: 1902,
      is_silent_outage: false,
      admitted: ["greenhouse:vercel", "lever:scale", "ashby:linear"],
      refused: ["greenhouse:stripe"],
      search_pages: [{ url: "https://hiring.cafe/api/search?q=software", pages: 4 }],
      fetch_seconds: 18.203,
      apply_seconds: 6.918,
      stage_elapsed_seconds: 391.06,
    },
    {
      name: "linkedin",
      counts: {
        body_inline: 0,
        body_fetched: 0,
        fetch_refused: 88,
        fetch_gone: 0,
        fetch_unavailable: 0,
        dependency_missing: 0,
        extracted_empty: 0,
        rejected_login_wall: 61,
        rejected_quality_gate: 0,
        not_attemptable: 4,
      },
      attempted: 153,
      resolved: 0,
      // Attempted work and recovered nothing. Carried by the artifact, never derived here.
      is_silent_outage: true,
      admitted: [],
      refused: [],
      search_pages: [],
      fetch_seconds: 209.44,
      // Nothing resolved, so nothing was applied and the timer never ran. NOT 0.0.
      apply_seconds: null,
      stage_elapsed_seconds: 391.06,
    },
  ],
  scan: {
    ran: true,
    boards_attempted: 124,
    boards_complete: 121,
    boards_partial: 0,
    boards_unchanged: 0,
    boards_failed: 3,
    postings_seen: 19844,
  },
  coverage: {
    leads_measured: 8,
    leads_with_fraction: 5,
    mean_fraction: 0.61,
    median_fraction: 0.64,
    top_missing: [
      { term: "kubernetes", count: 5 },
      { term: "terraform", count: 4 },
      { term: "rust", count: 3 },
      { term: "grpc", count: 2 },
      { term: "on-call", count: 2 },
    ],
  },
  stages: [
    {
      name: "scan",
      entered: 19844,
      advanced: 19617,
      drops: [
        { reason: "board_failed", count: 189, note: "3 boards returned 5xx or timed out" },
        { reason: "malformed_payload", count: 38, note: "" },
      ],
      reconciled: true,
      instrumented: true,
      derived: false,
      note: "postings the six providers listed",
      run_scoped_attribution: null,
    },
    {
      name: "liveness",
      entered: 19617,
      advanced: 19461,
      drops: [
        { reason: "dead", count: 121, note: "payload diff says the posting is gone" },
        { reason: "gone_after_redirect", count: 35, note: "subset of unknown" },
      ],
      reconciled: true,
      instrumented: true,
      derived: false,
      note: "",
      run_scoped_attribution: null,
    },
    {
      name: "eligibility",
      entered: 19461,
      advanced: 3771,
      drops: [
        { reason: "ineligible", count: 1204, note: "carries a quoted span from the frozen JD" },
        { reason: "location_gate_us_only", count: 9187, note: "" },
        { reason: "not_new_this_run", count: 5299, note: "" },
      ],
      reconciled: true,
      instrumented: true,
      derived: false,
      note: "",
      run_scoped_attribution: null,
    },
    {
      name: "shortlist",
      entered: 3771,
      advanced: 8,
      drops: [
        { reason: "hidden_hard_filter", count: 1943, note: "" },
        { reason: "hidden_non_swe", count: 501, note: "" },
        { reason: "hidden_over_seniority", count: 262, note: "target_seniority_band=entry" },
        { reason: "hidden_duplicate", count: 118, note: "exact_quad only" },
        { reason: "hidden_handled", count: 61, note: "" },
        { reason: "hidden_below_cutoff", count: 878, note: "the remainder of the buckets above" },
      ],
      reconciled: true,
      instrumented: true,
      // The last bucket is the remainder of the others, so this stage balances by construction.
      derived: true,
      // Decision-log prose with a backtick span in it, which is what the artifact actually
      // carries: the first sentence is the readout and the rest is the argument behind it.
      note:
        "considered == shortlisted + every drop. The `hidden_below_cutoff` bucket is the " +
        "remainder of the others (D-016), so this stage reconciles by construction and its " +
        "balance is bookkeeping rather than evidence.",
      run_scoped_attribution: {
        judged: 3771,
        handled: 61,
        applied: 0,
        duplicate: 118,
        dead: 0,
        unexplained: 0,
      },
    },
    {
      name: "tailor",
      entered: 8,
      advanced: 8,
      drops: [],
      reconciled: true,
      instrumented: true,
      derived: false,
      note: "",
      run_scoped_attribution: null,
    },
    {
      name: "delivery",
      entered: null,
      advanced: null,
      drops: [],
      reconciled: null,
      // Not instrumented on this run. Distinct from a stage that measured zero.
      instrumented: false,
      derived: false,
      note: "queue projection did not report",
      run_scoped_attribution: null,
    },
  ],
  sources: [
    { provider: "greenhouse", board_slug: "stripe", company_source: "seed", open_postings: 412, unique: 402, assisted: 10, eligible: 96, leads: 2, applied: 0 },
    { provider: "greenhouse", board_slug: "databricks", company_source: "seed", open_postings: 388, unique: 380, assisted: 8, eligible: 71, leads: 1, applied: 0 },
    { provider: "ashby", board_slug: "ramp", company_source: "user", open_postings: 96, unique: 96, assisted: 0, eligible: 22, leads: 1, applied: 0 },
    { provider: "lever", board_slug: "notion", company_source: "seed", open_postings: 140, unique: 133, assisted: 7, eligible: 30, leads: 1, applied: 0 },
    { provider: "workday", board_slug: "intel", company_source: "seed", open_postings: 1904, unique: null, assisted: null, eligible: 233, leads: 2, applied: 0 },
    { provider: "smartrecruiters", board_slug: "micron", company_source: "seed", open_postings: 311, unique: null, assisted: null, eligible: 44, leads: 1, applied: 0 },
    { provider: "hiringcafe", board_slug: "-", company_source: "lane", open_postings: 2210, unique: 1902, assisted: 308, eligible: 401, leads: 0, applied: 0 },
  ],
};

/** The other runs reuse 114's shape with their own headline numbers; enough to exercise the picker. */
export const FUNNELS: Record<number, RunFunnel> = {
  114: FUNNEL_114,
  113: { ...FUNNEL_114, run_id: 113, started_at: RUNS[1]!.started, finished_at: RUNS[1]!.finished },
  112: { ...FUNNEL_114, run_id: 112, started_at: RUNS[2]!.started, finished_at: RUNS[2]!.finished },
  111: {
    ...FUNNEL_114,
    run_id: 111,
    started_at: RUNS[3]!.started,
    finished_at: RUNS[3]!.finished,
    reconciles: false,
    // The scan died before the gate was armed, so its readout is an absence, not a row of zeros.
    gate: {
      instrumented: false,
      judged: null,
      eligible: null,
      ineligible: null,
      uncertain: null,
      failed_open_batches: null,
    },
    lanes: [],
    // A REASON, not a flag. This is the real one run 5 recorded, truncated the way the artifact
    // truncates it: the ids are what a reader chases.
    fatal: "cohort incomplete: 10 shortlisted candidates unaccounted: 4288, 20797, 20798, 20812, 20834, 20841, 20855, 20857, 20861, 20869",
    errors: ["scan aborted: 61 of 124 boards unreachable", "no leads emitted"],
  },
};
