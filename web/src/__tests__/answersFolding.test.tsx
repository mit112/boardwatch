import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Answers } from "../api/types";
import { AnswersPanel } from "../components/AnswersPanel";

/*
 * Measured on the live store: the identity block rendered seven rows, every one of them reading
 * "not set", and the panel was 779px of a 2,050px pane. An unset row is not the same weight as a
 * set one — it is a gap in the local profile, not an answer to copy — so the unset ones fold
 * behind a single line that states the ratio.
 */

const ANSWERS: Answers = {
  identity: {
    full_name: "Example Person",
    email: "person@example.com",
    phone: null,
    city: null,
    linkedin: null,
  },
  work_auth: { status: "EAD or similar (work authorization document)" },
  education: [],
  questions: [],
};

describe("the answers panel", () => {
  it("folds every unset row behind one line that states the ratio", () => {
    const { container } = render(<AnswersPanel answers={ANSWERS} onError={() => undefined} />);
    const details = container.querySelectorAll("details");
    expect(details.length).toBeGreaterThan(0);
    const identityFold = Array.from(details).find((element) =>
      element.querySelector("summary")?.textContent?.includes("of 5 set"),
    );
    expect(identityFold).toBeDefined();
    expect(identityFold?.querySelector("summary")?.textContent).toBe("2 of 5 set");
    // The three unset fields are inside the fold, not beside the set ones.
    const folded = within(identityFold as HTMLElement);
    folded.getByText("phone");
    folded.getByText("city");
    folded.getByText("linkedin");
  });

  it("leaves the set rows in the open, where they can be copied", () => {
    render(<AnswersPanel answers={ANSWERS} onError={() => undefined} />);
    const name = screen.getByText("full name");
    expect(name.closest("details")).toBeNull();
  });

  it("draws no fold at all when every field is set", () => {
    const complete: Answers = { ...ANSWERS, identity: { full_name: "Example Person" } };
    const { container } = render(<AnswersPanel answers={complete} onError={() => undefined} />);
    const summaries = Array.from(container.querySelectorAll("summary")).map(
      (element) => element.textContent,
    );
    expect(summaries.filter((text) => text?.endsWith("of 1 set"))).toHaveLength(0);
  });

  it("starts collapsed when the caller says the description is the next read", () => {
    render(
      <AnswersPanel answers={ANSWERS} defaultOpen={false} onError={() => undefined} />,
    );
    const toggle = screen.getByRole("button", { name: /Application answers/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });
});
