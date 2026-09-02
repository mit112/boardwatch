import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QueueRowItem } from "../components/QueueRowItem";
import { ReviewReasonBadge } from "../components/ReviewReasonBadge";
import type { ReviewReason } from "../api/types";
import { queueRow } from "../test/rows";

/*
 * The two requirement holds added with the delivery router's new gates. Both reach the page as
 * `review_reason` codes, and the failure they guard against is a WORDING one: the badge is the
 * only place the reader learns which requirement held a lead, so rendering an abstain as a
 * decision spends a judgement the engine explicitly declined to make.
 *
 * `REASONS` is a `Record<ReviewReason, ...>`, so a member added server-side and mirrored in
 * `api/types.ts` but forgotten here is already a compile error. What that cannot catch is a
 * member mapped to the WRONG words, or two members collapsed onto one label — which is exactly
 * what these assert.
 */
describe("the requirement-hold badges", () => {
  it("names a hard-family abstain as an abstain, never as an ineligible verdict", () => {
    const { container } = render(
      <ReviewReasonBadge reason="eligibility_unconfirmed" showReason />,
    );
    // `getByText` throws when absent, so each call is itself the assertion.
    screen.getByText("eligibility unconfirmed");
    const text = container.textContent ?? "";
    expect(text).toMatch(/abstained/i);
    expect(text).toMatch(/could not be decided either way/i);
    // The distinction the whole member exists for: an abstain is NOT a finding of ineligibility.
    expect(text).toMatch(/not a finding that the lead is ineligible/i);
  });

  it("names an unconfirmed experience bar as a stated requirement", () => {
    const { container } = render(
      <ReviewReasonBadge reason="experience_requirement" showReason />,
    );
    screen.getByText("experience requirement");
    expect(container.textContent ?? "").toMatch(/states an experience requirement/i);
  });

  // D-412 follow-up: `role_vetoed` used to hard-code "the role gate classified this title as
  // not software", which is false whenever the veto actually fired on a seniority/executive
  // phrase in a real software title ("Java Developer - Vice President"). Reinstating that copy
  // would pass every OTHER assertion in this file (the label is still unique, still non-empty),
  // so this guard exists specifically to catch that regression.
  it("does not claim a role-vetoed lead is not software", () => {
    const { container } = render(<ReviewReasonBadge reason="role_vetoed" showReason />);
    screen.getByText("role vetoed");
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/not software/i);
    // The per-title evidence lives in the `off target` badge's `off_target_reason`, not here —
    // this copy stays generic on purpose (see `QueueRowItem`'s `Flags`).
    expect(text).toMatch(/vetoed this title/i);
  });

  it("gives every reason its OWN label, so no two holds read alike", () => {
    const reasons: ReviewReason[] = [
      "ineligible_verdict",
      "non_us_location",
      "role_vetoed",
      "role_unconfirmed",
      "eligibility_unconfirmed",
      "experience_requirement",
    ];
    const labels = reasons.map((reason) => {
      const { container, unmount } = render(<ReviewReasonBadge reason={reason} />);
      const text = container.textContent ?? "";
      unmount();
      return text;
    });
    expect(new Set(labels).size).toBe(reasons.length);
    expect(labels.every((label) => label.length > 0)).toBe(true);
  });
});

describe("the off-target badge on a role-vetoed compact row", () => {
  // D-412 follow-up, the other half of the UI fix: the gate's per-title evidence — the exact
  // phrase it matched — reaches the compact row ONLY through the `off target` badge's
  // `off_target_reason`. QueueRowItem used to SUPPRESS that badge on `role_vetoed` rows (the
  // `review_reason !== "role_vetoed"` guard on line 50), on the theory that the generic
  // `role vetoed` badge already carried the same claim. It did not — that copy is deliberately
  // generic (see ReviewReasonBadge) — so the suppression hid the only place the matched span
  // appeared on the row. Restoring the line-50 guard makes this fail: the badge, and with it the
  // audit trail, disappears.
  it("shows the matched-phrase reason a role_vetoed row would otherwise hide", () => {
    const offTargetReason =
      'executive/seniority phrase in title, not distinguishing role from qualifier ' +
      '(matched "Vice President")';
    render(
      <QueueRowItem
        row={queueRow({
          review_reason: "role_vetoed",
          off_target: true,
          off_target_reason: offTargetReason,
        })}
        rank={1}
        selected={false}
        active={false}
        collapsing={false}
        onSelect={() => undefined}
        onApplied={() => undefined}
        onSkip={() => undefined}
      />,
    );
    // The row renders its flags in both tiers, so the badge appears more than once; either proves
    // it was not suppressed. `getAllBy*` throws on zero matches, so restoring the suppression fails
    // the test here.
    expect(screen.getAllByText("off target").length).toBeGreaterThan(0);
    // The matched span travels as the badge's `title` tooltip — the compact row's whole audit trail.
    expect(screen.getAllByTitle(offTargetReason).length).toBeGreaterThan(0);
  });
});
