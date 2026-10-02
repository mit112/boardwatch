import { describe, expect, it } from "vitest";

import type { QueueDetail, RequirementView, ReviewReason } from "../api/types";
import {
  REASON_PLAIN,
  classifyRequirements,
  nothingFlaggedSentence,
  requirementState,
  reviewsDiffer,
  rowNote,
  whatToCheck,
} from "../lib/jobStatus";
import { queueRow } from "../test/rows";

/*
 * The invariants the redesign promises about STATUS, tested as the promises are worded:
 *
 *   - an unknown requirement is never satisfied and never unmet, however it is presented;
 *   - two readings that disagree stay discoverable, and a reading nobody took is not a disagreement;
 *   - a job with something to check is never summarised as clear.
 *
 * The expected values are written out by hand from those sentences, not computed by calling the
 * helper under test a second time.
 */

function requirement(overrides: Partial<RequirementView> = {}): RequirementView {
  return {
    requirement: "1+ years of professional experience",
    covered: false,
    rule: "experience.min_years",
    disposition: "unknown",
    profile_field: null,
    quote: "1+ years of professional experience",
    rationale: null,
    ...overrides,
  };
}

function detail(requirements: RequirementView[], row = queueRow()): QueueDetail {
  return { row, jd_body: "body", requirements, board_target: null };
}

describe("requirement states", () => {
  it("never reads an unknown requirement as unmet, though the wire says covered:false", () => {
    // `covered` is `disposition == "met"` server-side, so an unknown arrives as covered:false —
    // exactly the shape that used to be listed under "Missing".
    const unknown = requirement({ covered: false, disposition: "unknown" });
    expect(requirementState(unknown)).toBe("unconfirmed");

    const sorted = classifyRequirements([unknown]);
    expect(sorted.unconfirmed).toEqual([unknown]);
    expect(sorted.unmet).toEqual([]);
    expect(sorted.satisfied).toEqual([]);
  });

  it("keeps met, unmet and unknown in three separate groups", () => {
    const met = requirement({ requirement: "A", covered: true, disposition: "met" });
    const unmet = requirement({ requirement: "B", covered: false, disposition: "unmet" });
    const unknown = requirement({ requirement: "C", covered: false, disposition: "unknown" });
    const sorted = classifyRequirements([met, unmet, unknown]);
    expect(sorted.satisfied.map((item) => item.requirement)).toEqual(["A"]);
    expect(sorted.unmet.map((item) => item.requirement)).toEqual(["B"]);
    expect(sorted.unconfirmed.map((item) => item.requirement)).toEqual(["C"]);
  });

  it("never treats a missing disposition as a passed check, even when covered is true", () => {
    // A rule row with no disposition was not assessed. `covered: true` must not rescue it.
    const odd = requirement({ covered: true, disposition: null });
    expect(requirementState(odd)).toBe("not_assessed");
    expect(classifyRequirements([odd]).satisfied).toEqual([]);
  });

  it("keeps résumé keywords out of the eligibility groups entirely", () => {
    const keyword = requirement({
      requirement: "kubernetes",
      covered: false,
      rule: null,
      disposition: null,
      quote: null,
    });
    const sorted = classifyRequirements([keyword]);
    // A résumé keyword missing from the résumé is not an unmet requirement of the job.
    expect(sorted.unmet).toEqual([]);
    expect(sorted.unconfirmed).toEqual([]);
    expect(sorted.keywordsAbsent).toEqual([keyword]);
  });
});

describe("independent readings", () => {
  it("flags a disagreement only when both engines spoke", () => {
    expect(reviewsDiffer({ verdict: "eligible", judge_verdict: "uncertain" })).toBe(true);
    expect(reviewsDiffer({ verdict: "uncertain", judge_verdict: "eligible" })).toBe(true);
    expect(reviewsDiffer({ verdict: "eligible", judge_verdict: "eligible" })).toBe(false);
    // The control: a gate that never spoke is a reading nobody took, not a second opinion.
    expect(reviewsDiffer({ verdict: "eligible", judge_verdict: null })).toBe(false);
    expect(reviewsDiffer({ verdict: null, judge_verdict: "eligible" })).toBe(false);
  });

  it("puts the disagreement in What to check, so it is found without opening the disclosure", () => {
    const row = queueRow({ verdict: "eligible", judge_verdict: "uncertain" });
    const keys = whatToCheck(detail([], row)).map((item) => item.key);
    expect(keys).toContain("differ");
  });
});

describe("what to check", () => {
  it("lists an unknown experience requirement as something to check, with its quote", () => {
    const row = queueRow({ verdict: "uncertain", review_reason: "experience_requirement" });
    const items = whatToCheck(detail([requirement()], row));
    const check = items.find((item) => item.key.startsWith("unconfirmed:"));
    expect(check?.headline).toBe("Check: 1+ years of professional experience");
    expect(check?.tone).toBe("warn");
    expect(check?.quote).toBe("1+ years of professional experience");
    // And it is not also reported as a blocker.
    expect(items.some((item) => item.key.startsWith("unmet:"))).toBe(false);
  });

  it("lists a confirmed-unmet requirement as a blocker, before anything softer", () => {
    const unmet = requirement({ requirement: "10+ years", disposition: "unmet" });
    const unknown = requirement({ requirement: "A degree", disposition: "unknown" });
    const items = whatToCheck(detail([unknown, unmet]));
    expect(items[0]?.tone).toBe("bad");
    expect(items[0]?.headline).toBe("Not met: 10+ years");
  });

  it("keeps a material blocker when the posting is also unverifiable", () => {
    const row = queueRow({ status: "unverifiable", verdict: "ineligible" });
    const tones = whatToCheck(
      detail([requirement({ disposition: "unmet", requirement: "US citizenship" })], row),
    ).map((item) => item.tone);
    expect(tones).toContain("bad");
    expect(tones).toContain("warn");
  });

  it("says nothing was flagged only when something was actually checked", () => {
    const clear = queueRow({ verdict: "eligible", judge_verdict: "eligible" });
    expect(nothingFlaggedSentence(clear, 3)).toBe(
      "Nothing flagged: the rules found no blocker and the independent review found no blocker.",
    );
    // No requirements extracted: "nothing flagged" would read as a pass, so it says it did not check.
    expect(nothingFlaggedSentence(clear, 0)).toContain("nothing was actually checked");
  });
});

describe("the list row's one status line", () => {
  it("names the review reason in plain words rather than the pipeline's label", () => {
    const row = queueRow({ verdict: "uncertain", review_reason: "experience_requirement" });
    expect(rowNote(row)).toEqual({ label: "Check the experience requirement", tone: "warn" });
  });

  it("puts a closed posting ahead of every other signal", () => {
    const row = queueRow({
      status: "closed",
      verdict: "uncertain",
      review_reason: "experience_requirement",
      judge_verdict: "uncertain",
    });
    expect(rowNote(row)?.label).toBe("Posting is closed");
  });

  it("says nothing for a job with nothing to flag, and flags a missing résumé", () => {
    expect(rowNote(queueRow({ verdict: "eligible", judge_verdict: "eligible" }))).toBeNull();
    expect(rowNote(queueRow({ verdict: "eligible", pdf_available: false }))?.label).toBe(
      "No résumé built for this job",
    );
  });

  it("states both readings when the rules and the review differ, with the right tone", () => {
    expect(rowNote(queueRow({ verdict: "eligible", judge_verdict: "uncertain" }))).toEqual({
      label: "Rules found no blocker; independent review is unsure",
      tone: "warn",
      coversDisagreement: true,
    });
    // A confirmed blocker on either side is not a "maybe".
    expect(rowNote(queueRow({ verdict: "eligible", judge_verdict: "ineligible" }))?.tone).toBe("bad");
    // Agreement, or a reading nobody took, is not a disagreement.
    expect(rowNote(queueRow({ verdict: "uncertain", judge_verdict: "uncertain" }))?.coversDisagreement).toBeUndefined();
    expect(rowNote(queueRow({ verdict: "eligible", judge_verdict: null, pdf_available: true }))).toBeNull();
  });

  it("shows the body-seniority reading on an apply-lane job, where nothing else carries it", () => {
    const row = queueRow({
      verdict: "eligible",
      judge_verdict: "eligible",
      judge_seniority_above_band: true,
    });
    expect(rowNote(row)?.label).toBe("Description reads senior");
    expect(whatToCheck(detail([], row)).map((item) => item.key)).toContain("seniority-body");
    // On a review row the reason already says it; it must not be said twice.
    const held = queueRow({
      verdict: "uncertain",
      review_reason: "seniority_judged_above_band",
      judge_seniority_above_band: true,
    });
    expect(whatToCheck(detail([], held)).map((item) => item.key)).not.toContain("seniority-body");
  });

  it("does not call an unverifiable posting open or closed", () => {
    const note = rowNote(queueRow({ status: "unverifiable", verdict: "eligible" }));
    expect(note?.label).toBe("Posting availability hasn’t been verified");
  });

  it("has a plain sentence for every review reason the server can send", () => {
    // The map is `Record<ReviewReason, …>`, so the compiler enforces coverage; this pins that no
    // entry is empty, which the compiler cannot see.
    for (const [reason, words] of Object.entries(REASON_PLAIN)) {
      expect(words.next.length, reason).toBeGreaterThan(8);
      expect(words.detail.length, reason).toBeGreaterThan(20);
    }
    const reasons = Object.keys(REASON_PLAIN) as ReviewReason[];
    expect(reasons).toHaveLength(15);
  });
});
