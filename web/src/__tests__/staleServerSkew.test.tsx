import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ReviewReason, Verdict } from "../api/types";
import { QueueRowItem } from "../components/QueueRowItem";
import { EM_DASH, formatAge, formatCount, formatFraction, formatScore } from "../lib/format";
import { availabilityMark, materialsMark, requirementsMark, reviewMark, rowNote } from "../lib/jobStatus";
import { sortRows } from "../lib/sort";
import type { SortState } from "../lib/sort";
import { absent, queueRow, withoutFields } from "../test/rows";

/*
 * The stale-server skew guard, which is `== null` and must stay `== null`.
 *
 * `boardwatch web` serves this bundle from DISK while answering from the Python it imported at
 * STARTUP, so a long-lived viewer can serve a bundle that reads a field its own API never learned
 * to send. The absent field arrives as `undefined`, NOT as `null` — `=== null` waves it straight
 * through, and the first property read off it throws during render. That is how one absent field
 * blanked the whole page (D-360).
 *
 * Every assertion below is written so that tightening a guard to `=== null` breaks it. `undefined`
 * is the ONLY input any of these tests supply, because `null` passes either way and would make the
 * whole file vacuous.
 *
 * Two guards are deliberately NOT asserted here. `formatTimestamp` and `isSafeHttpUrl` return the
 * same answer for `undefined` under either comparison — `new Date(undefined)` is an Invalid Date
 * and `new URL(undefined)` throws into their own `catch` — so an assertion on them would pass
 * against the tightened version and prove nothing.
 */

const ABSENT_REASON = absent<ReviewReason | null>();
const ABSENT_VERDICT = absent<Verdict | null>();
const ABSENT_NUMBER = absent<number | null>();
const PROVIDER_SORT: SortState = { key: "provider", direction: "asc" };

describe("a field an older server never sent", () => {
  it("gives a job with no review reason no status line instead of throwing", () => {
    const row = withoutFields(queueRow({ verdict: "eligible", judge_verdict: "eligible" }), [
      "review_reason",
    ]);
    // No line is the honest render: the server cannot say why the job was held, and a job with
    // nothing to flag is a job with nothing to say.
    expect(() => rowNote(row)).not.toThrow();
    expect(rowNote(row)).toBeNull();
    expect(ABSENT_REASON).toBeUndefined();
  });

  it("reads an absent verdict as not assessed — never as a pass", () => {
    // The reading nobody took, in words, and in the tone that claims nothing.
    expect(requirementsMark(ABSENT_VERDICT)).toEqual({
      label: "Requirements not assessed yet",
      tone: "quiet",
    });
    expect(reviewMark(ABSENT_VERDICT)).toEqual({ label: "No independent review yet", tone: "quiet" });
  });

  it("reads an absent status and an absent résumé flag as unknown and not-ready", () => {
    expect(availabilityMark(absent<"open" | null>()).tone).toBe("quiet");
    // Not "ready": a flag the server never sent must not promise a résumé that may not exist.
    expect(materialsMark(absent<boolean | null>()).tone).toBe("warn");
  });

  it("renders an em dash from every display helper", () => {
    expect(formatAge(ABSENT_NUMBER)).toBe(EM_DASH);
    expect(formatFraction(ABSENT_NUMBER)).toBe(EM_DASH);
    expect(formatScore(ABSENT_NUMBER)).toBe(EM_DASH);
    expect(formatCount(ABSENT_NUMBER)).toBe(EM_DASH);
  });

  it("still draws a whole queue row when four fields are missing at once", () => {
    // The shape a viewer older than these fields actually sends: the keys are not there at all,
    // so every read is `undefined`. This is the row that blanked the page.
    const row = withoutFields(queueRow({ title: "Backend Engineer" }), [
      "review_reason",
      "score",
      "coverage",
      "posted_days",
    ]);

    const { container } = render(
      <QueueRowItem
        row={row}
        selected={false}
        active={false}
        collapsing={false}
        onSelect={() => undefined}
      />,
    );

    expect(screen.getAllByTitle("Backend Engineer").length).toBeGreaterThan(0);
    // A posting date it could not be told is absent, never "today" or "0d ago".
    expect(container.textContent).not.toMatch(/today|0d ago/);
  });

  it("renders the application site and sorts safely when discovery provenance is absent", () => {
    // An older server can omit discovery provenance; the actual application URL still names the site.
    const stale = withoutFields(queueRow({ apply_url: "https://boards.greenhouse.io/example/1" }), ["provider"]);

    const { container } = render(
      <QueueRowItem
        row={stale}
        selected={false}
        active={false}
        collapsing={false}
        onSelect={() => undefined}
      />,
    );
    expect(container.textContent).toContain("greenhouse");
    expect(() =>
      sortRows([stale, queueRow({ provider: "workday" })], PROVIDER_SORT, () => 1),
    ).not.toThrow();
  });

  it("CONTROL: source alone cannot label a missing application link", () => {
    // No usable application URL means there is no destination to label, even with a source.
    render(
      <QueueRowItem
        row={queueRow({ provider: "greenhouse", apply_url: null })}
        selected={false}
        active={false}
        collapsing={false}
        onSelect={() => undefined}
      />,
    );
    expect(screen.queryByText("greenhouse")).toBeNull();
  });
});
