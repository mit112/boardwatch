import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { QueueDetail, QueueRow, ReviewReason } from "../api/types";
import { DetailPane } from "../components/DetailPane";
import { QueueRowItem } from "../components/QueueRowItem";
import { REASON_PLAIN, whatToCheck } from "../lib/jobStatus";
import { queueRow } from "../test/rows";

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  openPdf: vi.fn(),
  revealFolder: vi.fn(),
}));

/*
 * The WORDING of each review reason, in plain language.
 *
 * Each reason reaches the page as a `review_reason` code, and the failure these tests guard
 * against is a wording one: this is the only place the reader learns which requirement held a job,
 * so rendering an abstain as a decision spends a judgement the engine explicitly declined to make.
 *
 * `REASON_PLAIN` is a `Record<ReviewReason, ...>`, so a member added server-side and mirrored in
 * `api/types.ts` but forgotten here is already a compile error. What that cannot catch is a member
 * mapped to the WRONG words, or two members collapsed onto one — which is exactly what these assert.
 */
describe("the plain-language review reasons", () => {
  it("names a hard-family abstain as an abstain, never as an ineligible verdict", () => {
    const text = REASON_PLAIN.eligibility_unconfirmed.detail;
    expect(text).toMatch(/could not decide this either way/i);
    // The distinction the whole member exists for: an abstain is NOT a finding of ineligibility.
    expect(text).toMatch(/not a finding that you are ineligible/i);
  });

  it("names an unconfirmed experience bar as something that may well be satisfied", () => {
    const words = REASON_PLAIN.experience_requirement;
    expect(words.next).toBe("Check the experience requirement");
    expect(words.detail).toMatch(/does not confirm you meet/i);
    expect(words.detail).toMatch(/may well be satisfied/i);
  });

  it("words the two absences as absences of OURS, never as claims about the posting", () => {
    // These jobs were cleared by SILENCE, so the copy must not read as a finding about the JD.
    // "This posting has no requirements" would be exactly that finding.
    const found = REASON_PLAIN.no_requirements_found.detail;
    expect(found).toMatch(/could be extracted/i);
    expect(found).toMatch(/says nothing about the job itself/i);
    expect(found).not.toMatch(/this posting has no requirement/i);

    const unevaluated = REASON_PLAIN.unevaluated.detail;
    expect(unevaluated).toMatch(/nothing has evaluated this job/i);
    // The transience is the difference from the other absence, and it is what the reader acts on:
    // one clears itself on a later run, the other never will.
    expect(unevaluated).toMatch(/later run/i);
  });

  it("does not claim a role-vetoed job is not software, nor an unconfirmed one a veto", () => {
    expect(REASON_PLAIN.role_vetoed.detail).not.toMatch(/not software/i);
    const unconfirmed = REASON_PLAIN.role_unconfirmed.detail;
    expect(unconfirmed).toMatch(/abstain, not a veto/i);
    expect(unconfirmed).not.toMatch(/off target/i);
  });

  it("reports an unmeasured role check as a missing list, never as a veto", () => {
    const words = REASON_PLAIN.role_gate_unmeasured;
    // States what is MISSING on our side, never a reading of the title.
    expect(words.detail).toMatch(/no role list/i);
    expect(words.detail).toMatch(/not a judgement about the role/i);
    expect(words.next).not.toMatch(/veto/i);
  });

  it("names a revision as a move under the résumé, not as a finding about the posting", () => {
    const words = REASON_PLAIN.revised_since_build;
    expect(words.next).toMatch(/after your résumé was built/i);
    expect(words.detail).toMatch(/check the résumé still fits/i);
  });

  it("gives every reason its OWN sentence, so no two holds read alike", () => {
    const reasons = Object.keys(REASON_PLAIN) as ReviewReason[];
    expect(reasons).toHaveLength(15);
    const lines = reasons.map((reason) => REASON_PLAIN[reason].next);
    expect(new Set(lines).size).toBe(lines.length);
    const details = reasons.map((reason) => REASON_PLAIN[reason].detail);
    expect(new Set(details).size).toBe(details.length);
  });
});

function renderRow(overrides: Partial<QueueRow>) {
  return render(
    <QueueRowItem
      row={queueRow(overrides)}
      selected={false}
      active
      collapsing={false}
      onSelect={() => undefined}
    />,
  );
}

describe("the role-vetoed compact row", () => {
  it("states the veto once, in plain words, with no second 'off target' mark", () => {
    renderRow({ review_reason: "role_vetoed", off_target: true, off_target_reason: "matched: vice president" });
    screen.getByText("Role check flagged the title");
    expect(screen.queryByText(/off target/i)).toBeNull();
  });

  it("carries the matched phrase into What to check, where the evidence belongs", () => {
    const row = queueRow({
      review_reason: "role_vetoed",
      off_target: true,
      off_target_reason: "matched: vice president",
    });
    const check = whatToCheck({ row, jd_body: "x", requirements: [], board_target: null }).find(
      (item) => item.key === "reason:role_vetoed",
    );
    expect(check?.body).toContain("matched: vice president");
  });
});

function detailFor(row: QueueRow): QueueDetail {
  return { row, jd_body: "A job description.", requirements: [], board_target: null };
}

function renderPane(row: QueueRow) {
  return render(
    <DetailPane
      detail={detailFor(row)}
      loading={false}
      error={null}
      answers={null}
      onClose={() => undefined}
      onApplied={() => undefined}
      onSkip={() => undefined}
      onReport={() => undefined}
      onFollowUp={() => undefined}
      onToast={() => undefined}
    />,
  );
}

function whatToCheckSection(): HTMLElement {
  const section = screen.getByRole("heading", { name: "What to check" }).closest("section");
  if (section === null) throw new Error("What to check is not a section");
  return section;
}

describe("the form-hard-stop job quotes the question the JD does not contain", () => {
  it("shows the quoted application-form question, the only place the reader can find it", () => {
    renderPane(
      queueRow({
        verdict: "uncertain",
        review_reason: "form_question_hard_stop",
        form_question: "Are you a US citizen or permanent resident?",
      }),
    );
    const section = within(whatToCheckSection());
    section.getByText("Application form has a hard-stop question");
    section.getByText("“Are you a US citizen or permanent resident?”");
  });

  it("states the generic copy, with no invented quote, when the server sent none", () => {
    renderPane(
      queueRow({ verdict: "uncertain", review_reason: "form_question_hard_stop", form_question: null }),
    );
    const section = within(whatToCheckSection());
    section.getByText("Application form has a hard-stop question");
    expect(section.queryByText(/“/)).toBeNull();
  });
});

describe("the not-full-time job quotes the provider field the JD does not contain", () => {
  it("shows the provider's own value, labelled as the board's field and not a verdict", () => {
    renderPane(
      queueRow({
        verdict: "uncertain",
        review_reason: "provider_employment_type",
        provider_employment_type: "CONTRACTOR",
      }),
    );
    const section = within(whatToCheckSection());
    section.getByText("May not be full-time");
    section.getByText("“CONTRACTOR”");
    section.getByText(/the job board['’]s own employment-type field/i);
  });

  it("states the generic copy, with no invented value, when the server sent none", () => {
    renderPane(
      queueRow({
        verdict: "uncertain",
        review_reason: "provider_employment_type",
        provider_employment_type: null,
      }),
    );
    const section = within(whatToCheckSection());
    section.getByText("May not be full-time");
    expect(section.queryByText(/“/)).toBeNull();
  });
});
