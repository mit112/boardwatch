import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { captureToken } from "./api/token";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "./index.css";

// FIRST, before the first render and before the first fetch: read the bearer token out of the URL
// fragment and erase it from the address bar.
captureToken();

const container = document.getElementById("root");
if (container === null) throw new Error("#root is missing from index.html");

/*
 * The floor, and the only one that catches `App` itself — its router, its toaster, its header.
 * Everything else is scoped below a boundary that keeps some of the page alive; this one has
 * nothing left to preserve, so its card renders bare against the background rather than inside
 * the app's own padded `<main>`. That is accepted: an unpadded card is a page you can read and
 * act on, which is the whole difference this makes.
 */
createRoot(container).render(
  <StrictMode>
    <ErrorBoundary
      title="boardwatch could not draw the page."
      hint="Draw it again first, and reload the tab if that does not take — the session token is kept in this browser, so a reload comes back authorised. If it still comes straight back, restart `boardwatch web` and open the new URL it prints: the page's JavaScript is served from disk while the data comes from the server's own copy, and only a restart brings the two back together."
      action="Draw the page again"
    >
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
