import { waitFor } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

/*
 * The fourth scope: the boundary in `main.tsx`, the only one that catches `App` itself — its
 * router, its header, its toaster. Nothing below it is worth preserving, so what it has to prove
 * is narrower and more absolute than the others: `#root` holds something a reader can act on
 * rather than the EMPTY body that an uncaught render throw leaves behind.
 *
 * `main.tsx` exports nothing and runs on import, so it is imported for real. Mocking `App` to
 * throw is the one mock here that is not real component code, and it is unavoidable: the point is
 * a failure in `App` ITSELF, above every other boundary, which no data can produce.
 */
vi.mock("../App", () => ({
  App: () => {
    throw new Error("App itself could not render");
  },
}));

let container: HTMLElement | null = null;

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  container = document.createElement("div");
  container.id = "root";
  document.body.appendChild(container);
  // `main.tsx` runs its work at import time, so it has to be re-evaluated rather than replayed.
  vi.resetModules();
});

afterEach(() => {
  container?.remove();
  container = null;
});

it("leaves a recovery card in #root when App itself throws", async () => {
  const root = container;
  if (root === null) throw new Error("the #root container was not created");

  await act(async () => {
    await import("../main");
  });

  await waitFor(() => {
    expect(root.textContent).toContain("boardwatch could not draw the page.");
  });
  // Not a blank page: the card names the action, which is the difference between a page you can
  // recover from and one that is simply gone.
  expect(root.textContent).toContain("Draw the page again");
});
