import { useState } from "react";

import { Icon } from "./components/Icon";
import { effectiveTheme, setTheme } from "./lib/theme";

import { FIXTURE_MODE } from "./api/client";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { StaleViewerBanner } from "./components/StaleViewerBanner";
import { Toaster } from "./components/Toaster";
import { useHashRoute } from "./hooks/useHashRoute";
import { useToasts } from "./hooks/useToasts";
import { AppliedPage } from "./routes/AppliedPage";
import { QueuePage } from "./routes/QueuePage";
import { RejectedPage } from "./routes/RejectedPage";
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
      className={`min-h-11 rounded-sm px-3.5 text-sm transition-colors duration-[120ms] ease-snap ${
        active
          ? "bg-surface-2 font-semibold text-fg shadow-[inset_0_-2px_0_0_var(--color-primary)]"
          : "font-medium text-fg-2 hover:bg-surface-2 hover:text-fg"
      }`}
    >
      {label}
    </button>
  );
}

/*
 * The theme switch: one button, pressed when the dark theme is in force. It sets an explicit
 * choice (and remembers it in this browser); until it is pressed the system preference decides.
 * The icon shows the theme you would switch TO, and the name says what it does, so neither carries
 * the state alone.
 */
function ThemeToggle() {
  const [dark, setDark] = useState(() => effectiveTheme() === "dark");
  return (
    <button
      type="button"
      aria-pressed={dark}
      aria-label="Dark theme"
      title={dark ? "Switch to the light theme" : "Switch to the dark theme"}
      onClick={() => {
        const next = dark ? "light" : "dark";
        setTheme(next);
        setDark(next === "dark");
      }}
      className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-sm text-fg-2 transition-colors duration-150 ease-in-out hover:bg-surface-2 hover:text-fg"
    >
      <Icon name={dark ? "sun" : "moon"} size={18} />
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
      <header inert={sheet} className="z-30 border-b border-divider bg-bg roomy:sticky roomy:top-0">
        <div className="mx-auto flex max-w-[160rem] flex-wrap items-center gap-6 px-6 py-3">
          {/* A real `h1`, not a styled span: it is the only document-level heading either route
              has, and without it a screen reader's heading list starts at `h2` under nothing.
              Set as a wordmark in the display voice. The accent rule beside it is the only place
              the accent appears outside a focus ring; it is `aria-hidden` and carries no meaning,
              because the word does. */}
          <h1 className="flex items-center gap-2 text-base font-semibold text-fg">
            <span aria-hidden="true" className="size-2.5 rounded-full bg-primary" />
            boardwatch
          </h1>
          <nav aria-label="Views" className="flex items-center gap-1">
            <NavTab
              label="Jobs"
              active={route === "queue"}
              onClick={() => {
                setRoute("queue");
              }}
            />
            {/* In the order of the work: what to apply to, what has been sent, what the rules turned
                away. The pipeline's own diagnostics are last and are not what this app is for. */}
            <NavTab
              label="Applied"
              active={route === "applied"}
              onClick={() => {
                setRoute("applied");
              }}
            />
            {/* Not "Rejected": that word belongs to an employer's answer to an application, and
                this list is what OUR rules turned away, read to catch a wrong call. */}
            <NavTab
              label="Filtered out"
              active={route === "rejected"}
              onClick={() => {
                setRoute("rejected");
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
          <span className="ml-auto flex items-center gap-2">
            {import.meta.env.DEV && FIXTURE_MODE ? (
              <span
                className="rounded-sm bg-surface-2 px-2 py-1 text-xs text-fg-2"
                title="Serving from src/fixtures/. Add ?live=1 to talk to the API instead."
              >
                fixture data
              </span>
            ) : null}
            <ThemeToggle />
          </span>
        </div>
      </header>

      {/* Under the header and inert with it while the sheet is up: it is page-level advice, and
          covered by the sheet like everything else the reader cannot reach there. */}
      <div inert={sheet}>
        <StaleViewerBanner />
      </div>

      {/*
        * 160rem, not the 110rem this used to be. 110rem is 1760px, so on the 27-inch display this
        * is worked on (2560 CSS px) it left 400px of dead margin each side AND — because the
        * detail pane takes up to 32rem of what is left — put the queue's list container at 1184px,
        * under the 78rem at which `QueueRowItem` switches to its eight-column tier. The widest
        * layout was therefore unreachable whenever a lead was open, at every width. The cap is on
        * the GRID's page, so it is raised here and the readable measure is held where the prose
        * actually is: the JD box in the detail pane and the queue's empty state.
        */}
      <main id="view" tabIndex={-1} className="mx-auto max-w-[160rem] px-4 py-6 sm:px-6 sm:py-8">
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
          {route === "queue" ? (
            <QueuePage push={push} onSheet={setSheet} />
          ) : route === "applied" ? (
            <AppliedPage push={push} />
          ) : route === "rejected" ? (
            <RejectedPage push={push} />
          ) : (
            <RunsPage />
          )}
        </ErrorBoundary>
      </main>

      <Toaster toasts={toasts} onDismiss={dismiss} onHold={hold} onRelease={release} />
    </div>
  );
}
