import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QueueRow } from "../api/types";
import { QueueRowItem } from "../components/QueueRowItem";
import { queueRow } from "../test/rows";

/*
 * `judge_seniority_above_band` on an APPLY row.
 *
 * D-504 records the final gate's body-seniority reading whether or not `gate.seniority_hold`
 * acts on it. With the hold ON the job moves to the review list and its reason already says so;
 * with it OFF the reading is recorded and the job stays in Jobs to explore — and until this line
 * existed the server sent that reading and the page dropped it. A reading that cannot be seen is a
 * monitoring failure, which is the case these tests pin.
 */
function row(overrides: Partial<QueueRow> = {}) {
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

const SENIOR = "Description reads senior";

function countSenior() {
  return screen.queryAllByText(SENIOR).length;
}

describe("the body-seniority reading", () => {
  it("shows on an apply-list row, where nothing else carries it", () => {
    row({ judge_seniority_above_band: true, review_reason: null });
    expect(countSenior()).toBe(1);
  });

  /*
   * THE DISCRIMINATING CASE, and the one the guard exists for. A review row holds the SAME
   * reading twice — once as `review_reason`, once as this flag — so a naive render (the reason's
   * line AND a line for the flag) puts it on the row twice. One decision shown twice reads as two
   * independent findings, which is why `off target` is already suppressed on a `role_vetoed` row.
   */
  it("does NOT repeat the reading on a review row that already states it", () => {
    row({
      judge_seniority_above_band: true,
      review_reason: "seniority_judged_above_band",
    });
    expect(countSenior()).toBe(1);
  });

  it("still shows the review reason when the apply-list flag is absent", () => {
    row({ review_reason: "seniority_judged_above_band" });
    expect(countSenior()).toBe(1);
  });

  /*
   * An older server omits the field entirely (`boardwatch web` serves a DISK bundle against the
   * Python it imported at STARTUP, so the bundle can be newer than the API). `undefined` must
   * render nothing rather than throw.
   */
  it("shows nothing, and does not throw, when the server omits the field", () => {
    row({ review_reason: null });
    expect(countSenior()).toBe(0);
  });

  it("shows nothing when the judge read the body as in-band", () => {
    row({ judge_seniority_above_band: false, review_reason: null });
    expect(countSenior()).toBe(0);
  });
});
