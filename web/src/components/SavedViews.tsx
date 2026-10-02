import { useId, useState } from "react";

/*
 * Named filter sets: the queue's toolbar, band facet and sort, saved under a name and put back in
 * one choice.
 *
 * `localStorage`, unlike the session-scoped filters themselves: a saved view is a choice the reader
 * made to keep, not "what am I doing right now". It lives in THIS browser only and is keyed by the
 * page's origin, which includes the port — so a viewer restarted on a different port starts with
 * none. Every access is wrapped, because storage throws outright when disabled, and a page that
 * cannot remember a view must still be a page that works.
 */

const STORAGE_KEY = "boardwatch.queue.views";

/** One saved view. Values are kept as the page's own session encodings, so restoring one goes
 *  through the same decoders a reload does and an out-of-catalog value is dropped there. */
export type QueueView = Record<string, string>;

interface Saved {
  name: string;
  view: QueueView;
}

function readSaved(): Saved[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is Saved =>
        typeof entry === "object" &&
        entry !== null &&
        typeof (entry as Saved).name === "string" &&
        typeof (entry as Saved).view === "object" &&
        (entry as Saved).view !== null &&
        // Every value a string, as this module writes them: storage is editable by anything on
        // the origin, and a number restored into the filter box would throw on its first `.trim()`.
        Object.values((entry as Saved).view).every((value) => typeof value === "string"),
    );
  } catch {
    return [];
  }
}

function writeSaved(saved: Saved[]): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
    return true;
  } catch {
    return false;
  }
}

const CONTROL =
  "min-h-11 rounded-sm border border-control px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:border-fg-2 hover:text-fg";

export function SavedViews({
  current,
  onApply,
  onError,
}: {
  current: QueueView;
  onApply: (view: QueueView) => void;
  onError: (message: string) => void;
}) {
  const [saved, setSaved] = useState<Saved[]>(readSaved);
  const [chosen, setChosen] = useState("");
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const selectId = useId();
  const nameId = useId();
  const hintId = useId();

  const store = (next: Saved[]) => {
    if (!writeSaved(next)) {
      onError("This browser would not store the view — storage is disabled or full.");
      return false;
    }
    setSaved(next);
    return true;
  };

  const save = () => {
    const trimmed = name.trim();
    if (trimmed === "") {
      setHint("Name the view first.");
      return;
    }
    // Saving under an existing name replaces it: the name is how the reader finds it again.
    const next = [...saved.filter((entry) => entry.name !== trimmed), { name: trimmed, view: current }];
    if (!store(next)) return;
    setChosen(trimmed);
    setNaming(false);
    setName("");
    setHint(null);
  };

  return (
    <div className="flex flex-wrap items-end gap-2">
      {saved.length === 0 ? null : (
        <label htmlFor={selectId} className="flex w-56 flex-col gap-1.5">
          <span className="label-micro text-fg-3">Saved view</span>
          <select
            id={selectId}
            value={chosen}
            onChange={(event) => {
              const pick = saved.find((entry) => entry.name === event.target.value);
              setChosen(event.target.value);
              if (pick !== undefined) onApply(pick.view);
            }}
            className="min-h-11 rounded-sm border border-control bg-surface px-3 text-sm text-fg transition-colors duration-150 ease-in-out hover:border-fg-2 focus:border-fg-2"
          >
            <option value="">choose a view…</option>
            {saved.map((entry) => (
              <option key={entry.name} value={entry.name}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {chosen === "" ? null : (
        <button
          type="button"
          aria-label={`Delete the saved view ${chosen}`}
          onClick={() => {
            if (store(saved.filter((entry) => entry.name !== chosen))) setChosen("");
          }}
          className={CONTROL}
        >
          Delete view
        </button>
      )}
      {naming ? (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <label htmlFor={nameId} className="flex w-56 flex-col gap-1.5">
            <span className="label-micro text-fg-3">View name</span>
            <input
              id={nameId}
              value={name}
              maxLength={60}
              // Focus moves into the box the reader just asked for — never on page load.
              autoFocus
              {...(hint === null ? {} : { "aria-describedby": hintId, "aria-invalid": true })}
              onChange={(event) => {
                setName(event.target.value);
                if (hint !== null) setHint(null);
              }}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.stopPropagation();
                  setNaming(false);
                  setHint(null);
                }
              }}
              placeholder="e.g. remote, gate eligible"
              className="min-h-11 rounded-sm border border-control bg-surface px-3 text-sm text-fg placeholder:text-fg-3"
            />
          </label>
          <button type="submit" className={CONTROL}>
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setNaming(false);
              setHint(null);
            }}
            className={CONTROL}
          >
            Cancel
          </button>
          {hint === null ? null : (
            <p id={hintId} className="w-full text-sm text-fg">
              {hint}
            </p>
          )}
        </form>
      ) : (
        <button
          type="button"
          onClick={() => {
            setNaming(true);
          }}
          title="Keep the current filters, facet and sort under a name, in this browser."
          className={CONTROL}
        >
          Save view
        </button>
      )}
    </div>
  );
}
