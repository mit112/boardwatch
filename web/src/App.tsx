import { FIXTURE_MODE } from "./api/client";
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
      className={`min-h-11 rounded px-3 text-sm transition-colors duration-[120ms] ease-snap ${
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
        onClick={() => {
          document.getElementById("view")?.focus();
        }}
        className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:top-2 focus-visible:left-2 focus-visible:z-50 focus-visible:inline-flex focus-visible:min-h-11 focus-visible:items-center focus-visible:rounded focus-visible:border focus-visible:border-fg-2 focus-visible:bg-surface-2 focus-visible:px-3 focus-visible:text-sm focus-visible:text-fg"
      >
        Skip to content
      </button>
      <header className="sticky top-0 z-30 border-b border-divider bg-bg/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[110rem] flex-wrap items-center gap-4 px-4 py-2">
          {/* A real `h1`, not a styled span: it is the only document-level heading either route
              has, and without it a screen reader's heading list starts at `h2` under nothing. */}
          <h1 className="text-sm tracking-wide text-fg">boardwatch</h1>
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
              className="ml-auto rounded border border-control px-2 py-1 text-[11px] tracking-wide text-fg-2 uppercase"
              title="Serving from src/fixtures/. Add ?live=1 to talk to the API instead."
            >
              fixture data
            </span>
          ) : null}
        </div>
      </header>

      <main id="view" tabIndex={-1} className="mx-auto max-w-[110rem] px-4 py-4">
        {route === "queue" ? <QueuePage push={push} /> : <RunsPage />}
      </main>

      <Toaster toasts={toasts} onDismiss={dismiss} onHold={hold} onRelease={release} />
    </div>
  );
}
