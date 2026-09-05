/*
 * The HTTP contract, transcribed from the implementation plan's contract table. This file is the
 * single place the frontend's idea of a shape lives; if the server disagrees, this is the one file
 * to reconcile.
 *
 * Two shapes the contract table leaves open, resolved here and flagged so they are easy to find:
 *
 *  1. `score`, `coverage` and `off_target_reason` are NOT on the store-level `QueueRow` dataclass,
 *     but the queue row must show a score and a coverage figure and the minimum-score filter needs
 *     a number to compare. They are computed live (design §6.2: score via `rank/heuristic`,
 *     coverage via `tailor/coverage`, neither persisted), so they belong to the API layer beside
 *     the three derived booleans it already adds.
 *  2. `RequirementView` is named by the contract but not defined. It is modelled here as one row
 *     per recognised requirement, carrying both the coverage answer (`covered`) and the eligibility
 *     evidence for it (`rule`, `disposition`, `profile_field`, `quote`). Entries with a `rule` are
 *     rendered as evidence; all entries are rendered in the covered / missing lists.
 *
 * `rank` is deliberately absent: the contract says the rows arrive ranked, so rank is the position
 * in the array and is never a field that could disagree with the ordering it describes.
 */

/** The three verdicts arrive from the API verbatim and are never computed or inferred client-side. */
export type Verdict = "eligible" | "uncertain" | "ineligible";

/**
 * Three values, where `postings.status` holds two. `unverifiable` is derived server-side for an
 * open posting whose company nothing enumerates: no scan can ever mark it missing, so "still
 * open" was never measured (D-314/D-324). The frontend NEVER derives it — it has no idea which
 * boards are watched, and a second opinion about that would be a wrong one.
 */
export type PostingStatus = "open" | "closed" | "unverifiable";

/**
 * Which reason holds a lead in the review lane, from `delivery/review_gate.classify` —
 * the same call the lane itself is a projection of, so a row's reason and the list it arrived in
 * are one decision (D-332). A CLOSED set: the frontend's map over it is exhaustive, so adding a
 * member server-side is a compile error here rather than a row that silently renders bare.
 *
 * `role_vetoed` and `role_unconfirmed` are separate members and must stay separate. The role gate
 * returns three answers and only `not_swe` is a veto; `uncertain` is an abstain, and rendering it
 * as "not software" would assert the decision the gate declined to make.
 *
 * `eligibility_unconfirmed` and `experience_requirement` are separate for the same kind of reason.
 * The first says a BLOCKING rule (work authorization or clearance) abstained, so the JD has to be
 * read before anything is spent on the lead; the second says a stated experience bar is not
 * confirmed satisfied, which is a lead the reader may well still want. One member for both would
 * lose the distinction that decides what the reader does next.
 *
 * `no_requirements_found` and `unevaluated` are the two ABSENCES, and they are separate from each
 * other on the same test. The first says the catalog read the JD and found no requirement in it,
 * so nothing was cleared and the reader has to read it themselves — a state that will not change
 * until the catalog does. The second says nothing has evaluated the lead yet, which the next run
 * may well fix on its own. Both were the apply lane's largest population before A3 (521 and 34 of
 * 646 measured leads), so folding them would also lose the split that change is measured on.
 */
export type ReviewReason =
  | "ineligible_verdict"
  | "non_us_location"
  | "role_vetoed"
  | "role_unconfirmed"
  | "unevaluated"
  | "no_requirements_found"
  | "eligibility_unconfirmed"
  | "experience_requirement"
  | "seniority_above_band";

export interface QueueRow {
  posting_id: number;
  job_id: number;
  title: string;
  company: string;
  location: string | null;
  remote_policy: string | null;
  /** From the nullable `postings.posted_at`. `null` renders as an em dash, NEVER as `0d`. */
  posted_days: number | null;
  first_seen: string;
  status: PostingStatus;
  verdict: Verdict | null;
  apply_url: string | null;
  delivered_run_id: number | null;
  tex_uri: string;
  pdf_uri: string | null;
  target_flag: boolean | null;

  /* Derived by the API, not the store. */
  thin_jd: boolean;
  off_target: boolean;
  pdf_available: boolean;

  /* Computed live by the API; labelled "as of now" wherever they are shown. */
  score: number | null;
  /** Résumé keyword coverage as a fraction 0..1. `null` exactly when `thin_jd` is true. */
  coverage: number | null;
  /**
   * Why the role gate vetoed the title, carrying the text it actually matched. Displayed beside
   * the badge so a veto is auditable. The frontend never re-derives this from the title: a
   * hand-written title pattern is a second, wrong opinion about a shipped gate.
   */
  off_target_reason: string | null;
  /**
   * Non-`null` EXACTLY on a review-lane row, so this and "the row arrived in `review`" are the
   * same statement. Never re-derive it from `off_target`: that flag is `not_swe` alone, while the
   * lane also holds a confirmed non-US location and a title the gate merely could not call
   * software, so most review leads carry a reason and no badge.
   */
  review_reason: ReviewReason | null;
}

export interface QueueCounts {
  in_queue: number;
  /** The affirmatively-eligible count and the headline yield. `uncertain` is NEVER summed in. */
  eligible: number;
  /** Its own visible bucket. "Not yet known" — not a warning, and not a step below eligible. */
  uncertain: number;
  /**
   * Delivered leads the gate now rejects. They are NOT in `rows` and NOT in `in_queue`: an
   * ineligible lead is not work, and its folder is drained to `_ineligible` on disk. Counted
   * rather than silently dropped, so `in_queue` has no unexplained remainder.
   */
  ineligible: number;
  /**
   * Delivered leads held for a LOOK rather than blindly appliable — a foreign or unknown-and-
   * unverified location, or a title the role gate will not positively call software. They ARE
   * listed, under `QueueResponse.review`, and their folders sit in `_review` (D-332). Its own
   * cell for the same reason `ineligible` has one: `in_queue` counts the apply lane, so without
   * this the difference between it and the delivered set is an unexplained remainder.
   */
  review: number;
  applied_ever: number;
  skipped: number;
  /**
   * Leads the owner flagged as wrongly-called-eligible, held for investigation. Its own bucket,
   * never folded into `skipped`: a report is a distinct signal, not disinterest. Excluded from
   * `rows` like a skip, so it is counted here rather than left an unexplained remainder.
   */
  reported: number;
  delivered_last_run: number;
  last_run_finished: string | null;
}

export interface QueueResponse {
  /**
   * The APPLY lane: exactly what the top level of `~/boardwatch-queue` holds, and therefore a
   * blind-apply list. Never contains a review lead or an ineligible one.
   */
  rows: QueueRow[];
  /**
   * The REVIEW lane: exactly what `_review` holds. Listed, not hidden — a review lead is work to
   * look at, unlike an ineligible one, which is excluded and only counted.
   *
   * Do NOT try to re-derive this from `off_target`. That flag is `not_swe` ONLY and never
   * `uncertain`, so most review leads carry no flag at all; the lane is the server's answer and
   * the only one that matches the folder tree. Each row's `review_reason` says which reason held
   * it, and is the only field that does.
   */
  review: QueueRow[];
  counts: QueueCounts;
}

export interface RequirementView {
  requirement: string;
  covered: boolean;
  rule: string | null;
  disposition: string | null;
  profile_field: string | null;
  /** A span quoted out of the FROZEN posting version. Rendered as text, never as markup. */
  quote: string | null;
  rationale: string | null;
}

export interface QueueDetail {
  row: QueueRow;
  /** `null` means no current posting version. Never `""` for that case. */
  jd_body: string | null;
  requirements: RequirementView[];
  board_target: string | null;
}

export type MarkOutcome =
  | "created"
  | "transitioned"
  | "unchanged"
  | "no_posting"
  | "no_job"
  | "skipped"
  | "unskipped"
  | "reported"
  | "unreported";

export interface AppliedResponse {
  outcome: MarkOutcome;
  job_id: number | null;
}

export interface SkipResponse {
  outcome: MarkOutcome;
}

export interface ReportResponse {
  outcome: MarkOutcome;
}

export interface RevealResponse {
  ok: boolean;
  reason?: string;
}

export interface AnswerQuestion {
  q: string;
  a: string;
  /** Shown, and NEVER copied. Some notes are warnings against reusing the answer as written. */
  note?: string | null;
}

export interface Answers {
  identity: Record<string, string | null>;
  work_auth: Record<string, string | null>;
  education: Record<string, string | null>[];
  questions: AnswerQuestion[];
}

export interface RunSummary {
  id: number;
  started: string | null;
  finished: string | null;
  status: string | null;
  boards_attempted: number | null;
  boards_complete: number | null;
  boards_partial: number | null;
  boards_unchanged: number | null;
  boards_failed: number | null;
  postings_seen: number | null;
  new_count: number | null;
  leads: number | null;
}

export interface RunsResponse {
  runs: RunSummary[];
}

/* The funnel artifact, passed through by `GET /api/runs/{run_id}`. Keys transcribed from
 * `reports/run_funnel.funnel_to_dict`; only what the page renders is typed. */

export interface FunnelDrop {
  reason: string;
  count: number;
  note: string;
}

export interface FunnelStage {
  name: string;
  entered: number | null;
  advanced: number | null;
  drops: FunnelDrop[];
  reconciled: boolean | null;
  instrumented: boolean;
  /** One drop bucket is the remainder of the others, so `reconciled` holds by construction. */
  derived: boolean;
  note: string;
  run_scoped_attribution: Record<string, number> | null;
}

export interface FunnelCoverage {
  leads_measured: number;
  leads_with_fraction: number;
  mean_fraction: number | null;
  median_fraction: number | null;
  top_missing: { term: string; count: number }[];
}

export interface FunnelSource {
  provider: string;
  board_slug: string;
  company_source: string;
  open_postings: number;
  unique: number | null;
  assisted: number | null;
  eligible: number;
  leads: number;
  applied: number;
}

export interface RunFunnel {
  artifact_version: number;
  run_id: number;
  started_at: string | null;
  finished_at: string | null;
  reconciles: boolean;
  /**
   * The REASON the run ended fatally, not a flag: `fatal: str | None` in `reports/run_funnel.py`.
   * Typed as a boolean it truth-tested correctly and printed nothing, which is the whole of the
   * diagnostic thrown away.
   */
  fatal: string | null;
  errors: string[];
  stages: FunnelStage[];
  coverage: FunnelCoverage;
  scan: {
    ran: boolean;
    boards_attempted: number | null;
    boards_complete: number | null;
    boards_partial: number | null;
    boards_unchanged: number | null;
    boards_failed: number | null;
    postings_seen: number | null;
  };
  sources: FunnelSource[];
}
