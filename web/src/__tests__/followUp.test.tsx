import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { QueueDetail } from "../api/types";
import { DetailPane } from "../components/DetailPane";
import { QueueRowItem } from "../components/QueueRowItem";
import { sortRows } from "../lib/sort";
import type { SortState } from "../lib/sort";
import { queueResponse, queueRow, withoutFields } from "../test/rows";

/*
 * Follow-up dates: a date pinned to a lead, the marker that says it is due, and the band facet
 * that filters to the due ones.
 *
 * Two properties carry this feature and each test below is written against the way it is easy to
 * get wrong:
 *
 *  1. DUE is never colour alone (SC 1.4.1). The word "due" is in the chip's own text, so the
 *     assertions below read TEXT — a treatment that only changed the border would fail them.
 *  2. `follow_up` is newer than this page's oldest possible server, which serves this bundle from
 *     DISK while answering from the Python it imported at STARTUP (D-360). The key is then absent,
 *     not null, and the row still has to draw.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  getQueue: vi.fn(),
  getDetail: vi.fn(),
  getAnswers: vi.fn(),
  getRuns: vi.fn(),
  getFunnel: vi.fn(),
  markApplied: vi.fn(),
  markSkipped: vi.fn(),
  unskip: vi.fn(),
  report: vi.fn(),
  unreport: vi.fn(),
  setFollowUp: vi.fn(),
  clearFollowUp: vi.fn(),
  revealFolder: vi.fn(),
  openPdf: vi.fn(),
}));

// Imported AFTER the mock factory, which vitest hoists above both.
import { clearFollowUp, getAnswers, getDetail, getQueue, setFollowUp } from "../api/client";
import { App } from "../App";

/** A local ISO date `days` from today, built from LOCAL parts — `toISOString()` is UTC. */
function isoDaysFromToday(days: number): string {
  const when = new Date();
  when.setDate(when.getDate() + days);
  const month = String(when.getMonth() + 1).padStart(2, "0");
  const day = String(when.getDate()).padStart(2, "0");
  return `${String(when.getFullYear())}-${month}-${day}`;
}

function renderRow(row: Parameters<typeof QueueRowItem>[0]["row"]) {
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

function detailFor(overrides = {}): QueueDetail {
  return {
    row: queueRow(overrides),
    jd_body: "About the team. We build and operate the systems that move every request.",
    requirements: [],
    board_target: null,
  };
}

function renderPane(detail: QueueDetail, onFollowUp: (date: string | null) => void) {
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
      onFollowUp={onFollowUp}
      onToast={() => undefined}
    />,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("the due marker on a row", () => {
  it("says DUE in words for a date in the past", () => {
    renderRow(queueRow({ follow_up: "2026-01-05" }));
    // TEXT, not a class: the word is the second channel, so a colour-only treatment fails here.
    expect(screen.getAllByText("follow-up due 2026-01-05").length).toBeGreaterThan(0);
  });

  it("says DUE for today, because due is <= today and never == today", () => {
    const today = isoDaysFromToday(0);
    renderRow(queueRow({ follow_up: today }));
    expect(screen.getAllByText(`follow-up due ${today}`).length).toBeGreaterThan(0);
  });

  it("shows the date WITHOUT the due marker for a date in the future", () => {
    const later = isoDaysFromToday(30);
    renderRow(queueRow({ follow_up: later }));
    expect(screen.getAllByText(`follow-up ${later}`).length).toBeGreaterThan(0);
    expect(screen.queryByText(`follow-up due ${later}`)).toBeNull();
  });

  it("renders nothing when no follow-up is pinned", () => {
    const { container } = renderRow(queueRow({ follow_up: null }));
    expect(container.textContent).not.toContain("follow-up");
  });

  it("still draws the row when the server never sent the key at all", () => {
    // An older API omits `follow_up` entirely, so the read is `undefined`. A guard written
    // `=== null` waves it through and the chip renders "follow-up undefined".
    const stale = withoutFields(queueRow({ title: "Backend Engineer" }), ["follow_up"]);
    const { container } = renderRow(stale);
    expect(screen.getAllByTitle("Backend Engineer").length).toBeGreaterThan(0);
    expect(container.textContent).not.toContain("follow-up");
    expect(container.textContent).not.toContain("undefined");
  });
});

describe("the detail pane's date input", () => {
  it("sends the typed date up", () => {
    const onFollowUp = vi.fn();
    renderPane(detailFor(), onFollowUp);

    const input = screen.getByLabelText("Follow up on");
    // A NATIVE date input, not a modal and not a text box: the platform's own picker in place
    // (`anti-patterns/anti-modal-overuse`).
    expect(input.getAttribute("type")).toBe("date");
    fireEvent.change(input, { target: { value: "2026-09-20" } });
    expect(onFollowUp).toHaveBeenCalledWith("2026-09-20");
  });

  it("sends null from Clear, and offers Clear only where there is one to clear", () => {
    const onFollowUp = vi.fn();
    const { unmount } = renderPane(detailFor(), onFollowUp);
    // Nothing pinned: the control is present but disabled, rather than a button that can only
    // ever be a no-op.
    expect(screen.getByRole("button", { name: "Clear follow-up" }).hasAttribute("disabled")).toBe(
      true,
    );
    unmount();

    renderPane(detailFor({ follow_up: "2026-09-20" }), onFollowUp);
    fireEvent.click(screen.getByRole("button", { name: "Clear follow-up" }));
    expect(onFollowUp).toHaveBeenCalledWith(null);
  });

  it("writes NOTHING when the input goes empty, so a half-typed edit cannot drop the date", () => {
    // A date input reports "" for any incomplete date, so an empty `change` is an edit in
    // progress and not a clear. Routing it to a clear would silently drop a stored date.
    const onFollowUp = vi.fn();
    renderPane(detailFor({ follow_up: "2026-09-20" }), onFollowUp);
    fireEvent.change(screen.getByLabelText("Follow up on"), { target: { value: "" } });
    expect(onFollowUp).not.toHaveBeenCalled();
  });

  it("shows the date the lead already carries", () => {
    renderPane(detailFor({ follow_up: "2026-09-20" }), vi.fn());
    expect(screen.getByLabelText<HTMLInputElement>("Follow up on").value).toBe("2026-09-20");
  });

  it("shows an empty input, not the string 'undefined', on a server that omits the key", () => {
    const detail = detailFor();
    const stale: QueueDetail = { ...detail, row: withoutFields(detail.row, ["follow_up"]) };
    renderPane(stale, vi.fn());
    expect(screen.getByLabelText<HTMLInputElement>("Follow up on").value).toBe("");
  });
});

describe("the write path", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function rowElement(): HTMLElement {
    const found = within(screen.getByRole("grid", { name: "Queue" }))
      .getAllByRole("row")
      .find((element) => element.hasAttribute("data-row-id"));
    if (found === undefined) throw new Error("no data row");
    return found;
  }

  async function openLead() {
    const row = queueRow({ company: "Globex", title: "Backend Engineer" });
    vi.mocked(getQueue).mockResolvedValue(queueResponse([row]));
    vi.mocked(getAnswers).mockResolvedValue({
      identity: {},
      work_auth: {},
      education: [],
      questions: [],
    });
    vi.mocked(getDetail).mockResolvedValue({
      row,
      jd_body: null,
      requirements: [],
      board_target: null,
    });
    render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    // The ROW, not the title button: the row carries several controls whose names include the
    // title, and clicking the row is what opens the pane anyway.
    fireEvent.click(rowElement());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    return row;
  }

  it("round-trips the date through client.ts and offers an undo that clears it", async () => {
    const row = await openLead();
    vi.mocked(setFollowUp).mockResolvedValue({
      outcome: "follow_up_set",
      follow_up: "2026-09-20",
    });
    vi.mocked(clearFollowUp).mockResolvedValue({
      outcome: "follow_up_cleared",
      follow_up: null,
    });

    fireEvent.change(screen.getByLabelText("Follow up on"), {
      target: { value: "2026-09-20" },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(vi.mocked(setFollowUp)).toHaveBeenCalledWith(row.posting_id, "2026-09-20");
    // Optimistic: the ROW shows it before any refetch, and the lead has NOT left the queue —
    // a follow-up is a note, not a disposition.
    const queue = screen.getByRole("grid", { name: "Queue" });
    expect(within(queue).getAllByText("follow-up 2026-09-20").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.mocked(clearFollowUp)).toHaveBeenCalledWith(row.posting_id);
    // The exact chip text, not `/follow-up/`: the grid's own sort control is called "follow-up".
    expect(
      within(screen.getByRole("grid", { name: "Queue" })).queryByText("follow-up 2026-09-20"),
    ).toBeNull();
  });

  it("puts the previous date back when the write fails", async () => {
    await openLead();
    let fail: (reason: unknown) => void = () => undefined;
    const pending = new Promise<never>((_resolve, reject) => {
      fail = reject;
    });
    pending.catch(() => undefined);
    vi.mocked(setFollowUp).mockReturnValue(pending);

    fireEvent.change(screen.getByLabelText("Follow up on"), {
      target: { value: "2026-09-20" },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(
      within(screen.getByRole("grid", { name: "Queue" })).getAllByText("follow-up 2026-09-20")
        .length,
    ).toBeGreaterThan(0);

    await act(async () => {
      fail(new Error("400 from /api/queue/1/followup"));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(
      within(screen.getByRole("grid", { name: "Queue" })).queryByText("follow-up 2026-09-20"),
    ).toBeNull();
    expect(screen.getByText("400 from /api/queue/1/followup")).toBeTruthy();
  });

  it("f on the focused row moves the cursor into the date input", async () => {
    await openLead();
    // Close the pane first, so `f` is the thing that opens it.
    fireEvent.click(screen.getByRole("button", { name: "Close detail" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    const dataRow = rowElement();
    dataRow.focus();
    fireEvent.keyDown(dataRow, { key: "f" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(document.activeElement).toBe(screen.getByLabelText("Follow up on"));
  });
});

describe("the follow-up due facet", () => {
  it("filters BOTH lanes to the leads that are due", async () => {
    const due = isoDaysFromToday(-1);
    const later = isoDaysFromToday(10);
    vi.mocked(getQueue).mockResolvedValue(
      queueResponse(
        [
          queueRow({ title: "APPLY-DUE", follow_up: due }),
          queueRow({ title: "APPLY-LATER", follow_up: later }),
          queueRow({ title: "APPLY-NONE", follow_up: null }),
        ],
        [queueRow({ title: "REVIEW-DUE", follow_up: due, review_reason: "non_us_location" })],
      ),
    );
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });
    fireEvent.click(screen.getByRole("button", { name: "show" }));

    // The cell counts the apply lane, exactly as `eligible` does: one due row there.
    fireEvent.click(screen.getByRole("button", { name: /^follow-up due 1 —/i }));

    const queue = within(screen.getByRole("grid", { name: "Queue" }));
    expect(queue.queryByText("APPLY-DUE")).not.toBeNull();
    expect(queue.queryByText("APPLY-LATER")).toBeNull();
    expect(queue.queryByText("APPLY-NONE")).toBeNull();
    // The review lane is reached too: a due review lead is work for today just as much.
    const review = within(screen.getByRole("grid", { name: "Review" }));
    expect(review.queryByText("REVIEW-DUE")).not.toBeNull();
  });
});

describe("sorting by follow-up", () => {
  it("orders by date and puts leads with no follow-up last in BOTH directions", () => {
    const rows = [
      queueRow({ title: "NONE", follow_up: null }),
      queueRow({ title: "LATE", follow_up: "2026-12-01" }),
      queueRow({ title: "EARLY", follow_up: "2026-09-20" }),
    ];
    const asc: SortState = { key: "follow_up", direction: "asc" };
    const desc: SortState = { key: "follow_up", direction: "desc" };
    expect(sortRows(rows, asc, () => 1).map((row) => row.title)).toEqual([
      "EARLY",
      "LATE",
      "NONE",
    ]);
    expect(sortRows(rows, desc, () => 1).map((row) => row.title)).toEqual([
      "LATE",
      "EARLY",
      "NONE",
    ]);
  });

  it("does not throw on a row from a server that never sent the key", () => {
    const stale = withoutFields(queueRow(), ["follow_up"]);
    const asc: SortState = { key: "follow_up", direction: "asc" };
    expect(() =>
      sortRows([stale, queueRow({ follow_up: "2026-09-20" })], asc, () => 1),
    ).not.toThrow();
  });
});
