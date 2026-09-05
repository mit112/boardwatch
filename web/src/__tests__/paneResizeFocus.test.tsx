import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Answers, QueueDetail } from "../api/types";
import { DetailPane } from "../components/DetailPane";
import { queueRow } from "../test/rows";

/*
 * Resizing ACROSS the pane's own breakpoint with a lead open. Below `lg` the pane is a
 * `fixed inset-0` modal sheet and `QueuePage` inerts the page behind it; at or above `lg` it is a
 * column beside the list. Shrinking past that line used to leave focus wherever it was — on
 * `<body>`, because at the wide tier the pane deliberately does not take it — with the whole page
 * behind an opaque sheet now inert. That is a keyboard reader with nothing focusable on screen.
 *
 * The shared setup stubs `matchMedia` as a constant `true` with no-op listeners, so the
 * transition cannot be driven through it; this file installs a controllable one and restores the
 * shared stub afterwards.
 */

/* Captured so the shared stub is restored after this file replaces it, bound so it is not the
   unbound method reference `@typescript-eslint/unbound-method` objects to. */
const SHARED_MATCH_MEDIA: typeof window.matchMedia = window.matchMedia.bind(window);

const ANSWERS: Answers = { identity: {}, work_auth: {}, education: [], questions: [] };

const DETAIL: QueueDetail = {
  row: queueRow(),
  jd_body: "About the team.",
  requirements: [],
  board_target: "greenhouse:example",
};

/** A `matchMedia` whose answer can be changed and whose change event actually fires. */
function installMatchMedia(initial: boolean): (next: boolean) => void {
  let matches = initial;
  const listeners = new Set<() => void>();
  window.matchMedia = vi.fn((media: string) => ({
    get matches() {
      return matches;
    },
    media,
    onchange: null,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  return (next: boolean) => {
    matches = next;
    act(() => {
      for (const listener of [...listeners]) listener();
    });
  };
}

afterEach(() => {
  window.matchMedia = SHARED_MATCH_MEDIA;
});

describe("the pane across a resize", () => {
  it("takes focus when the window shrinks and it becomes the modal sheet", () => {
    const setMatches = installMatchMedia(true);
    render(
      <DetailPane
        detail={DETAIL}
        loading={false}
        error={null}
        answers={ANSWERS}
        onClose={() => undefined}
        onApplied={() => undefined}
        onSkip={() => undefined}
        onReport={() => undefined}
        onToast={() => undefined}
      />,
    );
    const pane = screen.getByRole("complementary", { name: "Lead detail" });
    // Side by side: the list keeps the cursor, so the pane must NOT have stolen it.
    expect(document.activeElement).not.toBe(pane);

    setMatches(false);
    // It is now `fixed inset-0` over an inert page, so the reader has to be inside it.
    expect(document.activeElement).toBe(pane);
  });

  it("hands focus back to the opener when the window grows and it is a column again", () => {
    const setMatches = installMatchMedia(false);
    render(<button type="button">opener</button>);
    const opener = screen.getByRole("button", { name: "opener" });
    opener.focus();

    render(
      <DetailPane
        detail={DETAIL}
        loading={false}
        error={null}
        answers={ANSWERS}
        onClose={() => undefined}
        onApplied={() => undefined}
        onSkip={() => undefined}
        onReport={() => undefined}
        onToast={() => undefined}
      />,
    );
    const pane = screen.getByRole("complementary", { name: "Lead detail" });
    expect(document.activeElement).toBe(pane);

    // Growing across the line is not a close, but the sheet is gone — so the cursor goes back
    // where it came from rather than sitting on a column that no longer traps it.
    setMatches(true);
    expect(document.activeElement).toBe(opener);
  });
});
