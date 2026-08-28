import type { ReviewReason } from "../api/types";
import { Badge } from "./Badge";

/*
 * WHICH reason holds a lead in the review lane. Before this existed the only marker a review row
 * could carry was `off_target`, which is `not_swe` ALONE — so a lead held for a confirmed non-US
 * location, and a lead held because the role gate would not positively call its title software,
 * rendered indistinguishable from a clean one.
 *
 * The map is keyed on the server's closed `ReviewReason` set, exactly as `VerdictChip` is keyed on
 * `Verdict`: the wire carries the code and this file carries the words, so a new member added
 * server-side is a compile error here rather than a row that silently renders bare. Nothing here
 * infers a reason from a title, a location or `off_target` — a second opinion about the lane is
 * how the page and the `_review` folder start disagreeing about one lead (D-332).
 *
 * `role_vetoed` and `role_unconfirmed` are worded as the different claims they are. Only the first
 * is a decision the gate made; the second is an abstain, and calling it "not software" would
 * assert the decision it declined to make.
 */
const REASONS: Record<ReviewReason, { label: string; reason: string }> = {
  non_us_location: {
    label: "outside the US",
    reason:
      "Held for review: the location gate confirmed a location outside the US, so this lead is not blindly appliable.",
  },
  role_vetoed: {
    label: "role vetoed",
    reason: "Held for review: the role gate classified this title as not software.",
  },
  role_unconfirmed: {
    label: "role unconfirmed",
    reason:
      "Held for review: the role gate would not positively call this title software. That is an abstain, not a veto, and not the claim that the role is off target.",
  },
  ineligible_verdict: {
    label: "ineligible verdict",
    reason:
      "Held for review: an ineligible verdict arrived on a lead the queue expected to have excluded.",
  },
};

/**
 * Renders nothing off the review lane, where `reason` is `null` by construction — so the caller
 * never has to know which list a row came from.
 */
export function ReviewReasonBadge({
  reason,
  showReason = false,
}: {
  reason: ReviewReason | null;
  showReason?: boolean;
}) {
  if (reason === null) return null;
  const words = REASONS[reason];
  return <Badge label={words.label} reason={words.reason} showReason={showReason} />;
}
