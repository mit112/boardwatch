import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReviewReasonBadge } from "../components/ReviewReasonBadge";
import type { ReviewReason } from "../api/types";

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
