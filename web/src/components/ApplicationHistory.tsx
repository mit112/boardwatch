import { useCallback, useEffect, useId, useRef, useState } from "react";

import { addApplicationNote, getApplicationEvents } from "../api/client";
import type { ApplicationEvent } from "../api/types";
import { formatTimestampWithYear } from "../lib/format";

/*
 * One application's ledger, and the box that adds a note to it.
 *
 * The ledger is the store's `application_events`, which is append-only by trigger, so this panel
 * only ever reads it and appends to it. It is fetched when the panel opens rather than shipped on
 * every row of `/api/applied`: a reader opens a handful of these, and the page lists hundreds.
 */

/** Must match the server's `NOTE_MAX_CHARS`. The server enforces it; this only stops the reader
 *  typing past a limit they would otherwise learn about from an error toast. */
const NOTE_MAX_CHARS = 2000;

/** What one event says, in words. A type this bundle does not know reads as itself. */
function describe(event: ApplicationEvent): string {
  switch (event.event_type) {
    case "created":
      return `recorded as ${event.to_status ?? "unknown"}`;
    case "status_change":
      return `${event.from_status ?? "unknown"} → ${event.to_status ?? "unknown"}`;
    case "note":
      return "note";
    default:
      return event.event_type;
  }
}

export function ApplicationHistory({
  applicationId,
  revision,
  named,
  onNoted,
  onError,
}: {
  applicationId: number;
  /** Changes whenever the row's ledger has grown — the page passes `last_activity_at` — so a
   *  status moved while the panel is open shows up in it without reopening. */
  revision: string | null;
  /** "Company — Title", for the accessible names of the list and the note box. */
  named: string;
  /** Called after a note lands, so the page can refetch the row's activity and the band. */
  onNoted: () => void;
  onError: (message: string) => void;
}) {
  const [events, setEvents] = useState<ApplicationEvent[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  /* Said beside the box, not implied by a disabled button: an inert control with no reason reads
     as a broken one, and a keyboard reader is never told it exists. */
  const [hint, setHint] = useState<string | null>(null);
  const noteId = useId();
  const hintId = useId();
  /* Only the newest read may land: an older one answering late would put back a shorter ledger
     over the one a status change just grew. */
  const latest = useRef(0);

  const load = useCallback(() => {
    const ticket = ++latest.current;
    return getApplicationEvents(applicationId)
      .then((response) => {
        if (ticket !== latest.current) return;
        setEvents(response.events);
        setFailed(null);
      })
      .catch((caught: unknown) => {
        if (ticket !== latest.current) return;
        setFailed(caught instanceof Error ? caught.message : "Could not load the history.");
      });
  }, [applicationId]);

  useEffect(() => {
    void load();
  }, [load, revision]);

  const save = () => {
    const note = draft.trim();
    if (saving) return;
    if (note === "") {
      setHint("Write the note first — an empty one is not saved.");
      return;
    }
    setHint(null);
    setSaving(true);
    void addApplicationNote(applicationId, note)
      .then(() => {
        // Cleared only once the store holds it, and only if the box still says what was sent: the
        // box stays editable during the save, and text added meanwhile was never written.
        setDraft((current) => (current.trim() === note ? "" : current));
        onNoted();
        return load();
      })
      .catch((caught: unknown) => {
        onError(caught instanceof Error ? caught.message : "Could not save that note.");
      })
      .finally(() => {
        setSaving(false);
      });
  };

  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      {failed !== null ? (
        <p role="alert" className="text-sm text-fg">
          {failed}
        </p>
      ) : events === null ? (
        <p role="status" className="text-sm text-fg-2">
          Loading the history…
        </p>
      ) : (
        <ol aria-label={`History of ${named}`} className="flex flex-col gap-1.5">
          {events.map((event) => (
            <li key={event.id} className="flex flex-wrap items-baseline gap-x-3 text-sm">
              <span className="text-fg-3 tabular-nums">
                {formatTimestampWithYear(event.occurred_at)}
              </span>
              <span className="text-fg-2">{describe(event)}</span>
              {event.note == null ? null : (
                <span className="whitespace-pre-wrap text-fg">{event.note}</span>
              )}
              <span className="label-micro text-fg-3">{event.source}</span>
            </li>
          ))}
        </ol>
      )}
      <form
        className="flex max-w-2xl flex-col gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        {/* The row's name is in the label, hidden visually: several panels can be open at once, and
            "Add a note" alone would not say which application a box belongs to. */}
        <label htmlFor={noteId} className="label-micro text-fg-3">
          Add a note <span className="sr-only">to {named}</span>
        </label>
        <textarea
          id={noteId}
          value={draft}
          maxLength={NOTE_MAX_CHARS}
          rows={2}
          {...(hint === null ? {} : { "aria-describedby": hintId, "aria-invalid": true })}
          placeholder="e.g. recruiter screen booked for Tuesday"
          onChange={(event) => {
            setDraft(event.target.value);
            if (hint !== null) setHint(null);
          }}
          onKeyDown={(event) => {
            // Cmd/Ctrl+Enter saves; a plain Enter is a new line, which a note may want.
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              save();
            }
          }}
          className="min-h-11 rounded-sm border border-control bg-surface px-3 py-2 text-sm text-fg placeholder:text-fg-3"
        />
        {hint === null ? null : (
          <p id={hintId} className="text-sm text-fg">
            {hint}
          </p>
        )}
        <span>
          <button
            type="submit"
            disabled={saving}
            aria-busy={saving}
            className="inline-flex min-h-11 items-center rounded-sm border border-control px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:border-fg-2 hover:text-fg disabled:text-fg-3"
          >
            Save note
          </button>
        </span>
      </form>
    </div>
  );
}
