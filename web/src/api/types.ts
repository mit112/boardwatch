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
  /*
   * The role gate's third non-pass answer (T184b): the user has no role taxonomy, so the gate
   * never read the title. Not a veto and not `role_unconfirmed` — nothing looked — and the
   * reader's next step is to give boardwatch a taxonomy, not to read the title.
   */
  | "role_gate_unmeasured"
  | "unevaluated"
  | "no_requirements_found"
  | "eligibility_unconfirmed"
  | "experience_requirement"
  | "seniority_above_band"
  | "seniority_judged_above_band"
  /*
   * The FINAL GATE's own `ineligible`, kept apart from `ineligible_verdict` above because the two
   * are different engines and the reader acts on them differently: that one is a versioned
   * deterministic rule firing against a resolved profile field, which is a catalog bug when it is
   * wrong; this is an independent read of the whole JD, which needs the quoted span opened and a
   * judgement made. It HOLDS the lead in review and never drains it — review is the fail-open
   * direction for a reading no rule produced.
   */
  | "judged_ineligible_verdict"
  /*
   * The only member that is a fact about the lead's HISTORY rather than about the posting as it
   * reads today: this job was BUILT, nothing has been applied to it, and the posting has since
   * been revised. A built decision governs its job permanently and the policy stamp hashes the
   * run manifest and not posting content, so nothing else notices — the lead sits in the apply
   * queue against a job description that has changed under the résumé tailored for it. Measured
   * live 2026-09-20: 34 of 887 built-but-unapplied jobs. It HOLDS and nothing is reopened.
   */
  | "revised_since_build"
  /*
   * The only member that does not come from the job description at all. The Greenhouse
   * APPLICATION FORM states a citizenship or export-control requirement the JD never mentions —
   * measured live on three apply-lane leads a hand pre-flight withdrew, none of which says
   * "citizen", "clearance", "ITAR" or "export" anywhere in its body. That is why the chip carries
   * the QUOTED question (`form_question` below): a reader sent to the JD for this reason finds
   * nothing there and concludes the gate misfired.
   */
  | "form_question_hard_stop"
  /*
   * The provider's own STRUCTURED `employmentType` says this is not a full-time engagement while
   * the job description says nothing a rule can quote. Measured live 2026-09-22 on the
   * 1,807-board fleet: the field is written by one provider only and reads non-full-time on 1,090
   * open postings; on 671 of those the engine sees no contract or internship prose at all, and 10
   * of those were reaching the blind-apply queue. It HOLDS and can never DECIDE — a
   * provider-authored field is not the frozen JD, so it cannot carry `ineligible`'s quoted span.
   */
  | "provider_employment_type";

export interface QueueRow {
  posting_id: number;
  job_id: number;
  title: string;
  company: string;
  /**
   * The ATS the posting SITS ON, from the store's `companies.provider` — the company ROW, never
   * the apply URL's host. The two genuinely differ: the job-apps and aggregator lanes write the
   * EMPLOYER's own apply URL, so a lane copy's host reads as the employer's board while the row
   * it sits on is the lane (`jobapps`, `linkedin`, `indeed`, `hiringcafe`, `jsonld`). The lane
   * name is the correct answer here — it is what the owner, who applies in batches by form, is
   * sorting on. The frontend NEVER re-derives this from `apply_url`.
   *
   * Optional on the wire for the reason `judge_seniority_above_band` is: `boardwatch web` serves
   * this bundle from DISK while answering from the Python it imported at STARTUP, so an older
   * server omits the key and the read is `undefined`. Every guard on it is `== null`, and the
   * honest render for "the server cannot say" is no label.
   */
  provider?: string | null;
  /** The PRIMARY location: the first entry of `locations`, or `null` when the list is empty. */
  location: string | null;
  /**
   * Every location the posting lists, de-duplicated case-insensitively with the whitespace
   * trimmed, in the board's original order; `[]` when it names none. This is the same list the
   * store-level row carries, NOT a re-split of the joined `location` string above — a separator
   * that appears inside a location ("Washington, D.C.") makes the two answers differ, and only
   * one of them is what the board actually published.
   */
  locations: string[];
  remote_policy: string | null;
  /** From the nullable `postings.posted_at`. `null` renders as an em dash, NEVER as `0d`. */
  posted_days: number | null;
  first_seen: string;
  status: PostingStatus;
  verdict: Verdict | null;
  /**
   * The FINAL GATE's own verdict on this lead — a SECOND opinion beside `verdict`, never a
   * component of it. `verdict` is the deterministic rules engine's roll-up; this is an
   * independent read of the job description, and the whole value of showing both is that they
   * can disagree: on the measured apply lane 42 of 390 judged leads read `uncertain` here while
   * the rules engine had cleared them.
   *
   * `null` is "the gate has not spoken" — no gate row exists for this lead under the current
   * identity — and is never "the gate cleared it". The honest render for it is NOTHING: an
   * "unjudged" chip on every row would be a chip on every row of an older server's queue, which
   * says nothing about any lead.
   *
   * Optional on the wire for the same reason `judge_seniority_above_band` is: `boardwatch web`
   * serves the bundle from DISK while running the Python it imported at STARTUP, so a long-lived
   * viewer can serve a bundle newer than its own API. An older server omits the field, and
   * `undefined` must read the same as `null` — hence `== null` at every use, never `=== null`.
   */
  judge_verdict?: Verdict | null;
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
   * The server's own explanation of the score — which components contributed and by how much.
   * `null` when the ranker recorded none. Rendered VERBATIM: the frontend never infers a reason
   * from the score, because a hand-written explanation is a second, wrong opinion about a shipped
   * ranker in exactly the way `off_target_reason` below is.
   */
  why: string | null;
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
  /**
   * The final gate's BODY-seniority reading: `true` exactly when the judge read the job
   * description as describing a role above the target band.
   *
   * On a REVIEW row the same reading already arrives as `review_reason:
   * "seniority_judged_above_band"`, so what this field is FOR is the apply-lane row — the case
   * that exists only while `gate.seniority_hold` is off, where D-504 records the reading but
   * does not act on it. The server has always sent this; nothing rendered it, so a recorded
   * reading was invisible on the page. A signal that cannot be seen is a monitoring failure,
   * not a conservatism feature.
   *
   * Optional on the wire for the same reason `locations` is: `boardwatch web` serves the bundle
   * from DISK while running the Python it imported at STARTUP, so a long-lived viewer can serve
   * a bundle newer than its own API. An older server omits the field, and the honest render for
   * "the server cannot say" is no badge.
   */
  judge_seniority_above_band?: boolean;
  /**
   * The QUOTED question from the Greenhouse application form that holds this lead, or `null`.
   *
   * Optional on the wire for exactly the reason `judge_seniority_above_band` above is: `boardwatch
   * web` serves this bundle from DISK while running the Python it imported at STARTUP, so a
   * long-lived viewer can serve a bundle newer than its own API. An older server omits the key,
   * and `undefined` has to render as "no quote available" rather than throw.
   *
   * `null` on every lead the gate does not hold, INCLUDING a Greenhouse lead whose form was read
   * and matched nothing. An absent hold has no evidence, and an empty string here would make
   * "no hard stop" and "a hard stop we cannot quote" the same value.
   */
  form_question?: string | null;
  /**
   * T92. The provider's `employmentType` verbatim when it states a non-full-time engagement, for
   * the `provider_employment_type` chip's tooltip. Optional for the reason `form_question` above
   * is: an older server omits the key and `undefined` has to read as "no value available" rather
   * than throw. `null` on every lead the gate does not hold for this reason.
   */
  provider_employment_type?: string | null;
  /**
   * The date this lead is to be looked at again, `YYYY-MM-DD`, or `null` when none is pinned.
   *
   * A NOTE on a lead rather than a disposition: it changes no lane, no verdict and no
   * applied/skipped/reported state, and it deliberately survives the lead being marked applied —
   * an applied lead is exactly the one that gets followed up on.
   *
   * A plain date and never an instant, because that is what it means: the server writes and
   * compares it in ITS OWN local zone, so "today" is due from 00:00 local rather than from 19:00
   * the previous evening. The frontend compares against the BROWSER's local date for the same
   * reason, and the two agree on the machine this viewer actually runs on — loopback only.
   *
   * Optional on the wire for the same reason `provider` is: `boardwatch web` serves this bundle
   * from DISK while answering from the Python it imported at STARTUP, so an older server omits
   * the key and the read is `undefined`. Every guard on it is `== null`.
   */
  follow_up?: string | null;
  /**
   * T125. Postings at the SAME company with a byte-identical current body, on ANOTHER job the
   * owner already applied to — most recent application first. `[]` when there are none.
   *
   * Annotation only: a repost under a new id can be a new opening, so the lead stays listed and
   * ranked exactly as it would be without this. Optional on the wire for the reason `follow_up`
   * is — an older server omits the key — so every read is `?? []`.
   */
  applied_identical_jd?: AppliedIdenticalJd[];
}

/** One applied posting whose job description is byte-identical to the lead's. */
export interface AppliedIdenticalJd {
  posting_id: number;
  title: string;
  /** The applied posting's primary location, or `null` when it names none. */
  location: string | null;
  /** When the application was submitted, with an explicit UTC offset; `null` when never recorded. */
  applied_at: string | null;
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
  /**
   * The FINAL GATE's reading of the same apply lane `eligible` and `uncertain` count, in three
   * cells that are never folded into each other or into those two. `judge_unjudged` is
   * `judge_verdict == null` EXACTLY — "the gate has not spoken" — and is not a catch-all: a lead
   * the gate called `ineligible` is in none of the three, the way a lead with no rules verdict is
   * in neither `eligible` nor `uncertain`.
   */
  judge_eligible: number;
  judge_uncertain: number;
  judge_unjudged: number;
  /**
   * Delivered leads whose posting the employer has since taken down. They are NOT in `rows` and
   * NOT in `in_queue`: a closed posting is not work, and its folder is drained to `_closed`. Its
   * own cell rather than folded into `ineligible` — nothing judged it, so calling it a rejection
   * would assert a decision no rule made.
   */
  closed: number;
  /**
   * Delivered leads whose employer-board twin is standing (D-498 rule (a)). They are NOT in `rows`
   * or `review`: the twin is the one to apply through, and this lead's folder is drained to
   * `_lane_copy`. Counted so the band still reconciles with the delivered set.
   */
  lane_copy: number;
  applied_ever: number;
  skipped: number;
  /**
   * Leads the owner flagged as wrongly-called-eligible, held for investigation. Its own bucket,
   * never folded into `skipped`: a report is a distinct signal, not disinterest. Excluded from
   * `rows` like a skip, so it is counted here rather than left an unexplained remainder.
   */
  reported: number;
  /**
   * Leads in the APPLY lane whose follow-up date has arrived (`<= today`, in the server's local
   * date). Counted over the lane rather than over every stored follow-up because the cell is a
   * FACET: the number on it has to be the number of rows clicking it shows.
   *
   * Optional on the wire, and typed that way on purpose: a server older than the field omits it,
   * and the honest render for a count nobody took is `0`, not `NaN`.
   */
  follow_up_due?: number;
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
  /**
   * What this SERVER can do, as distinct from what the data says. Optional because a viewer older
   * than the field omits it entirely, and the honest default for an unknown capability here is
   * "assume it works": hiding a control that would in fact have worked costs the reader the only
   * route to the folder.
   */
  meta?: { reveal_supported: boolean };
}

/**
 * One row of `GET /api/applied`: one application ATTEMPT, newest first.
 *
 * Every posting-derived field is nullable, and that is the shape of the data rather than
 * defensiveness. An application imported from another tool's history matched a posting the store
 * holds, but nothing ever tailored a résumé for it, so the delivery queue never offered it —
 * `posting_id` is `null` for exactly those rows. It is the id every existing control keys on
 * (`/api/pdf/<id>`, `/api/queue/<id>/unapplied`), so a row without one gets no PDF and no unmark
 * rather than a button pointed at a sibling posting the queue never delivered.
 *
 * `status` is typed `string`, not a closed union, deliberately: it is rendered VERBATIM and never
 * indexed into a map, so a member this bundle has never heard of reads as itself instead of
 * throwing. The catalogs that ARE unions here (`Verdict`, `ReviewReason`) are the ones a component
 * looks up, which is what makes a closed type worth its containment cost.
 */
export interface AppliedRow {
  /** The stable list key. `job_id` is not one — a job can carry several attempts. */
  application_id: number;
  job_id: number;
  posting_id: number | null;
  company: string | null;
  title: string | null;
  location: string | null;
  apply_url: string | null;
  status: string;
  /** When the application was MADE. `null` for an attempt that never reached `applied`. */
  submitted_at: string | null;
  /** When boardwatch LEARNED of it, which is a different quantity and never a substitute. */
  created_at: string | null;
  posting_status: PostingStatus | null;
  /** When the employer took the posting down. `null` on a posting that is not closed. */
  closed_at: string | null;
  /** True exactly when `GET /api/pdf/<posting_id>` would serve the bytes. */
  pdf_available: boolean;
  pdf_uri: string | null;
  /** `application_events.source` for the event that set the current status: "web", "import". */
  source: string | null;
  /**
   * Whether `POST /api/queue/<posting_id>/unapplied` would act on THIS attempt.
   *
   * The route is per JOB — it withdraws the job's latest attempt — while this page is one row per
   * attempt, so the control is offered on the row the server names and nowhere else. Read as
   * `=== true`: an older server omits the key, and `undefined` must withhold the control rather
   * than offer one that acts on a different row.
   */
  can_unmark: boolean;
  /**
   * The follow-up date pinned to this lead, `YYYY-MM-DD`, or `null` where none is.
   *
   * Resolved on `job_id` — the store's key is `queue.followup.<job_id>` — so every attempt on one
   * job carries the same date, and setting it from any of their rows moves all of them.
   */
  follow_up: string | null;
}

/**
 * The applied page's band. `by_status` carries EVERY member of the store's application-status
 * catalog on every response, zeros included, so a 0 is a measurement rather than a key the reader
 * has to guess was absent.
 *
 * `posting_closed` is applied-and-since-closed: it counts only the attempts that are still in a
 * submitted state, so a withdrawn attempt against a dead requisition is not reported as an
 * application waiting on an employer.
 */
export interface AppliedCounts {
  total: number;
  by_status: Record<string, number>;
  posting_closed: number;
  /** Applications whose pinned date has arrived, counted once per JOB however many attempts it
   *  holds, and gated on the submitted statuses exactly as `posting_closed` is. */
  follow_up_due: number;
}

/** `GET /api/applied`. Named for the history, not for the mark: `AppliedResponse` above is the
 *  POST route's answer and the two are different shapes. */
export interface AppliedHistoryResponse {
  rows: AppliedRow[];
  counts: AppliedCounts;
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
  | "unreported"
  | "follow_up_set"
  | "follow_up_cleared";

export interface AppliedResponse {
  outcome: MarkOutcome;
  job_id: number | null;
}

export interface SkipResponse {
  outcome: MarkOutcome;
}

/**
 * `POST /api/queue/skip` and `POST /api/queue/unskip`, which take `{ job_ids: [...] }` and act on
 * the whole list in one transaction.
 *
 * `skipped` names the ids the call acted on and `failed` the ids that named no standing lead —
 * reported rather than refused, so one stale id cannot discard the owner's decision about the
 * rest of a selection. Both are OPTIONAL on the wire for the same reason `locations` is: the
 * viewer serves this bundle from disk and answers from the Python it imported at start-up, so a
 * server that has the route but not a field must degrade to "nothing here" rather than throw.
 */
export interface BatchSkipResponse {
  skipped?: number[];
  failed?: number[];
}

export interface ReportResponse {
  outcome: MarkOutcome;
}

/**
 * `POST /api/queue/{id}/followup` and `/unfollowup`. `follow_up` is the date the STORE now holds,
 * echoed back rather than assumed, so an optimistic row is reconciled against what was written.
 */
export interface FollowUpResponse {
  outcome: MarkOutcome;
  follow_up: string | null;
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

/**
 * The final gate's readout (`gate_to_dict`). `instrumented: false` with every count `null` is a
 * run whose gate was never armed — NOT a block of zeros, which would claim a measurement nobody
 * took. `null` for the whole block is an artifact older than the gate, which says the same thing.
 */
export interface FunnelGate {
  instrumented: boolean;
  judged: number | null;
  eligible: number | null;
  ineligible: number | null;
  uncertain: number | null;
  /** Batches the judge could not reach, cleared fail-open. The one count that changes what the
   * reader does with the leads, so it is never rendered in the same weight as the others. */
  failed_open_batches: number | null;
}

/** Wall clock between two pipeline stage boundaries. The whole list is `null` on an artifact that
 * predates the measurement; `[]` would claim a run that spent no time anywhere. */
export interface FunnelStageDuration {
  name: string;
  seconds: number;
}

/**
 * One JD-acquisition lane's work (`LaneReport`). `counts` carries all ten `AcquisitionOutcome`
 * keys every time, so a 0 in it is MEASURED — the map is rendered whole rather than filtered to
 * its non-zero members. `fetch_seconds`/`apply_seconds` are `null` for NOT MEASURED, never 0.0.
 */
export interface FunnelLane {
  name: string;
  counts: Record<string, number>;
  attempted: number;
  resolved: number;
  /** Carried, never derived as `resolved === 0`: a lane with nothing to do is not an outage. */
  is_silent_outage: boolean;
  admitted: string[];
  refused: string[];
  search_pages: { url: string; pages: number }[];
  fetch_seconds: number | null;
  apply_seconds: number | null;
  stage_elapsed_seconds: number | null;
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
  gate: FunnelGate | null;
  /** `null` means the run predates the measurement, so no stage card shows a duration. */
  stage_durations: FunnelStageDuration[] | null;
  /** `[]` when no lane ran this run — a measured absence, unlike a missing key. */
  lanes: FunnelLane[];
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
