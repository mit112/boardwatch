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
  const { toasts, push, dismiss } = useToasts();

  return (
    <div className="min-h-screen bg-bg">
      <header className="sticky top-0 z-30 border-b border-divider bg-bg/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[110rem] flex-wrap items-center gap-4 px-4 py-2">
          <span className="text-sm tracking-wide text-fg">boardwatch</span>
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

      <main className="mx-auto max-w-[110rem] px-4 py-4">
        {route === "queue" ? <QueuePage push={push} /> : <RunsPage />}
      </main>

      <Toaster toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}
