import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QueueRow } from "../api/types";
import { QueueRowItem } from "../components/QueueRowItem";
import { queueRow, withoutFields } from "../test/rows";

/*
 * `judge_verdict` on a queue row.
 *
 * The store has carried a final-gate verdict for the apply lane since T42 and `classify` has read
 * it since D-489, but no payload emitted it — so a lead the gate read as `uncertain` rendered
 * identically to one it cleared, on a lane of 392. A signal that cannot be seen is a monitoring
 * failure, which is the case these tests pin.
 *
 * Every label is asserted WITH its `gate` prefix, because the prefix is the feature: an unprefixed
 * `uncertain` chip beside the rules engine's `uncertain` chip is two chips and no way to tell
 * which engine produced either, which is the same defect as not rendering it at all.
 */
function row(overrides: Partial<QueueRow> = {}) {
  return render(
    <QueueRowItem
      row={queueRow(overrides)}
      rank={1}
      selected={false}
      active
      collapsing={false}
      onSelect={() => undefined}
      onApplied={() => undefined}
      onSkip={() => undefined}
      onReport={() => undefined}
    />,
  );
}

/*
 * `QueueRowItem` renders `<Flags>` TWICE — once as a column and once in the title cell's meta
 * line, so a tier that drops the column keeps the fact. ONE badge is therefore TWO DOM nodes, and
 * every count here is against that baseline rather than against 1 (same as `seniorityBadge`).
 */
const PER_ROW = 2;

describe("the final gate's verdict on a row", () => {
  it("renders the gate's uncertain BESIDE the rules engine's eligible", () => {
    // The load-bearing shape and the reason the field exists: the rules engine cleared this lead
    // and the gate did not. 42 of 390 judged leads on the measured lane are exactly this.
    row({ verdict: "eligible", judge_verdict: "uncertain" });

    expect(screen.queryAllByText("gate uncertain")).toHaveLength(PER_ROW);
    // The rules verdict is untouched and still rendered once, by `VerdictChip` in its own cell.
    // An implementation that replaced the verdict chip instead of adding beside it fails here.
    expect(screen.queryAllByText("eligible")).toHaveLength(1);
    expect(screen.queryAllByText("gate eligible")).toHaveLength(0);
  });

  it("renders the gate's own eligible as its own chip", () => {
    row({ verdict: "eligible", judge_verdict: "eligible" });

    expect(screen.queryAllByText("gate eligible")).toHaveLength(PER_ROW);
  });

  /*
   * THE STALE-SERVER CASE, and the one the `== null` guard exists for. `boardwatch web` serves the
   * bundle from DISK against the Python it imported at STARTUP, so a viewer older than this field
   * omits the key entirely and it arrives as `undefined`, not `null`. `WORDS[undefined].label` is
   * the exact throw that blanked the whole page (D-360), so a `=== null` guard fails this test.
   */
  it("renders no chip, and does not throw, when the server omits the field", () => {
    const stale = withoutFields(queueRow({ title: "Backend Engineer" }), ["judge_verdict"]);

    render(
      <QueueRowItem
        row={stale}
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

    // The row still drew — the assertion that separates "no chip" from "no page".
    expect(screen.getAllByTitle("Backend Engineer").length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/^gate /)).toHaveLength(0);
  });

  /*
   * `null` is "the gate has not spoken", which says nothing about the lead. An "unjudged" chip
   * here would be a chip on every row of a queue no gate has reached — 392 chips carrying no
   * information — so the honest render is nothing.
   */
  it("renders no chip when the gate has not spoken", () => {
    row({ judge_verdict: null });

    expect(screen.queryAllByText(/^gate /)).toHaveLength(0);
    expect(screen.queryAllByText(/not judged/)).toHaveLength(0);
  });
});
