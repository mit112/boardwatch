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

  it("words the two absences as absences of OURS, never as claims about the posting", () => {
    // A3's whole point is that these leads were cleared by SILENCE, so the copy must not read as
    // a finding about the JD. "This posting has no requirements" would be exactly that finding,
    // and it is the wording most likely to be written by someone shortening the label.
    const found = render(<ReviewReasonBadge reason="no_requirements_found" showReason />);
    screen.getByText("nothing extracted");
    const foundText = found.container.textContent ?? "";
    expect(foundText).toMatch(/catalog found no requirement/i);
    expect(foundText).toMatch(/no rule cleared anything/i);
    expect(foundText).not.toMatch(/this posting has no requirement/i);
    found.unmount();

    const unevaluated = render(<ReviewReasonBadge reason="unevaluated" showReason />);
    screen.getByText("not evaluated");
    const unevaluatedText = unevaluated.container.textContent ?? "";
    expect(unevaluatedText).toMatch(/nothing has evaluated this lead/i);
    // The transience is the difference from `no_requirements_found`, and it is what the reader
    // acts on: one clears itself on the next run, the other never will.
    expect(unevaluatedText).toMatch(/next run/i);
    unevaluated.unmount();
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
    // Rendered WITHOUT `detailReason`, so it falls back to this generic copy; on a real row the
    // per-title evidence reaches the chip through `detailReason` (see `QueueRowItem`'s `Flags`).
    expect(text).toMatch(/vetoed this title/i);
  });

  // T184b. With no role taxonomy the gate never read the title, so the copy may claim neither a
  // veto nor "not software" — and it names the one command that makes the gate able to fire.
  it("reports an unmeasured role gate as a missing taxonomy, never as a veto", () => {
    const { container } = render(
      <ReviewReasonBadge reason="role_gate_unmeasured" showReason />,
    );
    screen.getByText("role gate unmeasured");
    const text = container.textContent ?? "";
    expect(text).toMatch(/no role taxonomy/i);
    expect(text).toMatch(/not a veto/i);
    expect(text).not.toMatch(/not software/i);
    expect(text).toMatch(/profile role-taxonomy/);
  });

  // T119. This reason is the only one that is NOT a reading of the posting as it stands: it says
  // the version the résumé was tailored against is no longer the one on the board. Wording it as
  // a finding about the job ("this posting changed its requirements") would assert a reading of
  // the revision that nothing here has made — the revision has not been read at all, which is
  // exactly why the lead is in front of the reader.
  it("names the revision as a move under the résumé, not as a finding about the posting", () => {
    const { container } = render(
      <ReviewReasonBadge reason="revised_since_build" showReason />,
    );
    screen.getByText("revised since build");
    const text = container.textContent ?? "";
    expect(text).toMatch(/revised since/i);
    expect(text).toMatch(/tailored for it/i);
    // The claim it must NOT make: nothing here has read the new body, so it cannot say the
    // posting is now ineligible, more senior, or anything else about its contents.
    expect(text).not.toMatch(/ineligible|no longer eligible/i);
  });

  it("gives every reason its OWN label, so no two holds read alike", () => {
    const reasons: ReviewReason[] = [
      "ineligible_verdict",
      "non_us_location",
      "role_vetoed",
      "role_unconfirmed",
      "role_gate_unmeasured",
      "eligibility_unconfirmed",
      "experience_requirement",
      "no_requirements_found",
      "unevaluated",
      "seniority_above_band",
      "seniority_judged_above_band",
      "form_question_hard_stop",
      "revised_since_build",
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

describe("the role-vetoed compact row surfaces its evidence without a duplicate chip", () => {
  // D-412 follow-up, the other half of the UI fix. On a `role_vetoed` row `off_target` is the SAME
  // `role_verdict(title)` decision the `role vetoed` badge already renders, so a second `off target`
  // chip would show one decision twice. The gate's per-title evidence — the exact phrase it matched
  // — instead reaches the compact row through the `role vetoed` badge's tooltip (`detailReason`),
  // and the `off target` chip is suppressed. Two failures are guarded: removing the suppression
  // brings the duplicate chip back, and dropping the `detailReason` routing loses the evidence.
  const offTargetReason =
    'title matched the executive/seniority deny pattern (matched "Vice President")';
  const renderRow = () =>
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
        onReport={() => undefined}
      />,
    );

  it("suppresses the duplicate off-target chip", () => {
    renderRow();
    // `queryAllByText` returns [] rather than throwing, so this fails if the suppression is removed.
    expect(screen.queryAllByText("off target")).toHaveLength(0);
  });

  it("carries the matched-phrase reason on the role-vetoed badge's tooltip", () => {
    renderRow();
    // The row renders its flags in both tiers, so the badge appears more than once. The matched
    // span travels as the `role vetoed` badge's `title` tooltip — the compact row's whole audit
    // trail. Dropping the `detailReason` routing (badge falls back to generic copy) fails this.
    expect(screen.getAllByText("role vetoed").length).toBeGreaterThan(0);
    expect(screen.getAllByTitle(offTargetReason).length).toBeGreaterThan(0);
  });
});

describe("the form-hard-stop row quotes the question the JD does not contain", () => {
  // T91. This reason is the only one whose evidence is NOT in the job description, so the quote
  // is the whole audit trail: a reader who sees "form hard stop", opens the JD and finds no
  // mention of citizenship concludes the gate misfired. The quote reaches the compact row exactly
  // as the role gate's matched phrase does — through the badge's `detailReason` tooltip.
  const question =
    "This position requires current U. S. citizenship in order to achieve and maintain a " +
    "security clearance. Are you currently a U. S. citizen?";
  const renderRow = (formQuestion: string | null) =>
    render(
      <QueueRowItem
        row={queueRow({
          review_reason: "form_question_hard_stop",
          form_question: formQuestion,
        })}
        rank={1}
        selected={false}
        active={false}
        collapsing={false}
        onSelect={() => undefined}
        onApplied={() => undefined}
        onSkip={() => undefined}
        onReport={() => undefined}
      />,
    );

  it("carries the quoted question on the badge's tooltip", () => {
    renderRow(question);
    expect(screen.getAllByText("form hard stop").length).toBeGreaterThan(0);
    // Dropping the `detailReason` routing falls back to the generic copy and fails this.
    expect(screen.getAllByTitle(question).length).toBeGreaterThan(0);
  });

  it("falls back to the generic copy when the server sent no quote", () => {
    // The state an older viewer process produces: it serves this bundle but omits the field. The
    // honest render is the reason WITHOUT a quote — never `undefined` in a tooltip, and never a
    // missing chip, because the hold is real either way.
    renderRow(null);
    expect(screen.getAllByText("form hard stop").length).toBeGreaterThan(0);
    expect(screen.getAllByTitle(/never mentions/).length).toBeGreaterThan(0);
  });

  it("says where the requirement was found, not that the JD states it", () => {
    const { container } = render(
      <ReviewReasonBadge reason="form_question_hard_stop" showReason />,
    );
    const text = container.textContent ?? "";
    expect(text).toMatch(/application form/i);
    expect(text).toMatch(/job description never mentions/i);
  });

  it("states what the PROVIDER wrote for a non-full-time hold, never a verdict", () => {
    // T92. A provider-authored structured field is not the frozen JD, so this copy may never
    // read as a decision about the candidate or assert the JD says anything.
    const { container } = render(
      <ReviewReasonBadge reason="provider_employment_type" showReason />,
    );
    const text = container.textContent ?? "";
    expect(text).toMatch(/metadata/i);
    expect(text).toMatch(/non-full-time/i);
    // it must NOT claim the job description states it -- that is the error the copy avoids
    expect(text).not.toMatch(/the job description (states|requires)/i);
  });
});

describe("the not-full-time row quotes the provider field the JD does not contain", () => {
  // T92, and the same audit-trail argument T91's block above makes: a reader who sees "not
  // full-time", opens the JD and finds nothing about the engagement concludes the gate misfired.
  // Measured 2026-09-22: on 671 of the 1,090 non-FullTime open postings the engine sees no
  // contract or internship prose at all, so "the JD says nothing" is the NORMAL case here.
  const renderRow = (value: string | null) =>
    render(
      <QueueRowItem
        row={queueRow({
          review_reason: "provider_employment_type",
          provider_employment_type: value,
        })}
        rank={1}
        selected={false}
        active={false}
        collapsing={false}
        onSelect={() => undefined}
        onApplied={() => undefined}
        onSkip={() => undefined}
        onReport={() => undefined}
      />,
    );

  it("carries the provider's own value on the badge's tooltip", () => {
    renderRow("Contract");
    expect(screen.getAllByText("not full-time").length).toBeGreaterThan(0);
    // Dropping the `detailReason` routing falls back to the generic copy and fails this.
    expect(screen.getAllByTitle("Contract").length).toBeGreaterThan(0);
  });

  it("falls back to the generic copy when the server sent no value", () => {
    // An older viewer serving this bundle omits the field: the honest render is the reason
    // WITHOUT a quote, never `undefined` in a tooltip and never a missing chip.
    renderRow(null);
    expect(screen.getAllByText("not full-time").length).toBeGreaterThan(0);
    expect(screen.getAllByTitle(/metadata/).length).toBeGreaterThan(0);
  });
});
