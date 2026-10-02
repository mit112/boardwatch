import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QueueRowItem } from "../components/QueueRowItem";
import { formatScore } from "../lib/format";
import { queueRow } from "../test/rows";

/*
 * One job row, rendered on its own.
 *
 * jsdom has NO layout, so nothing here measures a width: what is checkable is which FACTS the row
 * carries and which it deliberately leaves out. The row is a compact block beside a workspace, so
 * the contract is "what changes the next action is on it, and nothing else":
 *
 *   present   role, company, where, work arrangement, how long ago, the ONE thing to check first,
 *             whether a résumé is ready
 *   absent    the ranking score and the keyword match (neither says whether to apply), and any
 *             per-row action buttons (the workspace holds them; every one has a key on the row)
 */

function renderRow(overrides = {}) {
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

describe("the where line", () => {
  it("shows the primary location, how many more the posting carries, and the work arrangement", () => {
    renderRow({ location: "Austin, TX", locations: ["Austin, TX", "Remote"], remote_policy: "hybrid" });
    screen.getByText("Austin, TX +1 · hybrid");
  });

  it("puts the whole list in the title attribute, so nothing is destroyed by truncation", () => {
    const { container } = renderRow({
      location: "Austin, TX",
      locations: ["Austin, TX", "Remote"],
    });
    const titled = Array.from(container.querySelectorAll("[title]")).map((element) =>
      element.getAttribute("title"),
    );
    expect(titled).toContain("Austin, TX, Remote");
  });

  it("says the location is not listed when the posting carries none, and shows no +N", () => {
    renderRow({ location: null, locations: [], remote_policy: null });
    screen.getByText("Location not listed");
    expect(screen.queryByText(/\+\d/)).toBeNull();
  });

  it("keeps the arrangement when only the location is missing", () => {
    renderRow({ location: null, locations: [], remote_policy: "remote" });
    screen.getByText("remote");
    expect(screen.queryByText("Location not listed")).toBeNull();
  });
});

describe("what the row leaves out", () => {
  it("prints neither the ranking score nor the keyword match", () => {
    const { container } = renderRow({ score: 9.87, coverage: 0.62, why: "title match (+0.25)" });
    expect(container.textContent).not.toContain("9.87");
    expect(container.textContent).not.toContain("62%");
    expect(container.textContent).not.toContain("title match");
  });

  it("has no per-row buttons to write with — the workspace and the keys hold those", () => {
    renderRow();
    expect(screen.queryByRole("button", { name: /applied|record|skip|report/i })).toBeNull();
  });

  it("keeps the whole title reachable when it is long", () => {
    const title = "Senior Staff Principal Software Engineer, Distributed Systems Platform Reliability";
    const { container } = renderRow({ title });
    expect(container.querySelector(`[title="${title}"]`)).not.toBeNull();
  });
});

describe("the one thing to check first", () => {
  it("is in plain words, not the pipeline's label", () => {
    renderRow({ verdict: "uncertain", review_reason: "experience_requirement" });
    screen.getByText("Check the experience requirement");
    expect(screen.queryByText("experience requirement")).toBeNull();
  });

  it("is absent when nothing is flagged — and a ready résumé is the only other mark", () => {
    renderRow({ verdict: "eligible", judge_verdict: "eligible", pdf_available: true });
    screen.getByText("Résumé ready");
    expect(screen.queryByText(/check|unsure|aren’t confirmed|differ/i)).toBeNull();
  });

  it("flags a missing résumé once, not twice", () => {
    renderRow({ verdict: "eligible", judge_verdict: "eligible", pdf_available: false });
    expect(screen.getAllByText(/résumé/i)).toHaveLength(1);
  });

  it("states both readings in one line when the rules and the independent review differ", () => {
    renderRow({ verdict: "eligible", judge_verdict: "uncertain" });
    // Neither reading is dropped: the rules' clear is not hidden behind the review's doubt, and
    // the review's doubt is not hidden behind the rules' clear.
    screen.getByText("Rules found no blocker; independent review is unsure");
    expect(screen.queryByText("Rules and independent review differ")).toBeNull();
  });

  it("names the disagreement when the status line is about something else", () => {
    renderRow({
      verdict: "eligible",
      judge_verdict: "uncertain",
      review_reason: "non_us_location",
    });
    screen.getByText("Rules and independent review differ");
  });

  it("does not turn an unverifiable posting into an open one", () => {
    renderRow({ status: "unverifiable", verdict: "eligible", judge_verdict: "eligible" });
    screen.getByText("Posting availability hasn’t been verified");
  });
});

describe("formatScore", () => {
  it("prints two decimals, because every live row read 0.9 or 1.0 at one", () => {
    expect(formatScore(0.9)).toBe("0.90");
    expect(formatScore(1)).toBe("1.00");
  });
});
