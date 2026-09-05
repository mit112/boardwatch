import type { QueueRow, ReviewReason } from "../api/types";

/*
 * The WORDS for each review reason, and the counting the page's copy is generated from.
 *
 * The lane's heading paragraph and the band's `review` tooltip both hand-wrote two of the nine
 * reasons — "outside the US, or … not positively call software". On the measured day that
 * described none of the 149 leads under it: the lane held 108 `unevaluated` and 41
 * `role_unconfirmed`. Copy that enumerates a closed catalog by hand goes stale the first time the
 * catalog grows, and it did.
 *
 * `Record<ReviewReason, string>` and not a partial map: a member added server-side and mirrored in
 * `api/types.ts` is a compile error here rather than a lead that quietly vanishes from the
 * breakdown. The labels are copied VERBATIM from `ReviewReasonBadge`'s own map so the sentence and
 * the chip on the row read as one vocabulary; `reviewSummary.test.tsx` compares the two through
 * the badge's render, because that map is not exported and the badge belongs to another change.
 * This file is the single source — the badge can be pointed at it whenever it is next touched.
 */
export const REVIEW_REASON_LABELS: Record<ReviewReason, string> = {
  eligibility_unconfirmed: "eligibility unconfirmed",
  experience_requirement: "experience requirement",
  ineligible_verdict: "ineligible verdict",
  no_requirements_found: "nothing extracted",
  non_us_location: "outside the US",
  role_unconfirmed: "role unconfirmed",
  role_vetoed: "role vetoed",
  seniority_above_band: "above the target band",
  unevaluated: "not evaluated",
};

export interface ReasonCount {
  reason: ReviewReason;
  count: number;
}

/**
 * How many leads each reason holds, largest first — the order the reader needs, because the
 * biggest bucket is the one worth doing something about.
 *
 * A row whose `review_reason` is not in the catalog is NOT counted and NOT given a bucket of its
 * own: the catalog is closed, so an unrecognised code is a mismatch between this bundle and the
 * server it is being served by (D-360), not a tenth reason. The totals below are taken from the
 * row count rather than from these buckets, so such a row still shows up in the figure the reader
 * acts on and the shortfall is visible rather than papered over.
 */
export function countReviewReasons(rows: QueueRow[]): ReasonCount[] {
  const tally = new Map<ReviewReason, number>();
  for (const row of rows) {
    const reason = row.review_reason;
    if (reason == null || !(reason in REVIEW_REASON_LABELS)) continue;
    tally.set(reason, (tally.get(reason) ?? 0) + 1);
  }
  return [...tally]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count);
}

/** `"108 not evaluated, 41 role unconfirmed"`, or `""` when nothing carries a known reason. */
export function reviewBreakdown(rows: QueueRow[]): string {
  return countReviewReasons(rows)
    .map(({ reason, count }) => `${count.toLocaleString()} ${REVIEW_REASON_LABELS[reason]}`)
    .join(", ");
}

/** The lane's one-sentence summary. The total is the ROW COUNT, never the sum of the buckets. */
export function reviewLaneSentence(rows: QueueRow[]): string {
  const total = rows.length.toLocaleString();
  const breakdown = reviewBreakdown(rows);
  return breakdown === "" ? `${total} held for a look.` : `${total} held for a look: ${breakdown}.`;
}
