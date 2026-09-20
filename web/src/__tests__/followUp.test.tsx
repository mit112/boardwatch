import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FollowUpResponse, QueueDetail } from "../api/types";
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

/**
 * The KEYBOARD path. A native date input fires `input` (React's `onChange`) on every segment edit
 * that leaves the value COMPLETE, so each of these is one keystroke landing on a whole date — and
 * a keystroke always reaches the input before the value it produced.
 */
function typeDate(input: HTMLElement, value: string): void {
  fireEvent.keyDown(input, { key: "2" });
  fireEvent.change(input, { target: { value } });
}

/**
 * The PICKER path. A click in the browser's own calendar popup dispatches no `keydown` to the
 * input — the popup is browser chrome and not in the document — so the value simply arrives.
 */
function pickDate(input: HTMLElement, value: string): void {
  fireEvent.change(input, { target: { value } });
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
  it("sends a date PICKED from the calendar up with no extra step", () => {
    const onFollowUp = vi.fn();
    renderPane(detailFor(), onFollowUp);

    const input = screen.getByLabelText("Follow up on");
    // A NATIVE date input, not a modal and not a text box: the platform's own picker in place
    // (`anti-patterns/anti-modal-overuse`).
    expect(input.getAttribute("type")).toBe("date");
    // One click in the calendar is one whole date and one intention, so it commits where it
    // lands: making the picker path wait for a blur as well would be a confirm step on a control
    // whose entire point is that it has none.
    pickDate(input, "2026-09-20");
    expect(onFollowUp).toHaveBeenCalledTimes(1);
    expect(onFollowUp).toHaveBeenCalledWith("2026-09-20");
  });

  it("commits a TYPED date once, on blur, and not once per segment", () => {
    // The defect this is written against: typing the year last walks the value through four
    // COMPLETE dates, and a commit per `onChange` wrote all four — four POSTs, four stacked
    // toasts whose undo carries an intermediate date, and a stored value decided by response
    // ordering rather than by the last keystroke. Commit on blur, per
    // `ux-interaction/forms/ux-form-validation-timing`.
    const onFollowUp = vi.fn();
    renderPane(detailFor(), onFollowUp);
    const input = screen.getByLabelText("Follow up on");

    for (const partial of ["0002-09-20", "0020-09-20", "0202-09-20", "2026-09-20"]) {
      typeDate(input, partial);
    }
    expect(onFollowUp).not.toHaveBeenCalled();
    // The draft is what the reader sees while typing — the field does not snap back mid-edit.
    expect(screen.getByLabelText<HTMLInputElement>("Follow up on").value).toBe("2026-09-20");

    fireEvent.blur(input);
    expect(onFollowUp).toHaveBeenCalledTimes(1);
    expect(onFollowUp).toHaveBeenCalledWith("2026-09-20");
  });

  it("commits a typed date on Enter, without waiting for the field to be left", () => {
    const onFollowUp = vi.fn();
    renderPane(detailFor(), onFollowUp);
    const input = screen.getByLabelText("Follow up on");

    typeDate(input, "2026-09-20");
    expect(onFollowUp).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onFollowUp).toHaveBeenCalledTimes(1);
    expect(onFollowUp).toHaveBeenCalledWith("2026-09-20");
    // And the commit is not repeated when the field is then left: one intention, one write.
    fireEvent.blur(input);
    expect(onFollowUp).toHaveBeenCalledTimes(1);
  });

  it("writes nothing when the value settles back on the date already stored", () => {
    const onFollowUp = vi.fn();
    renderPane(detailFor({ follow_up: "2026-09-20" }), onFollowUp);
    const input = screen.getByLabelText("Follow up on");

    typeDate(input, "2026-10-20");
    typeDate(input, "2026-09-20");
    fireEvent.blur(input);
    expect(onFollowUp).not.toHaveBeenCalled();
  });

  it("bounds the picker to the window the server accepts, in BOTH directions", () => {
    // The same bound as `server.FOLLOWUP_MAX_DAYS`, and two-sided for the same reason: a
    // mistyped year is as likely to land in the past as in the future, and a control that
    // offers a date the route refuses is a 400 the reader cannot have predicted.
    renderPane(detailFor(), vi.fn());
    const input = screen.getByLabelText("Follow up on");
    expect(input.getAttribute("min")).toBe(isoDaysFromToday(-366));
    expect(input.getAttribute("max")).toBe(isoDaysFromToday(366));
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
    const input = screen.getByLabelText("Follow up on");
    typeDate(input, "");
    expect(onFollowUp).not.toHaveBeenCalled();
    // And the field snaps back to the stored date once the edit is abandoned, so an emptied
    // input never leaves the pane claiming there is no follow-up when the store holds one.
    fireEvent.blur(input);
    expect(onFollowUp).not.toHaveBeenCalled();
    expect(screen.getByLabelText<HTMLInputElement>("Follow up on").value).toBe("2026-09-20");
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
    // A date RELATIVE to today, never a literal: the chip reads "follow-up due <d>" once d is
    // today or past, so a hardcoded future date silently becomes a different assertion the day
    // it arrives. That is what turned CI red at UTC midnight while local was still green.
    const future = isoDaysFromToday(7);
    vi.mocked(setFollowUp).mockResolvedValue({
      outcome: "follow_up_set",
      follow_up: future,
    });
    vi.mocked(clearFollowUp).mockResolvedValue({
      outcome: "follow_up_cleared",
      follow_up: null,
    });

    fireEvent.change(screen.getByLabelText("Follow up on"), {
      target: { value: future },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(vi.mocked(setFollowUp)).toHaveBeenCalledWith(row.posting_id, future);
    // Optimistic: the ROW shows it before any refetch, and the lead has NOT left the queue —
    // a follow-up is a note, not a disposition.
    const queue = screen.getByRole("grid", { name: "Queue" });
    expect(within(queue).getAllByText(`follow-up ${future}`).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.mocked(clearFollowUp)).toHaveBeenCalledWith(row.posting_id);
    // The exact chip text, not `/follow-up/`: the grid's own sort control is called "follow-up".
    expect(
      within(screen.getByRole("grid", { name: "Queue" })).queryByText(`follow-up ${future}`),
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

    const future = isoDaysFromToday(7);
    fireEvent.change(screen.getByLabelText("Follow up on"), {
      target: { value: future },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(
      within(screen.getByRole("grid", { name: "Queue" })).getAllByText(`follow-up ${future}`)
        .length,
    ).toBeGreaterThan(0);

    await act(async () => {
      fail(new Error("400 from /api/queue/1/followup"));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(
      within(screen.getByRole("grid", { name: "Queue" })).queryByText(`follow-up ${future}`),
    ).toBeNull();
    expect(screen.getByText("400 from /api/queue/1/followup")).toBeTruthy();
  });

  it("reconciles the row against the date the STORE echoes, not the one it sent", async () => {
    // The optimistic value and the echo are the same string only while the route's parser stays
    // strict, and `FollowUpResponse.follow_up` promises the reconciliation
    // (`ux-interaction/states/ux-state-optimistic`: reconcile with the server response). A write
    // that never reads the echo leaves the page showing a date the store does not hold.
    const row = await openLead();
    const sent = isoDaysFromToday(5);
    const stored = isoDaysFromToday(6);
    vi.mocked(setFollowUp).mockResolvedValue({ outcome: "follow_up_set", follow_up: stored });

    pickDate(screen.getByLabelText("Follow up on"), sent);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(vi.mocked(setFollowUp)).toHaveBeenCalledWith(row.posting_id, sent);
    const queue = within(screen.getByRole("grid", { name: "Queue" }));
    expect(queue.getAllByText(`follow-up ${stored}`).length).toBeGreaterThan(0);
    expect(queue.queryByText(`follow-up ${sent}`)).toBeNull();
    // The toast names the stored date too: a confirmation that reads back the value the store
    // refused would be the same lie in words.
    expect(screen.getByText(`Follow up on Globex — Backend Engineer on ${stored}`)).toBeTruthy();
  });

  it("keeps the optimistic date when the server omits the echo entirely", async () => {
    // The `== null` half of the reconciliation. This viewer serves the bundle from disk and
    // answers from the Python it imported at start-up, so the key can be absent — and a read
    // written without the guard would blank the chip the write just drew.
    await openLead();
    const sent = isoDaysFromToday(5);
    vi.mocked(setFollowUp).mockResolvedValue(
      withoutFields<FollowUpResponse>({ outcome: "follow_up_set", follow_up: sent }, [
        "follow_up",
      ]),
    );

    pickDate(screen.getByLabelText("Follow up on"), sent);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(
      within(screen.getByRole("grid", { name: "Queue" })).getAllByText(`follow-up ${sent}`).length,
    ).toBeGreaterThan(0);
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

  it("f while the lead's detail is still in flight still lands the cursor when it arrives", async () => {
    // `f` on the lead that is ALREADY selected used to look the input up and focus it on the
    // spot — but the pane's detail is fetched, so while it is in flight there is no input and
    // the keystroke was dropped with nothing recorded. The reader pressed a key and nothing
    // ever happened.
    const row = queueRow({ company: "Globex", title: "Backend Engineer" });
    vi.mocked(getQueue).mockResolvedValue(queueResponse([row]));
    vi.mocked(getAnswers).mockResolvedValue({
      identity: {},
      work_auth: {},
      education: [],
      questions: [],
    });
    let land: (detail: QueueDetail) => void = () => undefined;
    vi.mocked(getDetail).mockReturnValue(
      new Promise<QueueDetail>((resolve) => {
        land = resolve;
      }),
    );
    render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    const dataRow = rowElement();
    dataRow.focus();
    fireEvent.click(dataRow);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    // In flight: the pane is drawing its loading state and the input does not exist yet.
    expect(screen.queryByLabelText("Follow up on")).toBeNull();
    fireEvent.keyDown(dataRow, { key: "f" });

    await act(async () => {
      land({ row, jd_body: null, requirements: [], board_target: null });
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(document.activeElement).toBe(screen.getByLabelText("Follow up on"));
  });

  it("forgets the f cursor when the detail load fails and another lead is opened", async () => {
    // The ref is the record of one keystroke on one lead. Only the SUCCESS path used to clear
    // it, so a failed load left it armed: the reader who later opened that lead by hand had the
    // cursor pulled off the list into the date input by a keystroke they pressed minutes ago.
    const first = queueRow({ company: "Acme Corp", title: "FIRST-LEAD" });
    const second = queueRow({ company: "Globex", title: "SECOND-LEAD" });
    vi.mocked(getQueue).mockResolvedValue(queueResponse([first, second]));
    vi.mocked(getAnswers).mockResolvedValue({
      identity: {},
      work_auth: {},
      education: [],
      questions: [],
    });
    let refused = false;
    vi.mocked(getDetail).mockImplementation((postingId: number) => {
      if (postingId === first.posting_id && !refused) {
        refused = true;
        return Promise.reject(new Error("503 from the store"));
      }
      const row = postingId === first.posting_id ? first : second;
      return Promise.resolve({ row, jd_body: null, requirements: [], board_target: null });
    });
    render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    const rowFor = (title: string): HTMLElement => {
      const found = within(screen.getByRole("grid", { name: "Queue" }))
        .getAllByRole("row")
        .find((element) => element.textContent?.includes(title) === true);
      if (found === undefined) throw new Error(`no row for ${title}`);
      return found;
    };

    const firstRow = rowFor("FIRST-LEAD");
    firstRow.focus();
    fireEvent.keyDown(firstRow, { key: "f" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("503 from the store")).toBeTruthy();

    // A different lead, then back to the first one by CLICK. This time the detail arrives, and
    // the cursor has to stay on the list: nothing asked for the input.
    fireEvent.click(rowFor("SECOND-LEAD"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const again = rowFor("FIRST-LEAD");
    again.focus();
    fireEvent.click(again);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByLabelText("Follow up on")).toBeTruthy();
    expect(document.activeElement).toBe(again);
  });
});

describe("the follow-up due facet", () => {
  /*
   * The cell and the filter read DIFFERENT scopes, deliberately, and this is the app's
   * precedent rather than this feature's quirk: every band cell is counted over the APPLY lane
   * (`api.py::_counts` is handed `rows`, which is that lane; `QueuePage` recomputes it over
   * `filtered`, which is the same lane), while every row-predicate facet filters BOTH lanes —
   * the three `judge_*` cells and the two verdict cells included.
   *
   * So the two are asserted SEPARATELY below, each naming the lane it comes from. Asserting
   * them together — "the cell says 1 and clicking it shows 1 row" — is what would have to be
   * rewritten the day either scope changed, and it is not what either one promises.
   */
  const lanes = () => {
    const due = isoDaysFromToday(-1);
    const later = isoDaysFromToday(10);
    return {
      due,
      applyLane: [
        queueRow({ title: "APPLY-DUE", follow_up: due }),
        queueRow({ title: "APPLY-LATER", follow_up: later }),
        queueRow({ title: "APPLY-NONE", follow_up: null }),
      ],
      reviewLane: [
        queueRow({ title: "REVIEW-DUE", follow_up: due, review_reason: "non_us_location" }),
      ],
    };
  };

  it("counts the APPLY lane alone, so a due review lead is not in the number", async () => {
    const { applyLane, reviewLane } = lanes();
    vi.mocked(getQueue).mockResolvedValue(queueResponse(applyLane, reviewLane));
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });

    // One due row in the apply lane and one in the review lane; the cell reads the apply lane's
    // figure, exactly as `eligible` and the `judge_*` cells do.
    expect(screen.getByRole("button", { name: /^follow-up due 1 —/i })).toBeTruthy();
  });

  it("filters BOTH lanes to the leads that are due, which is more rows than the cell counts", async () => {
    const { applyLane, reviewLane } = lanes();
    vi.mocked(getQueue).mockResolvedValue(queueResponse(applyLane, reviewLane));
    render(<App />);
    await screen.findByRole("grid", { name: "Queue" });
    fireEvent.click(screen.getByRole("button", { name: "show" }));

    fireEvent.click(screen.getByRole("button", { name: /^follow-up due 1 —/i }));

    // The APPLY lane: the due one survives, the pinned-but-not-due and the unpinned do not.
    const queue = within(screen.getByRole("grid", { name: "Queue" }));
    expect(queue.queryByText("APPLY-DUE")).not.toBeNull();
    expect(queue.queryByText("APPLY-LATER")).toBeNull();
    expect(queue.queryByText("APPLY-NONE")).toBeNull();
    // The REVIEW lane is reached too — a due review lead is work for today just as much — so
    // two rows are showing against a cell that read 1.
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
