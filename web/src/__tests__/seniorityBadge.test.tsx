import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QueueRowItem } from "../components/QueueRowItem";
import type { QueueRow } from "../api/types";
import { queueRow } from "../test/rows";

/*
 * `judge_seniority_above_band` on an APPLY row.
 *
 * D-504 records the final gate's body-seniority reading whether or not `gate.seniority_hold`
 * acts on it. With the hold ON the lead moves to the review lane and `ReviewReasonBadge`
 * already says so; with it OFF the reading is recorded and the lead stays in the apply lane —
 * and until this badge existed the server sent that reading and the page dropped it. A reading
 * that cannot be seen is a monitoring failure, which is the case these tests pin.
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
 * line, so a tier that drops the column keeps the fact. So ONE badge is TWO DOM nodes, and every
 * count here is against that baseline rather than against 1.
 */
const PER_ROW = 2;

function countSenior() {
  return screen.queryAllByText("body reads senior").length;
}

describe("the body-seniority badge", () => {
  it("shows the reading on an apply-lane row, where nothing else carries it", () => {
    row({ judge_seniority_above_band: true, review_reason: null });
    expect(countSenior()).toBe(PER_ROW);
  });

  /*
   * THE DISCRIMINATING CASE, and the one the guard exists for. A review row holds the SAME
   * reading twice — once as `review_reason`, once as this flag — so the naive render (a bare
   * `row.judge_seniority_above_band ? <Badge/> : null`) puts TWO chips on one row and this count
   * doubles. Verified to fail against exactly that mutant before being counted as done. It is
   * the failure `off target` is already suppressed on a `role_vetoed` row to avoid: one decision
   * shown twice reads as two independent findings.
   */
  it("does NOT repeat the reading on a review row that already states it", () => {
    row({
      judge_seniority_above_band: true,
      review_reason: "seniority_judged_above_band",
    });
    expect(countSenior()).toBe(PER_ROW);
  });

  it("still renders the review badge when the apply-lane flag is absent", () => {
    row({ review_reason: "seniority_judged_above_band" });
    expect(countSenior()).toBe(PER_ROW);
  });

  /*
   * An older server omits the field entirely (`boardwatch web` serves a DISK bundle against the
   * Python it imported at STARTUP, so the bundle can be newer than the API). `undefined` must
   * render nothing rather than throw — the same stale-server rule `ReviewReasonBadge` carries.
   */
  it("renders no badge, and does not throw, when the server omits the field", () => {
    row({ review_reason: null });
    expect(countSenior()).toBe(0);
  });

  it("renders no badge when the judge read the body as in-band", () => {
    row({ judge_seniority_above_band: false, review_reason: null });
    expect(countSenior()).toBe(0);
  });
});
