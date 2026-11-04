import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QueueRowItem } from "../components/QueueRowItem";
import { SponsorBadge } from "../components/SponsorBadge";
import { queueRow } from "../test/rows";

/*
 * The "H-1B filer" badge beside the company. Present only when the server sent a record; with none
 * it leaves no text, no "unknown" and no placeholder. The counts below are the fixture's own.
 */

const SEEN = { computing_rows: 7, computing_low_wage_rows: 2, latest_decision: "2026-03-01" };

function renderRow(overrides = {}) {
  return render(
    <QueueRowItem
      row={queueRow({ company: "Example Employer", ...overrides })}
      selected={false}
      active
      collapsing={false}
      onSelect={() => undefined}
    />,
  );
}

describe("the H-1B filer badge", () => {
  it("shows the badge with the counts and the not-a-promise words in its tooltip", () => {
    const { container } = renderRow({ sponsor_seen: SEEN });
    const badge = screen.getByText("H-1B filer");
    const tip = badge.getAttribute("title") ?? "";
    expect(tip).toContain("7 computing roles");
    expect(tip).toContain("2 at wage level I or II");
    expect(tip).toContain("latest decision 2026-03-01");
    expect(tip).toContain("from public DOL filings; not a promise of sponsorship");
    // Beside the company, in the same line.
    expect(badge.closest("button")?.textContent).toContain("Example Employer");
    expect(container.querySelectorAll("[title]").length).toBeGreaterThan(0);
  });

  it("gives a screen reader the same sentence as text, not only as a title", () => {
    const { container } = renderRow({ sponsor_seen: SEEN });
    const hidden = container.querySelector(".sr-only");
    expect(hidden?.textContent).toContain("7 computing roles");
    expect(hidden?.textContent).toContain("not a promise of sponsorship");
  });

  it("omits the latest-decision clause when none is recorded", () => {
    renderRow({ sponsor_seen: { ...SEEN, latest_decision: null } });
    expect(screen.getByText("H-1B filer").getAttribute("title")).not.toContain("latest decision");
  });

  it("renders nothing at all for null", () => {
    const { container } = renderRow({ sponsor_seen: null });
    expect(screen.queryByText("H-1B filer")).toBeNull();
    expect(container.textContent).not.toMatch(/H-1B|unknown|sponsor/i);
    expect(container.querySelector(".sr-only")).toBeNull();
  });

  it("renders nothing when an older server omits the field", () => {
    const { container } = renderRow();
    expect(container.textContent).not.toMatch(/H-1B|unknown|sponsor/i);
    expect(container.querySelector(".sr-only")).toBeNull();
  });
});

describe("the workspace form of the badge", () => {
  it("prints the sentence as visible text, so a keyboard reader needs no tooltip", () => {
    const { container } = render(<SponsorBadge seen={SEEN} showReason />);
    expect(container.textContent).toContain("from public DOL filings; not a promise of sponsorship");
    expect(container.querySelector(".sr-only")).toBeNull();
  });

  it("is empty for null and for undefined", () => {
    expect(render(<SponsorBadge seen={null} showReason />).container.textContent).toBe("");
    expect(render(<SponsorBadge seen={undefined} />).container.textContent).toBe("");
  });
});
