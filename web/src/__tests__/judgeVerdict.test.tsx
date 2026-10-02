import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QueueRow } from "../api/types";
import { QueueRowItem } from "../components/QueueRowItem";
import { queueRow, withoutFields } from "../test/rows";

/*
 * `judge_verdict` on a queue row.
 *
 * The store has carried a final-gate verdict for the apply lane since T42 and `classify` has read
 * it since D-489, but no payload emitted it — so a job the gate read as `uncertain` rendered
 * identically to one it cleared, on a lane of 392. A signal that cannot be seen is a monitoring
 * failure, which is the case these tests pin.
 *
 * The words are the point: the page says "independent review", never a bare "uncertain" beside the
 * rules' own "uncertain", which would be two readings and no way to tell which engine produced
 * either. And a reading nobody took is never printed as a clear one.
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

describe("the independent review's reading on a row", () => {
  it("shows the review's doubt BESIDE the rules' clear, naming both", () => {
    // The load-bearing shape and the reason the field exists: the rules engine cleared this job
    // and the review did not. 42 of 390 judged jobs on the measured lane are exactly this.
    row({ verdict: "eligible", judge_verdict: "uncertain" });
    screen.getByText("Rules found no blocker; independent review is unsure");
    // It did not replace the rules' reading with the review's, nor the reverse.
    expect(screen.queryByText("Independent review found no blocker")).toBeNull();
  });

  it("says nothing about the review when it agrees and nothing else is flagged", () => {
    row({ verdict: "eligible", judge_verdict: "eligible" });
    // Agreement is not news; the workspace still shows both readings.
    expect(screen.queryByText(/independent review/i)).toBeNull();
  });

  /*
   * THE STALE-SERVER CASE. `boardwatch web` serves the bundle from DISK against the Python it
   * imported at STARTUP, so a viewer older than this field omits the key entirely and it arrives
   * as `undefined`, not `null`. Reading it must not throw and must not invent a reading.
   */
  it("draws the row, and invents no reading, when the server omits the field", () => {
    const stale = withoutFields(queueRow({ title: "Backend Engineer" }), ["judge_verdict"]);

    render(
      <QueueRowItem
        row={stale}
        selected={false}
        active={false}
        collapsing={false}
        onSelect={() => undefined}
      />,
    );

    // The row still drew — the assertion that separates "no line" from "no page".
    expect(screen.getAllByTitle("Backend Engineer").length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/independent review/i)).toHaveLength(0);
  });

  /*
   * `null` is "the gate has not spoken", which says nothing about the job. An "unreviewed" mark on
   * every row of a queue no gate has reached would be hundreds of marks carrying no information.
   */
  it("shows no mark when the review has not spoken", () => {
    row({ judge_verdict: null });
    expect(screen.queryAllByText(/independent review/i)).toHaveLength(0);
    expect(screen.queryAllByText(/not judged|unreviewed/i)).toHaveLength(0);
  });
});
