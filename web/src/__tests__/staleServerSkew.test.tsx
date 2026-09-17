import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ReviewReason, Verdict } from "../api/types";
import { QueueRowItem } from "../components/QueueRowItem";
import { ReviewReasonBadge } from "../components/ReviewReasonBadge";
import { VerdictChip } from "../components/VerdictChip";
import { EM_DASH, formatAge, formatCount, formatFraction, formatScore } from "../lib/format";
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
  it("renders no review badge instead of throwing", () => {
    const { container } = render(<ReviewReasonBadge reason={ABSENT_REASON} />);
    // No badge is the honest render: the server cannot say why the lead was held.
    expect(container.textContent).toBe("");
  });

  it("renders the no-verdict chip instead of throwing", () => {
    render(<VerdictChip verdict={ABSENT_VERDICT} />);
    expect(screen.getByText("no verdict")).toBeTruthy();
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

    render(
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

    expect(screen.getAllByTitle("Backend Engineer").length).toBeGreaterThan(0);
    // The numbers it could not be told read as absent, never as zero.
    expect(screen.getAllByText(EM_DASH).length).toBeGreaterThan(0);
  });

  it("renders no ATS label, and still sorts by provider, when the key is absent", () => {
    // A row from a server that predates `provider`: the key is not there at all, so the read is
    // `undefined`. Rendering must produce nothing rather than an empty chip, and `sortRows` must
    // not reach `localeCompare` on it — a guard written `=== null` does both wrong.
    const stale = withoutFields(queueRow({ provider: "greenhouse" }), ["provider"]);

    const { container } = render(
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
    expect(container.textContent).not.toContain("greenhouse");
    expect(() =>
      sortRows([stale, queueRow({ provider: "workday" })], PROVIDER_SORT, () => 1),
    ).not.toThrow();
  });

  it("CONTROL: the same row WITH a provider does render the ATS label", () => {
    // Without this, the assertion above is green for a component that renders no label at all.
    render(
      <QueueRowItem
        row={queueRow({ provider: "greenhouse" })}
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
    expect(screen.getByText("greenhouse")).toBeTruthy();
  });
});
