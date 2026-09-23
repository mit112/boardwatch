import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AppliedIdenticalJd, QueueDetail, QueueRow } from "../api/types";
import { DetailPane } from "../components/DetailPane";
import { QueueRowItem } from "../components/QueueRowItem";
import { formatDateWithYear } from "../lib/format";
import { queueRow, withoutFields } from "../test/rows";

/*
 * T125: a lead whose job description is byte-identical to one the owner already applied to at the
 * same company says so — in WORDS, on the row and in the pane. Annotation only; nothing is hidden.
 *
 * The date is compared through `formatDateWithYear` rather than spelled out, because it renders in
 * the runner's own zone and locale; what these tests pin is that it is THERE, beside the location.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  openPdf: vi.fn(),
  revealFolder: vi.fn(),
}));

const ALEXANDRIA: AppliedIdenticalJd = {
  posting_id: 901,
  title: "Software Engineer, Platform",
  location: "Alexandria, VA",
  applied_at: "2026-09-14T15:30:00+00:00",
};
const RESTON: AppliedIdenticalJd = {
  posting_id: 902,
  title: "Software Engineer, Platform",
  location: "Reston, VA",
  applied_at: "2026-09-10T15:30:00+00:00",
};
const ARLINGTON: AppliedIdenticalJd = {
  posting_id: 903,
  title: "Software Engineer, Platform",
  location: "Arlington, VA",
  applied_at: null,
};

function renderPane(row: QueueRow) {
  const detail: QueueDetail = {
    row,
    jd_body: "We build and operate the systems that move every request.",
    requirements: [],
    board_target: null,
  };
  return render(
    <DetailPane
      detail={detail}
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

function renderRow(row: QueueRow) {
  return render(
    <QueueRowItem
      row={row}
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
}

describe("the pane", () => {
  it("names the applied posting's location and date", () => {
    renderPane(queueRow({ applied_identical_jd: [ALEXANDRIA] }));
    screen.getByText(
      `Applied to an identical JD: Alexandria, VA · ${formatDateWithYear(ALEXANDRIA.applied_at)}`,
    );
  });

  it("renders nothing when the list is empty, or when an older server omits it", () => {
    renderPane(queueRow({ applied_identical_jd: [] }));
    expect(screen.queryByText(/identical JD/)).toBeNull();
    renderPane(withoutFields(queueRow(), ["applied_identical_jd"]));
    expect(screen.queryByText(/identical JD/)).toBeNull();
  });

  it("shows the first plus +N, and every entry stays readable in the pane", () => {
    renderPane(queueRow({ applied_identical_jd: [ALEXANDRIA, RESTON, ARLINGTON] }));
    const summary = screen.getByText(
      `Applied to an identical JD: Alexandria, VA · ${formatDateWithYear(ALEXANDRIA.applied_at)} +2`,
    );
    // A native disclosure: the full list is its content, reachable by keyboard and in the tree.
    expect(summary.tagName).toBe("SUMMARY");
    const list = summary.closest("details");
    if (list === null) throw new Error("the +N line is not a disclosure");
    const entries = Array.from(list.querySelectorAll("li"), (item) => item.textContent);
    expect(entries).toEqual([
      `Alexandria, VA · ${formatDateWithYear(ALEXANDRIA.applied_at)} · Software Engineer, Platform`,
      `Reston, VA · ${formatDateWithYear(RESTON.applied_at)} · Software Engineer, Platform`,
      // No date recorded: the location alone, never an em dash standing in for a date.
      "Arlington, VA · Software Engineer, Platform",
    ]);
  });
});

describe("the list row", () => {
  it("carries a text badge that says it in words", () => {
    renderRow(queueRow({ applied_identical_jd: [ALEXANDRIA] }));
    // TEXT, never colour alone (SC 1.4.1). The row renders `Flags` in two tiers, hence `All`.
    const badges = screen.getAllByText("applied: identical JD");
    expect(badges.length).toBeGreaterThan(0);
    for (const badge of badges) {
      expect(badge.getAttribute("title")).toMatch(/identical job description/);
    }
  });

  it("carries no badge when the list is empty", () => {
    renderRow(queueRow({ applied_identical_jd: [] }));
    expect(screen.queryByText("applied: identical JD")).toBeNull();
  });
});
