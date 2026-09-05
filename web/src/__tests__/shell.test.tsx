import { expect, it } from "vitest";

import FAVICON from "../../public/favicon.svg?raw";
import INDEX_HTML from "../../index.html?raw";

/*
 * The document shell. `index.html` is not part of the module graph these tests render, so both
 * files are read as text through Vite's `?raw` — which is also why neither can go red
 * behaviourally: each asserts a literal in a file, and the file is the only implementation there
 * is. These are regression guards, not demonstrations of a bug.
 */
it("declares the SVG favicon, so the tab is not a blank sheet of paper", () => {
  expect(INDEX_HTML).toContain('<link rel="icon" type="image/svg+xml" href="/favicon.svg" />');
});

it("draws the favicon in the application's own two colours", () => {
  // The wordmark's accent bar on the page's own ground; no text, which is unreadable at 16px.
  expect(FAVICON).toContain("#5ec8f0");
  expect(FAVICON).toContain("#08090c");
  expect(FAVICON).not.toContain("<text");
});
