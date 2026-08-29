import { useState } from "react";

import { FIXTURE_MODE } from "./api/client";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Toaster } from "./components/Toaster";
import { useHashRoute } from "./hooks/useHashRoute";
import { useToasts } from "./hooks/useToasts";
import { QueuePage } from "./routes/QueuePage";
import { RunsPage } from "./routes/RunsPage";

function NavTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`min-h-11 rounded-sm px-3.5 font-display text-xs tracking-[0.08em] uppercase transition-colors duration-[120ms] ease-snap ${
        active
          ? "bg-surface-2 text-fg shadow-[inset_0_-2px_0_0_var(--color-accent)]"
          : "text-fg-2 hover:bg-surface hover:text-fg"
      }`}
    >
      {label}
    </button>
  );
}

export function App() {
  const [route, setRoute] = useHashRoute();
  const { toasts, push, dismiss, hold, release } = useToasts();
  /*
   * True only while the queue's detail pane is the full-screen SHEET it becomes below `lg`. The
   * sheet covers the header and the skip link, so both are inert for as long as it is up — a skip
   * link that moves focus behind an opaque modal is worse than none. The toaster is deliberately
   * not inerted: it draws above the sheet and holds the only undo a mark-applied has. `QueuePage`
   * reports the state, because the breakpoint belongs to the pane rather than here.
   */
  const [sheet, setSheet] = useState(false);

  return (
    <div className="min-h-screen bg-bg">
      {/*
        * SC 2.4.1 Bypass Blocks. Visible on focus, never otherwise.
        *
        * A BUTTON, not the usual `<a href="#view">`, and the reason is this application's URL
        * fragment: it is both the router AND the channel the CLI hands the bearer token over
        * (`api/token.ts`), where any fragment that does not begin with `/` is READ AS A TOKEN. A
        * skip link would leave `#view` in the address bar, and the next reload would send
        * `Authorization: Bearer view`. Moving focus without touching the fragment avoids that
        * outright, and it also stops the link resetting the route from Runs back to Queue.
        */}
      <button
        type="button"
        inert={sheet}
        onClick={() => {
          document.getElementById("view")?.focus();
        }}
        className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:top-2 focus-visible:left-2 focus-visible:z-50 focus-visible:inline-flex focus-visible:min-h-11 focus-visible:items-center focus-visible:rounded-sm focus-visible:border focus-visible:border-fg-2 focus-visible:bg-surface-2 focus-visible:px-3 focus-visible:text-sm focus-visible:text-fg"
      >
        Skip to content
      </button>
      <header inert={sheet} className="sticky top-0 z-30 border-b border-divider bg-bg/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[110rem] flex-wrap items-center gap-6 px-6 py-3">
          {/* A real `h1`, not a styled span: it is the only document-level heading either route
              has, and without it a screen reader's heading list starts at `h2` under nothing.
              Set as a wordmark in the display voice. The accent rule beside it is the only place
              the accent appears outside a focus ring; it is `aria-hidden` and carries no meaning,
              because the word does. */}
          <h1 className="flex items-center gap-2.5 font-display text-[0.8125rem] tracking-[0.2em] text-fg uppercase">
            <span aria-hidden="true" className="h-3.5 w-0.5 rounded-full bg-accent" />
            boardwatch
          </h1>
          <nav aria-label="Views" className="flex items-center gap-1">
            <NavTab
              label="Queue"
              active={route === "queue"}
              onClick={() => {
                setRoute("queue");
              }}
            />
            <NavTab
              label="Runs"
              active={route === "runs"}
              onClick={() => {
                setRoute("runs");
              }}
            />
          </nav>
          {/* Dev-only by construction: `FIXTURE_MODE` is always false in a production build, so
              the `import.meta.env.DEV` literal folds this badge — and its mention of the fixture
              directory — out of the shipped bundle rather than leaving it as unreachable text. */}
          {import.meta.env.DEV && FIXTURE_MODE ? (
            <span
              className="ml-auto rounded-sm border border-control px-2 py-1 label-micro text-fg-2"
              title="Serving from src/fixtures/. Add ?live=1 to talk to the API instead."
            >
              fixture data
            </span>
          ) : null}
        </div>
      </header>

      <main id="view" tabIndex={-1} className="mx-auto max-w-[110rem] px-6 py-10">
        {/*
          * Wraps the route SWITCH, not the header — so a view that fails to draw leaves the nav
          * above it working, and the reader's way out is the tab they already know. `resetKeys`
          * on the route is what makes that way out real: without it, taking the tab would carry
          * this card onto the other view, which is not broken.
          */}
        <ErrorBoundary
          title="This view could not be drawn."
          hint="The tabs above still work, so the other view is one click away. Drawing this one again is worth a try — it reloads from the server either way, and nothing in the queue was changed by the failure."
          action="Draw this view again"
          resetKeys={[route]}
        >
          {route === "queue" ? <QueuePage push={push} onSheet={setSheet} /> : <RunsPage />}
        </ErrorBoundary>
      </main>

      <Toaster toasts={toasts} onDismiss={dismiss} onHold={hold} onRelease={release} />
    </div>
  );
}
