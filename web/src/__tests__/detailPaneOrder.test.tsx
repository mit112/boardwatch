import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Answers, QueueDetail, RequirementView } from "../api/types";
import { DetailPane } from "../components/DetailPane";
import { queueRow } from "../test/rows";

/*
 * What the pane says FIRST, and how many times it says one fact.
 *
 * Measured on the live store: the pane scrolled 2,050px, of which the answers panel — expanded,
 * every identity row reading "not set" — was 779px, and it sat ABOVE the job description that the
 * requirements block's own copy tells the reader to go and read. The decision block stated the
 * status three times and the coverage twice. None of that is visible to a type checker, so it is
 * pinned here as DOM order and as the absence of duplicated cells.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  openPdf: vi.fn(),
  revealFolder: vi.fn(),
}));

const ANSWERS: Answers = {
  identity: { full_name: "Example Person", email: "person@example.com", phone: null },
  work_auth: { status: "EAD or similar (work authorization document)", sponsorship: null },
  education: [],
  questions: [],
};

function detailWith(requirements: RequirementView[], overrides = {}): QueueDetail {
  return {
    row: queueRow(overrides),
    jd_body: "About the team. We build and operate the systems that move every request.",
    requirements,
    board_target: "greenhouse:example",
  };
}

function renderPane(detail: QueueDetail, extra: { revealSupported?: boolean } = {}) {
  return render(
    <DetailPane
      detail={detail}
      loading={false}
      error={null}
      answers={ANSWERS}
      onClose={() => undefined}
      onApplied={() => undefined}
      onSkip={() => undefined}
      onReport={() => undefined}
      onToast={() => undefined}
      {...extra}
    />,
  );
}

const REQUIREMENT: RequirementView = {
  requirement: "python",
  covered: true,
  rule: "degree_level",
  disposition: "eligible",
  profile_field: "education.highest_degree",
  quote: "A bachelor's degree in computer science.",
  rationale: "Profile records a completed bachelor's degree.",
};

describe("the pane's reading order", () => {
  it("puts the job description ABOVE the application answers", () => {
    renderPane(detailWith([REQUIREMENT]));
    const description = screen.getByRole("heading", { name: "job description" });
    const answers = screen.getByRole("button", { name: /Application answers/ });
    // Bit 4 = DOCUMENT_POSITION_FOLLOWING: `answers` comes after `description` in the tree.
    expect(description.compareDocumentPosition(answers) & 4).toBe(4);
  });

  it("collapses the answers when no requirement was extracted, because the JD is the next read", () => {
    renderPane(detailWith([]));
    const answers = screen.getByRole("button", { name: /Application answers/ });
    expect(answers.getAttribute("aria-expanded")).toBe("false");
  });

  it("leaves the answers expanded when requirements WERE extracted", () => {
    renderPane(detailWith([REQUIREMENT]));
    const answers = screen.getByRole("button", { name: /Application answers/ });
    expect(answers.getAttribute("aria-expanded")).toBe("true");
  });
});

/**
 * The decision block alone. Scoped, because the answers panel further down also carries a
 * `work_auth.status` row, and an unscoped `getByText("status")` would be answered by that one —
 * a query that cannot fail for the reason the test is about.
 */
function decisionBlock(): HTMLElement {
  const section = screen.getByRole("heading", { level: 2 }).closest("section");
  if (section === null) throw new Error("the decision block is not a section");
  return section;
}

describe("the decision block", () => {
  it("drops the status fact when the status chip already carries it", () => {
    renderPane(detailWith([REQUIREMENT], { status: "closed" }));
    const block = within(decisionBlock());
    // The word was on screen three times: a fact cell, a chip, and the chip's sentence.
    expect(block.queryByText("status")).toBeNull();
    expect(block.getAllByText("closed")).toHaveLength(1);
  });

  it("keeps the status fact when no chip renders, so an open posting still states it", () => {
    renderPane(detailWith([REQUIREMENT], { status: "open" }));
    within(decisionBlock()).getByText("status");
  });

  it("drops the coverage fact when the thin-JD chip already carries it", () => {
    renderPane(detailWith([REQUIREMENT], { thin_jd: true, coverage: null }));
    const block = within(decisionBlock());
    block.getByText("thin JD");
    expect(block.queryByText("coverage · as of now")).toBeNull();
  });

  it("keeps the coverage fact on an ordinary posting", () => {
    renderPane(detailWith([REQUIREMENT], { thin_jd: false, coverage: 0.62 }));
    within(decisionBlock()).getByText("coverage · as of now");
  });

  it("shows the server's score explanation under the number", () => {
    const why = "target company (+0.30), title match (+0.25)";
    renderPane(detailWith([REQUIREMENT], { score: 0.9, why }));
    within(decisionBlock()).getByText(why);
  });
});

describe("the reveal button", () => {
  it("is omitted where the platform has no file-manager handler", () => {
    renderPane(detailWith([REQUIREMENT]), { revealSupported: false });
    expect(screen.queryByRole("button", { name: "Reveal folder" })).toBeNull();
  });

  it("renders by default, so an older server that omits the flag loses nothing", () => {
    renderPane(detailWith([REQUIREMENT]));
    screen.getByRole("button", { name: "Reveal folder" });
  });
});

describe("the description box", () => {
  it("offers an expand control that reports its own state", () => {
    renderPane(detailWith([REQUIREMENT]));
    const toggle = screen.getByRole("button", { name: /Expand the job description/i });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    const collapsed = screen.getByRole("button", { name: /Collapse the job description/i });
    expect(collapsed.getAttribute("aria-expanded")).toBe("true");
  });
});
