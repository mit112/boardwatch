import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/*
 * jsdom implements no `matchMedia`, and `useMediaQuery` reads it on EVERY render — so without a
 * stub the queue page throws before any assertion can run.
 *
 * It answers `true`, which pins the tests at the `lg` tier: the detail pane is a column beside the
 * list and nothing on the page is `inert`. That is the tier where "the queue beside it is
 * unaffected" is a claim worth testing — below `lg` the pane is a full-screen sheet and the list
 * behind it is inert by design, so querying for a surviving row there would answer a different
 * question.
 */
function stubMediaQueryList(query: string): MediaQueryList {
  return {
    matches: true,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  };
}

window.matchMedia = stubMediaQueryList;

// `globals` is off, so React Testing Library cannot register this for itself.
afterEach(() => {
  cleanup();
});
