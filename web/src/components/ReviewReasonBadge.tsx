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
 * assert the decision it declined to make. `eligibility_unconfirmed` is worded the same way and for
 * the same reason: it reports that a blocking rule ABSTAINED, never that the lead is ineligible.
 *
 * `no_requirements_found` and `unevaluated` are both absences and are worded as absences of
 * OURS. Neither says anything about the posting: the first reports that our catalog matched
 * nothing in the JD, the second that no evaluation exists yet.
 */
const REASONS: Record<ReviewReason, { label: string; reason: string }> = {
  non_us_location: {
    label: "outside the US",
    reason:
      "Held for review: the location gate confirmed a location outside the US, so this lead is not blindly appliable.",
  },
  role_vetoed: {
    label: "role vetoed",
    // Neutral on purpose (D-412 follow-up): the veto can fire on a real software title where
    // the matched span is a seniority/executive phrase ("Java Developer - Vice President"), not
    // a genuine non-software determination. Naming the specific reason here would repeat
    // whichever claim `role_verdict` made, correct or not -- the per-title detail lives in
    // `off_target_reason`, not in this generic copy.
    reason: "Held for review: the role gate vetoed this title.",
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
  eligibility_unconfirmed: {
    label: "eligibility unconfirmed",
    reason:
      "Held for review: a work-authorization or clearance rule abstained, so a blocking requirement could not be decided either way. That is not a finding that the lead is ineligible.",
  },
  experience_requirement: {
    label: "experience requirement",
    reason:
      "Held for review: this posting states an experience requirement the profile does not confirm meeting.",
  },
  no_requirements_found: {
    label: "nothing extracted",
    // States what the CATALOG did, never what the posting requires: finding no requirement is a
    // fact about our own coverage of this JD, and wording it as "this posting has no
    // requirements" would assert a reading of the posting that nothing here supports.
    reason:
      "Held for review: the eligibility catalog found no requirement in this job description, so no rule cleared anything. Read the JD before applying.",
  },
  seniority_above_band: {
    label: "above the target band",
    // States what the TITLE said, never what the candidate is: the verdict is title-only by
    // construction (D-477 refused a body-seniority family), so wording this as "you are not
    // senior enough" would assert a reading of the candidate that nothing here supports.
    reason:
      "Held for review: the title alone levels above the target seniority band. That is a title-only reading, not a judgement on the job description.",
  },
  unevaluated: {
    label: "not evaluated",
    reason:
      "Held for review: nothing has evaluated this lead under the current profile yet, so there is no verdict and no evidence either way. The next run may decide it.",
  },
};

/**
 * Renders nothing off the review lane, where `reason` is `null` by construction — so the caller
 * never has to know which list a row came from.
 *
 * The guard is `== null`, deliberately loose, because it also has to survive `undefined`. The type
 * says that cannot happen and on a matched pair it cannot; but `boardwatch web` serves the bundle
 * from DISK while running the Python it imported at STARTUP, so a long-lived viewer process can
 * serve a bundle newer than its own API. A viewer started before this field existed omits it
 * entirely, `REASONS[undefined]` is `undefined`, and reading `.label` off that threw — which
 * unmounted the whole tree and blanked the page. A missing field means the server cannot say why a
 * lead was held, so the honest render is no badge: exactly the pre-#224 page.
 *
 * This guard is still the fix. `ErrorBoundary` now contains the review lane, so the same class of
 * throw costs a card rather than the page — but containment is the floor under this guard, not a
 * replacement for it: a caught error still loses the whole lane, and the reader wants the leads.
 */
export function ReviewReasonBadge({
  reason,
  detailReason = null,
  showReason = false,
}: {
  reason: ReviewReason | null;
  detailReason?: string | null;
  showReason?: boolean;
}) {
  if (reason == null) return null;
  const words = REASONS[reason];
  // `detailReason` is the gate's per-title evidence (`off_target_reason`) for a `role_vetoed`
  // row. Surfacing it HERE lets the single `role vetoed` chip carry that evidence, so the `off
  // target` chip below can stay suppressed instead of rendering the same decision twice (D-412
  // follow-up). It is safe to show directly now that `role_verdict` states only what the regex
  // matched, never a false claim about the title; the generic copy is the fallback when absent.
  return (
    <Badge
      label={words.label}
      reason={detailReason ?? words.reason}
      showReason={showReason}
    />
  );
}
