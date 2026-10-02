import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  clearFollowUp,
  getAnswers,
  getApplied,
  getDetail,
  getQueue,
  markApplied,
  markSkipped,
  report,
  setFollowUp,
  skipMany,
  unapply,
  unreport,
  unskip,
  unskipMany,
} from "../api/client";
import type {
  Answers,
  AppliedHistoryResponse,
  FollowUpResponse,
  QueueCounts,
  QueueDetail,
  QueueResponse,
  QueueRow,
  ReviewReason,
} from "../api/types";
import { TOKEN_EVENT, readWatermark, writeWatermark } from "../api/token";
import { openApplyUrl } from "../components/ApplyLink";
import { ApplyReturnPrompt } from "../components/ApplyReturnPrompt";
import { DetailPane, FOLLOW_UP_INPUT_ID, PANE_ID, SIDE_BY_SIDE } from "../components/DetailPane";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { Icon } from "../components/Icon";
import { QueueTable } from "../components/QueueTable";
import type { Selection } from "../components/QueueTable";
import { LENSES, LensTabs, QueueSummary } from "../components/QueueSummary";
import type { Lens, RecordedState } from "../components/QueueSummary";
import { FILTER_INPUT_ID, QueueToolbar } from "../components/QueueToolbar";
import { RecordedPanel, SessionBar, SessionDone } from "../components/ApplySession";
import type { SessionEnd } from "../components/ApplySession";
import { SavedViews } from "../components/SavedViews";
import type { QueueView } from "../components/SavedViews";
import { QUEUE_FACETS, StatusBand } from "../components/StatusBand";
import type { QueueFacet } from "../components/StatusBand";
import { useHashRoute } from "../hooks/useHashRoute";
import { useMediaQuery } from "../hooks/useMediaQuery";
import type { ToastRequest } from "../hooks/useToasts";
import {
  REVIEW_REASON_LABELS,
  countReviewReasons,
  reviewLaneSentence,
} from "../lib/reviewReasons";
import { isFollowUpDue } from "../lib/format";
import { SUBMITTED_STATUSES, countRecorded } from "../lib/progress";
import { firstOfEachGroup, relatedPostings, similarGroups } from "../lib/similar";
import { matchesLocation, matchesQuery, parseSortState, sortRows } from "../lib/sort";
import type { SortState } from "../lib/sort";

const COLLAPSE_MS = 200;
const POLL_MS = 30_000;
/** How long the summary waits for the application history before it says it could not read it and
 *  offers a retry. The page never waits on it: jobs load and work with or without the count. */
const APPLIED_TIMEOUT_MS = 12_000;
/**
 * After a job is recorded, a further record is refused for this long. The write is irreversible
 * enough to be worth a guard that costs nothing to a deliberate click — nobody reads a job and
 * decides in half a second — and that a held key or a double click cannot get past: the workspace
 * has already moved to the NEXT job, so a repeat would otherwise record that one unseen.
 */
const RECORD_LOCK_MS = 600;

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new Error("timed out"));
    }, ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        window.clearTimeout(timer);
        reject(error instanceof Error ? error : new Error("failed"));
      },
    );
  });
}

type AppliedState =
  | { kind: "loading" }
  | { kind: "ready"; data: AppliedHistoryResponse }
  | { kind: "failed" };

/** An apply session: optional, with no goal until the person chooses a batch. `count` is
 *  applications CONFIRMED recorded this session — a failed write never moves it. */
interface Session {
  batch: number | null;
  count: number;
}

/*
 * Working state kept across a tab switch and a reload, in `sessionStorage` and never in
 * `localStorage`: this is what the reader is doing RIGHT NOW, so it should die with the tab rather
 * than greet them a week later with a filter they have forgotten setting.
 *
 * Every access is wrapped, exactly as `api/token.ts` wraps its own: storage throws outright when
 * it is disabled or the quota is gone, and a viewer that cannot remember a filter must still be a
 * viewer that runs.
 */
function readSession(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeSession(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    /* Remembering is a convenience; failing to remember is never a page failure. */
  }
}

/*
 * The cursor, put back on a lead's row after its pane closes — looked up by POSTING ID at the
 * moment it is needed, never remembered as an element.
 *
 * A remembered element is the bug this replaces. `DetailPane` captured `document.activeElement`
 * when it mounted and refocused it on unmount, which restores nothing unless the cursor was on the
 * trigger row at that instant: opening a lead assigns `window.location.hash`, a fragment navigation
 * resolving to no element, and a browser answers that by moving focus to the body. So the pane
 * captured `<body>` and dutifully put it back (D-348 measured exactly that, and ruled out `inert`
 * by stripping it and reproducing anyway). An id survives all of it, including a row element that
 * was re-rendered or moved lists while the pane was up.
 *
 * Deferred a tick because the row is not reachable until React has committed the close: below `lg`
 * the list behind the sheet is `inert`, and `.focus()` inside an inert subtree does nothing.
 * Falls back to the filter box when the lead is no longer listed — the row can be gone (marked
 * applied, filtered out), and `<body>` is where a keyboard reader gets stranded.
 */
function focusRow(postingId: number): void {
  window.setTimeout(() => {
    const row = document.querySelector<HTMLElement>(`[data-row-id="${String(postingId)}"]`);
    if (row === null) document.getElementById(FILTER_INPUT_ID)?.focus();
    else row.focus();
  }, 0);
}

/*
 * The queue's working state, restored on mount and written on every change. Taking the Runs tab
 * and coming back used to throw away the filter text, the score floor, both facets and both sort
 * orders — all of it re-entered by hand, every time.
 *
 * The decoders are the enforcement point for the closed catalogs. Storage outlives a bundle
 * upgrade, so a stored facet or sort key can name a member this build no longer has: it is
 * DISCARDED whole rather than passed through as a tenth bucket or repaired into something valid.
 */
const QUEUE_KEYS = {
  query: "boardwatch.queue.query",
  location: "boardwatch.queue.location",
  lens: "boardwatch.queue.lens",
  minScore: "boardwatch.queue.minScore",
  board: "boardwatch.queue.board",
  mode: "boardwatch.queue.mode",
  hideThin: "boardwatch.queue.hideThin",
  hideUnverifiable: "boardwatch.queue.hideUnverifiable",
  hideSimilar: "boardwatch.queue.hideSimilar",
  facet: "boardwatch.queue.facet",
  reason: "boardwatch.queue.reason",
  sort: "boardwatch.queue.sort",
} as const;

/** The `mode` select value for a row whose board states no remote policy. */
export const NO_MODE = "(not stated)";

const decodeText = (raw: string | null): string | null => raw;
const encodeText = (value: string): string => value;

/*
 * `review` is a LANE, and the page now has a control for lanes (the three lists above the table),
 * so it is no longer a facet that can be switched on here. A stored or saved `review` facet — from
 * before that — decodes to nothing; `applyView` turns it into the Needs review list instead.
 */
type RowFacet = Exclude<QueueFacet, "review">;

const decodeFacet = (raw: string | null): RowFacet | null =>
  raw !== "review" && (QUEUE_FACETS as readonly string[]).includes(raw ?? "")
    ? (raw as RowFacet)
    : null;

const LENS_KEYS = LENSES.map((entry) => entry.key) as readonly string[];
const decodeLens = (raw: string | null): Lens | null =>
  raw !== null && LENS_KEYS.includes(raw) ? (raw as Lens) : null;
const encodeLens = (value: Lens): string => value;
const encodeFacet = (value: RowFacet | null): string => value ?? "";

/**
 * What a facet is called in prose — the "Showing …" sentence and the empty-list hint. The wire
 * member is not the words: `judge_unjudged only` is a field name, and the reader clicked a cell
 * labelled `not judged`.
 */
const FACET_LABELS: Record<RowFacet, string> = {
  eligible: "rules found no blocker",
  uncertain: "some requirements not confirmed",
  judge_eligible: "independent review found no blocker",
  judge_uncertain: "independent review unsure",
  judge_unjudged: "not independently reviewed",
  follow_up_due: "follow-up due",
  new: "new since your last visit",
};

/** The frozen "new since last visit" set before the first response has arrived. A module constant
 *  so the identity is stable and no memo re-runs for a new empty set every render. */
const NOTHING_NEW: ReadonlySet<number> = new Set();

/**
 * Whether one row passes a ROW-LEVEL facet. `review` is excluded from the parameter because it is
 * a LANE rather than a row predicate — both call sites answer it before they ever reach here — so
 * this switch stays exhaustive over the closed catalog and a member added to `QUEUE_FACETS` is a
 * compile error rather than a silent `false` that empties the list.
 */
function matchesFacet(
  row: QueueRow,
  facet: RowFacet,
  newIds: ReadonlySet<number>,
): boolean {
  switch (facet) {
    case "eligible":
    case "uncertain":
      return row.verdict === facet;
    case "judge_eligible":
      return row.judge_verdict === "eligible";
    case "judge_uncertain":
      return row.judge_verdict === "uncertain";
    /* `== null`, never `=== null`: an older server omits `judge_verdict` entirely, and "the
       server cannot say" is the same statement as "the gate has not spoken". */
    case "judge_unjudged":
      return row.judge_verdict == null;
    /* `<=` today on the BROWSER's calendar, which is the server's own: the viewer only ever
       talks to loopback. `isFollowUpDue` guards `== null` for a server that omits the field. */
    case "follow_up_due":
      return isFollowUpDue(row.follow_up);
    /* Membership, never a re-derivation from `delivered_run_id`: the set is computed ONCE per
       load (see `adopt`) precisely so it cannot move under the reader, and comparing against a
       watermark here would re-answer the question on every render against a watermark that has
       already advanced. */
    case "new":
      return newIds.has(row.posting_id);
  }
}

const decodeReason = (raw: string | null): ReviewReason | null =>
  raw !== null && raw in REVIEW_REASON_LABELS ? (raw as ReviewReason) : null;
const encodeReason = (value: ReviewReason | null): string => value ?? "";

const encodeSort = (value: SortState): string => JSON.stringify(value);

/**
 * `useState` that reads its initial value from `sessionStorage` and writes every later one back.
 *
 * `decode` and `encode` must be module-level functions: an inline arrow would be a new identity on
 * every render and the setter would stop being stable, which is what the callers below rely on.
 */
function useSessionState<T>(
  key: string,
  fallback: T,
  decode: (raw: string | null) => T | null,
  encode: (value: T) => string,
): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => decode(readSession(key)) ?? fallback);
  const set = useCallback(
    (next: T) => {
      setValue(next);
      writeSession(key, encode(next));
    },
    [key, encode],
  );
  return [value, set];
}

type Removal = "applied" | "skipped" | "reported";

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

/*
 * One review reason, as a toggle. Pressed is a filled chip with the word "pressed" carried by
 * `aria-pressed` and by the fill — never colour alone (SC 1.4.1) — and the `aria-label` starts
 * with the visible label and count so Label in Name holds (SC 2.5.3) before it names the action
 * `aria-pressed` cannot convey.
 */
function ReasonChip({
  label,
  count,
  active,
  onToggle,
}: {
  label: string;
  count: number;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={`${label} ${count.toLocaleString()} — ${active ? "showing only these, activate to clear" : "show only these"}`}
      onClick={onToggle}
      className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-sm px-3 text-sm transition-colors duration-[120ms] ease-snap ${
        active
          ? "bg-primary font-medium text-on-primary"
          : "bg-surface text-fg-2 shadow-card hover:bg-surface-2 hover:text-fg"
      }`}
    >
      <span>{label}</span>
      <span className={`tabular-nums ${active ? "text-on-primary" : "text-fg-3"}`}>
        {count.toLocaleString()}
      </span>
    </button>
  );
}

export function QueuePage({
  push,
  onSheet,
}: {
  push: (request: ToastRequest) => void;
  onSheet: (open: boolean) => void;
}) {
  const [data, setData] = useState<QueueResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [removed, setRemoved] = useState<Map<number, Removal>>(new Map());
  const [collapsing, setCollapsing] = useState<Set<number>>(new Set());
  const [stashed, setStashed] = useState<QueueResponse | null>(null);
  const [newCount, setNewCount] = useState(0);
  /*
   * The bulk selection, by `posting_id` so it keys the same way `removed`, `collapsing` and the
   * roving stop do. PER PAGE and never persisted: `useSessionState` is for "what am I looking
   * for", and a selection is "what am I about to do" — restoring one after a reload would offer a
   * Skip over rows the reader last looked at yesterday. A route change unmounts this component,
   * which is what clears it.
   */
  const [marked, setMarked] = useState<ReadonlySet<number>>(() => new Set());

  /*
   * Which list the page is showing: the jobs to explore (the apply lane), the jobs that need a
   * review (the review lane), or both. A view of data the server already splits, not a new
   * classification — and a plain list switch, where the review lane used to be a section folded
   * shut under the apply table. The default is the apply lane while it has anything in it and the
   * review lane when it is empty (see `lens` below), so the page never opens on an empty list with
   * the work one click away.
   */
  const [lensPref, setLensPref] = useSessionState<Lens | null>(
    QUEUE_KEYS.lens,
    null,
    decodeLens,
    (value) => value ?? "",
  );

  const [query, setQuery] = useSessionState(QUEUE_KEYS.query, "", decodeText, encodeText);
  // A place, matched against every location a posting lists. "" is everywhere.
  const [location, setLocation] = useSessionState(QUEUE_KEYS.location, "", decodeText, encodeText);
  const [minScore, setMinScore] = useSessionState(
    QUEUE_KEYS.minScore,
    "",
    decodeText,
    encodeText,
  );
  // The job board (`provider`) to show; "" is every board.
  const [board, setBoard] = useSessionState(QUEUE_KEYS.board, "", decodeText, encodeText);
  // Work mode is the row's own `remote_policy`; "" is every mode and NO_MODE is "the board states none".
  const [mode, setMode] = useSessionState(QUEUE_KEYS.mode, "", decodeText, encodeText);
  const [hideThin, setHideThin] = useSessionState(QUEUE_KEYS.hideThin, "", decodeText, encodeText);
  const [hideUnverifiable, setHideUnverifiable] = useSessionState(
    QUEUE_KEYS.hideUnverifiable,
    "",
    decodeText,
    encodeText,
  );
  // Fold leads at one company under one title into the best-placed one (`lib/similar`).
  const [hideSimilar, setHideSimilar] = useSessionState(
    QUEUE_KEYS.hideSimilar,
    "",
    decodeText,
    encodeText,
  );
  /*
   * The verdict facet from the status band, shared across BOTH lanes exactly like `query` and
   * `minScore` — it expresses "what am I looking for", which spans the apply queue and the review
   * list. `null` is "all". Applied AFTER `filtered`/`filteredReview` below, never inside them, so
   * the band's own counts stay put and the reader can switch straight from one facet to another
   * instead of the cell they need to click dropping to zero.
   */
  const [facet, setFacet] = useSessionState<RowFacet | null>(
    QUEUE_KEYS.facet,
    null,
    decodeFacet,
    encodeFacet,
  );
  /*
   * The REVIEW-REASON facet, alongside the verdict one and composed with it. Every review row
   * already carried its reason as a chip and nothing could filter by one, so on a 149-lead lane
   * the chips were nine repeating labels to scan past rather than a control. Applied after
   * `filteredReview` for the same reason the verdict facet is: the chip counts must not collapse
   * to the current selection, or the chip the reader wants next reads zero.
   */
  const [reasonFacet, setReasonFacet] = useSessionState<ReviewReason | null>(
    QUEUE_KEYS.reason,
    null,
    decodeReason,
    encodeReason,
  );
  const [sort, setSort] = useSessionState<SortState>(
    QUEUE_KEYS.sort,
    { key: "rank", direction: "asc" },
    parseSortState,
    encodeSort,
  );
  /*
   * The open lead and the run filter live in the URL (`#/queue?run=5&lead=61310`), not in state:
   * they are the two things a reader points AT rather than does, so they have to be sendable,
   * bookmarkable and reloadable. `useHashRoute` is called here rather than passed down from `App`
   * because it subscribes to `hashchange` itself and the route above needs neither key.
   */
  const [, , routeParams, setRouteParams] = useHashRoute();
  const selected = routeParams.lead;
  const runFilter = routeParams.run;
  const openLead = useCallback(
    (postingId: number | null) => {
      setRouteParams({ lead: postingId });
    },
    [setRouteParams],
  );
  /*
   * The keyboard CURSOR, which is not the selection: ↓/↑ walk the list without opening a pane and
   * without fetching a detail per row, and Enter opens the one you stopped on. One cursor for both
   * tables, because a posting id is unique across them and arrow keys never leave the table that
   * has focus anyway.
   */
  const [activeId, setActiveId] = useState<number | null>(null);
  /*
   * Both are keyed by the posting they describe, and the render reads them through `shownDetail` /
   * `shownError` below. `selected` is now driven by the URL, so it can change without going
   * through a click handler — a back button, a pasted link — and clearing these in an effect keyed
   * on it would be a setState synchronised into an effect body, which is the cascading render the
   * lint rule rejects. Comparing the id costs nothing and cannot go stale.
   */
  const [detail, setDetail] = useState<QueueDetail | null>(null);
  const [detailError, setDetailError] = useState<{ id: number; message: string } | null>(null);
  const [answers, setAnswers] = useState<Answers | null>(null);

  /* Whether the `lead` in the URL is a posting this queue actually holds. `false` while the queue
     is still loading, when every id is unknown. */
  const leadKnown =
    data !== null &&
    selected !== null &&
    [...data.rows, ...data.review].some((row) => row.posting_id === selected);

  const lens: Lens =
    lensPref ?? (data !== null && data.rows.length === 0 && data.review.length > 0 ? "review" : "explore");

  const knownIds = useRef<Set<number>>(new Set());

  /*
   * "NEW SINCE LAST VISIT", as posting ids: computed ONCE per page load and then frozen for the
   * life of the tab.
   *
   * Frozen is the REQUIREMENT, not an optimisation. The reader works down a list of 20-30 leads;
   * a set recomputed against a watermark the load had already advanced would empty the moment
   * anything re-fetched, and a set recomputed against a stale watermark would silently grow while
   * the page sat open. So the only thing that moves it is a RELOAD — the `refresh` button
   * re-enters `adopt` and the latch below leaves the set exactly as it is.
   *
   * State, so the facet memos can depend on it honestly, plus a one-way LATCH that says whether
   * it has been computed. The latch is a ref because it is read and written inside `adopt`, never
   * during render, and it is what makes "once" a property of this code rather than of the order
   * the fetches happen to land in.
   */
  const [newIds, setNewIds] = useState<ReadonlySet<number>>(NOTHING_NEW);
  const newIdsComputed = useRef(false);

  const adopt = useCallback((response: QueueResponse) => {
    /*
     * `review` is normalised ONCE, here, and never again — eight places downstream read it, five
     * of them as a bare `data.review.length`, and guarding each would be five chances to miss one.
     *
     * It needs normalising because `review` is newer than this page's oldest possible server: a
     * viewer that imported its Python before the lane split sends no `review` key at all. The
     * type says that cannot happen; `boardwatch web` says otherwise, serving this bundle from DISK
     * against the API it imported at STARTUP (D-360). Spreading `undefined` throws `not iterable`,
     * and that throw is inside a promise, so NO error boundary sees it — it lands in the `.catch`
     * below and paints a load-failure card that blames the transport and tells the reader to
     * re-open a URL, neither of which is true or would help.
     */
    const normalised: QueueResponse = { ...response, review: response.review ?? [] };
    setData(normalised);
    // BOTH lanes. A lead that moves between them on a re-evaluation is not new, and counting it
    // as new would put a permanent "N new" nag on the page that refreshing never clears.
    knownIds.current = new Set(
      [...normalised.rows, ...normalised.review].map((row) => row.posting_id),
    );
    if (!newIdsComputed.current) {
      newIdsComputed.current = true;
      // BOTH lanes, exactly as `knownIds` above and as every row-level facet: a lead delivered
      // last night that landed in `review` is new work too, and a watermark taken from the apply
      // lane alone would stop advancing the night every new lead was held.
      const everyRow = [...normalised.rows, ...normalised.review];
      const runs = everyRow
        .map((row) => row.delivered_run_id)
        .filter((id): id is number => id != null);
      const watermark = readWatermark();
      // `null` — a first visit — marks NOTHING new. Marking all 392 would be a page that opens
      // shouting on the one load where the reader has no way to know it is wrong.
      setNewIds(
        new Set(
          watermark === null
            ? []
            : everyRow
                .filter((row) => row.delivered_run_id != null && row.delivered_run_id > watermark)
                .map((row) => row.posting_id),
        ),
      );
      // Advanced AFTER the set is computed, never before, or the comparison is against its own
      // answer. Skipped when no row carries a run at all, so a momentarily empty queue cannot
      // ratchet the watermark backwards.
      if (runs.length > 0) writeWatermark(Math.max(...runs));
    }
    setStashed(null);
    setNewCount(0);
    setRemoved(new Map());
  }, []);

  /*
   * Bumped when a credential is captured after load — the CLI's URL pasted into this open tab
   * (`api/token.ts`). The load below is keyed on it, so the page that is currently showing "Not
   * authorised. Re-open the URL the CLI printed" retries with the new bearer instead of asking
   * the reader to do again what they just did.
   */
  const [tokenNonce, setTokenNonce] = useState(0);
  useEffect(() => {
    const onToken = () => {
      setTokenNonce((current) => current + 1);
    };
    window.addEventListener(TOKEN_EVENT, onToken);
    return () => {
      window.removeEventListener(TOKEN_EVENT, onToken);
    };
  }, []);

  useEffect(() => {
    let live = true;
    void getQueue()
      .then((response) => {
        if (!live) return;
        // Cleared on success, not only set on failure: a retry that works must take the card down.
        setLoadError(null);
        adopt(response);
      })
      .catch((caught: unknown) => {
        if (live) setLoadError(errorMessage(caught, "Could not load the queue."));
      });
    return () => {
      live = false;
    };
  }, [adopt, tokenNonce]);

  /*
   * A background refresh NEVER re-orders the list or moves a row under the pointer. It stashes the
   * newer response and surfaces a quiet count; adopting it is the reader's decision.
   */
  useEffect(() => {
    const timer = window.setInterval(() => {
      void getQueue()
        .then((response) => {
          // `?? []` as above, and it matters more here: this `.catch` swallows deliberately, so
          // the same throw would kill the poll silently and "N new" would never appear again for
          // the life of the process.
          const fresh = [...response.rows, ...(response.review ?? [])].filter(
            (row) => !knownIds.current.has(row.posting_id),
          );
          if (fresh.length > 0) {
            setStashed(response);
            setNewCount(fresh.length);
          }
        })
        .catch(() => {
          /* A failed poll is not an error the reader has to act on; the next one retries. */
        });
    }, POLL_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    // Not until the lead is known to be ON the page: a stale `lead` in the URL must not spend a
    // request on a posting the queue does not hold, and the effect below drops it instead.
    if (selected === null || !leadKnown) return;
    let live = true;
    void getDetail(selected)
      .then((response) => {
        if (live) setDetail(response);
      })
      .catch((caught: unknown) => {
        if (live) {
          setDetailError({ id: selected, message: errorMessage(caught, "Could not load this lead.") });
        }
      });
    return () => {
      live = false;
    };
  }, [selected, leadKnown]);

  useEffect(() => {
    if (selected === null || answers !== null) return;
    void getAnswers()
      .then(setAnswers)
      .catch(() => {
        /* The panel shows its own loading line; a missing answers.yaml is not a page failure. */
      });
  }, [selected, answers]);

  const shownDetail = detail !== null && detail.row.posting_id === selected ? detail : null;
  const shownError =
    detailError !== null && detailError.id === selected ? detailError.message : null;
  const detailLoading = selected !== null && shownDetail === null && shownError === null;

  /*
   * `f` on a row: open the lead and put the cursor in the pane's date input. It never writes a
   * date — see `QueueTable`'s key handler for why a blind one would be a guess.
   *
   * A ref plus an effect rather than a focus call here, because the pane's detail is FETCHED: at
   * the moment this runs the input does not exist yet on any lead but the open one. The ref is
   * written in an event handler and read in an effect, never during render.
   */
  const followUpFocus = useRef<number | null>(null);
  const focusFollowUp = useCallback(
    (row: QueueRow) => {
      if (selected === row.posting_id) {
        const input = document.getElementById(FOLLOW_UP_INPUT_ID);
        if (input !== null) {
          input.focus();
          return;
        }
        // The lead is open but its detail is still IN FLIGHT, so there is no input yet. Recording
        // the id lands the cursor when it arrives; `?.focus()` on nothing dropped the keystroke.
        followUpFocus.current = row.posting_id;
        return;
      }
      followUpFocus.current = row.posting_id;
      openLead(row.posting_id);
    },
    [selected, openLead],
  );

  /*
   * The record is for ONE keystroke on ONE lead, and two paths used to outlive it: a detail load
   * that FAILED (the success effect below was the only place that cleared it) and the reader
   * opening some other lead. Either left an id armed, so a later CLICK on that first lead pulled
   * the cursor off the list and into the date input — exactly what the effect below exists to
   * prevent. Cleared whenever the open lead is not the recorded one, and whenever that lead's
   * detail came back an error.
   */
  useEffect(() => {
    if (followUpFocus.current !== selected || shownError !== null) followUpFocus.current = null;
  }, [selected, shownError]);

  /*
   * The other half of `f`: the pane's detail arrives asynchronously, so the input the keystroke
   * asked for does not exist until this lands. Keyed on `shownDetail` and guarded on the id the
   * keystroke recorded, so a pane opened by a CLICK never steals the cursor off the list.
   */
  useEffect(() => {
    if (followUpFocus.current === null || shownDetail === null) return;
    if (shownDetail.row.posting_id !== followUpFocus.current) return;
    followUpFocus.current = null;
    document.getElementById(FOLLOW_UP_INPUT_ID)?.focus();
  }, [shownDetail]);

  /*
   * A `lead` the page cannot show — a stale bookmark, or a lead applied to since the link was sent
   * — is dropped from the URL rather than left to open a pane on a posting in neither lane. Runs
   * only once the queue has loaded: before that, EVERY id is unknown.
   */
  useEffect(() => {
    if (data === null || selected === null || leadKnown) return;
    setRouteParams({ lead: null });
  }, [data, selected, leadKnown, setRouteParams]);

  /*
   * Below `lg` the detail pane is an opaque full-screen sheet, so it is a modal and everything it
   * covers has to be `inert` — the platform's own containment, no focus-trap dependency. Without
   * it, Shift+Tab out of the open sheet landed on a grid row BEHIND it, where `a` marks the lead
   * applied: a write the reader cannot see the target of, whose only undo is a toast. At `lg` and
   * up the pane is a column beside a list that stays fully usable, nothing is covered, and nothing
   * is inerted — Enter to look then ↓ to carry on down the queue is the whole point of that tier.
   *
   * The header and the skip link are covered too and are not in this subtree, so the sheet's state
   * is reported up to `App`. The toaster is deliberately NOT inerted: it draws above the sheet and
   * carries the only undo a mark-applied has.
   */
  const sideBySide = useMediaQuery(SIDE_BY_SIDE);
  const sheetOpen = selected !== null && !sideBySide;
  useEffect(() => {
    onSheet(sheetOpen);
    return () => {
      onSheet(false);
    };
  }, [onSheet, sheetOpen]);

  /*
   * Rank is the array POSITION, and there are now two arrays — so each lane is ranked within
   * itself, 1..n. Sharing one map across both would print a review lane starting at rank 380,
   * which reads as "worse than everything above" when it is a different list entirely.
   */
  const rankByPosting = useMemo(() => {
    const map = new Map<number, number>();
    (data?.rows ?? []).forEach((row, index) => {
      map.set(row.posting_id, index + 1);
    });
    return map;
  }, [data]);

  const reviewRankByPosting = useMemo(() => {
    const map = new Map<number, number>();
    (data?.review ?? []).forEach((row, index) => {
      map.set(row.posting_id, index + 1);
    });
    return map;
  }, [data]);

  const reviewRankOf = useCallback(
    (row: QueueRow) => reviewRankByPosting.get(row.posting_id) ?? 0,
    [reviewRankByPosting],
  );

  const rankOf = useCallback(
    (row: QueueRow) => rankByPosting.get(row.posting_id) ?? 0,
    [rankByPosting],
  );

  /*
   * ONE predicate for both lists. The toolbar's filters apply to the apply lane AND the review
   * lane: a filter that silently skipped one would make it look empty for a query that matches,
   * which is the worst version of this feature — a reader concludes there is nothing to review
   * when there is.
   *
   * A null score is not below a floor, it is unmeasured — so a floor excludes it rather than
   * silently treating "unknown" as zero.
   */
  const passesFilters = useCallback(
    (row: QueueRow): boolean => {
      const floor = minScore.trim() === "" ? null : Number(minScore);
      if (removed.has(row.posting_id)) return false;
      if (runFilter !== null && row.delivered_run_id !== runFilter) return false;
      if (!matchesQuery(row, query.trim())) return false;
      if (!matchesLocation(row, location.trim())) return false;
      if (board !== "" && row.provider !== board) return false;
      if (mode !== "" && (row.remote_policy ?? NO_MODE) !== mode) return false;
      if (hideThin !== "" && row.thin_jd) return false;
      if (hideUnverifiable !== "" && row.status === "unverifiable") return false;
      if (floor !== null && !Number.isNaN(floor) && (row.score === null || row.score < floor)) {
        return false;
      }
      return true;
    },
    [removed, runFilter, query, location, minScore, board, mode, hideThin, hideUnverifiable],
  );

  const filtered = useMemo(() => (data?.rows ?? []).filter(passesFilters), [data, passesFilters]);

  const sortedApply = useMemo(() => {
    // The verdict facets narrow it; `null` shows all.
    const base =
      facet === null ? filtered : filtered.filter((row) => matchesFacet(row, facet, newIds));
    return sortRows(base, sort, rankOf);
  }, [filtered, facet, newIds, sort, rankOf]);
  /* Counted BEFORE the fold, so a folded group's one visible row still says how many it stands
     for. Folding last keeps the best-placed lead of each group, in whatever order is sorting. */
  const similarApply = useMemo(() => similarGroups(sortedApply), [sortedApply]);
  const visible = useMemo(
    () => (hideSimilar === "" ? sortedApply : firstOfEachGroup(sortedApply)),
    [sortedApply, hideSimilar],
  );

  const filteredReview = useMemo(
    () => (data?.review ?? []).filter(passesFilters),
    [data, passesFilters],
  );

  const sortedReview = useMemo(() => {
    // A verdict facet reaches the review lane too: a review lead can be `eligible` — held only for
    // its location — so filtering "eligible" while skipping this list is the documented "make the
    // review list look empty for a matching filter" failure. `review` shows the whole lane.
    const byVerdict =
      facet === null
        ? filteredReview
        : filteredReview.filter((row) => matchesFacet(row, facet, newIds));
    const base =
      reasonFacet === null
        ? byVerdict
        : byVerdict.filter((row) => row.review_reason === reasonFacet);
    return sortRows(base, sort, reviewRankOf);
  }, [filteredReview, facet, reasonFacet, newIds, sort, reviewRankOf]);
  const similarReview = useMemo(() => similarGroups(sortedReview), [sortedReview]);
  const visibleReview = useMemo(
    () => (hideSimilar === "" ? sortedReview : firstOfEachGroup(sortedReview)),
    [sortedReview, hideSimilar],
  );

  /*
   * THE VISIBLE ORDER: the one sequence "next job", the position count, the previous/next buttons
   * and the apply session all walk. It is exactly what the reader sees, top to bottom, under the
   * current list, filters, sort and fold — never a re-ranked or re-derived order, and never a job
   * outside the list on screen.
   */
  const navList = useMemo<QueueRow[]>(
    () =>
      lens === "explore" ? visible : lens === "review" ? visibleReview : [...visible, ...visibleReview],
    [lens, visible, visibleReview],
  );

  /*
   * Each list's count is the number of jobs IN THAT LIST matching the search, place and filters —
   * never a sum across lists that could overlap. The two lanes are disjoint by construction (a job
   * is in the apply lane or the review lane, never both), which is the only reason "All jobs" may
   * be their sum.
   */
  const lensCounts: Record<Lens, number> = {
    explore: filtered.length,
    review: filteredReview.length,
    all: filtered.length + filteredReview.length,
  };

  /*
   * THE APPLICATION HISTORY, for the summary's "recorded today / past 7 days". Read once, with a
   * deadline: the page never waits on it, because jobs are the work and this is a count. On a
   * failure or a timeout the summary says so and offers a retry instead of loading forever.
   *
   * `confirmed` is what THIS visit has recorded, keyed by posting and added only AFTER the server
   * said yes (see `act`) — so a failed write can never inflate it. An entry whose posting the
   * history already lists as submitted is not counted twice.
   */
  const [applied, setApplied] = useState<AppliedState>({ kind: "loading" });
  const [appliedAttempt, setAppliedAttempt] = useState(0);
  const [confirmed, setConfirmed] = useState<ReadonlyMap<number, string>>(() => new Map());
  useEffect(() => {
    let live = true;
    void withTimeout(getApplied(), APPLIED_TIMEOUT_MS)
      .then((data) => {
        if (live) setApplied({ kind: "ready", data });
      })
      .catch(() => {
        if (live) setApplied({ kind: "failed" });
      });
    return () => {
      live = false;
    };
  }, [appliedAttempt, tokenNonce]);
  const retryApplied = useCallback(() => {
    setApplied({ kind: "loading" });
    setAppliedAttempt((current) => current + 1);
  }, []);

  const recordedState: RecordedState = useMemo(() => {
    const entries = [...confirmed].map(([postingId, at]) => ({ postingId, at }));
    if (applied.kind === "loading") return { kind: "loading" };
    if (applied.kind === "failed") {
      return { kind: "failed", sessionOnly: entries.length };
    }
    // Only postings the history ALREADY counts as submitted: a withdrawn attempt on the same
    // posting is not a record, and recording it again is a new application that must count.
    const already = new Set(
      applied.data.rows
        .filter((row) => row.posting_id !== null && SUBMITTED_STATUSES.includes(row.status))
        .map((row) => row.posting_id),
    );
    const fresh = entries
      .filter((entry) => !already.has(entry.postingId))
      .map((entry) => ({ status: "applied", submitted_at: entry.at }));
    const counted = countRecorded([...applied.data.rows, ...fresh]);
    return { kind: "ready", today: counted.today, week: counted.week };
  }, [applied, confirmed]);

  /*
   * THE APPLY SESSION. Optional, and off until the person starts it. A ref mirrors the state so a
   * write's `.then` — which runs long after the render that created it — reads the session as it
   * is NOW, not as it was when the button was pressed.
   */
  const [session, setSessionState] = useState<Session | null>(null);
  const sessionRef = useRef<Session | null>(null);
  const setSession = useCallback((next: Session | null) => {
    sessionRef.current = next;
    setSessionState(next);
  }, []);
  const [sessionEnd, setSessionEnd] = useState<SessionEnd | null>(null);
  /* The workspace's own acknowledgement after "Record application" when NO session is running:
     the job has left the list, so the workspace says what just happened and what comes next. */
  const [recordedPanel, setRecordedPanel] = useState<{ row: QueueRow; nextId: number | null } | null>(
    null,
  );
  const recordLock = useRef(0);

  const bandCounts: QueueCounts = useMemo(() => {
    let appliedDelta = 0;
    let skippedDelta = 0;
    let reportedDelta = 0;
    for (const kind of removed.values()) {
      if (kind === "applied") appliedDelta += 1;
      else if (kind === "skipped") skippedDelta += 1;
      else reportedDelta += 1;
    }
    return {
      // Recomputed against the active filter.
      in_queue: filtered.length,
      eligible: filtered.filter((row) => row.verdict === "eligible").length,
      uncertain: filtered.filter((row) => row.verdict === "uncertain").length,
      // Recomputed against the active filter, exactly as the two above are and for the same
      // reason: the cell has to agree with the list the reader is looking at. Facet-BLIND, like
      // every cell here — `filtered` is the text, score-floor and run filters, never the facet,
      // so clicking one cell cannot drop the cell the reader clicks next to zero.
      judge_eligible: filtered.filter((row) => row.judge_verdict === "eligible").length,
      judge_uncertain: filtered.filter((row) => row.judge_verdict === "uncertain").length,
      // `== null`, never `=== null`: an older server omits the field, and "the server cannot say"
      // reads as "the gate has not spoken" rather than throwing off the count.
      judge_unjudged: filtered.filter((row) => row.judge_verdict == null).length,
      // Recomputed against the active filter like the five above, and over the APPLY lane like
      // every cell here: `filtered` is that lane. The FACET reaches both lanes, as the verdict
      // and `judge_*` facets do, so clicking this cell can show MORE rows than the number on
      // it — the count answers "how much of the work list is due", and the filter answers "show
      // me everything that is due". Recomputing keeps the cell honest while a write is still
      // optimistic and the payload has not been re-fetched.
      follow_up_due: filtered.filter((row) => isFollowUpDue(row.follow_up)).length,
      // Passed through, NOT recomputed: an ineligible lead is never in `rows`, so no
      // client-side filter can see one. Recomputing it here would always yield 0 and quietly
      // contradict the server.
      ineligible: data?.counts.ineligible ?? 0,
      // Passed through for the same reason as `ineligible`: a closed posting is drained on disk,
      // so it is never a row and no client-side filter can see one.
      closed: data?.counts.closed ?? 0,
      // Passed through for the same reason again: a lane copy is drained to `_lane_copy` and is
      // never a row.
      lane_copy: data?.counts.lane_copy ?? 0,
      // Recomputed against the active filter, unlike `ineligible`: a review lead IS in the
      // payload, so a client-side filter can see one and the cell must agree with the list the
      // reader is looking at.
      review: filteredReview.length,
      applied_ever: (data?.counts.applied_ever ?? 0) + appliedDelta,
      skipped: (data?.counts.skipped ?? 0) + skippedDelta,
      reported: (data?.counts.reported ?? 0) + reportedDelta,
      // Run-scoped facts, not filter-scoped: they come from the server unchanged.
      delivered_last_run: data?.counts.delivered_last_run ?? 0,
      last_run_finished: data?.counts.last_run_finished ?? null,
    };
  }, [filtered, filteredReview, removed, data]);

  const restore = useCallback((postingId: number) => {
    setCollapsing((current) => {
      const next = new Set(current);
      next.delete(postingId);
      return next;
    });
    setRemoved((current) => {
      const next = new Map(current);
      next.delete(postingId);
      return next;
    });
  }, []);

  /*
   * "Did you apply?" on return. An apply page opened from here — `o`, or a click on an apply link
   * — arms `pendingApply`; this TAB then has to be hidden and shown again before the question is
   * put. Visibility and never window focus: switching to another application and back blurs and
   * focuses the window without the reader having gone near the apply page, and a link
   * middle-clicked into a background tab is asked about only once the reader has actually gone to
   * it and come back. A ref, because it is written in handlers and read in DOM listeners and
   * nothing renders from it; the prompt itself is state.
   */
  const pendingApply = useRef<{ row: QueueRow; left: boolean } | null>(null);
  const [returnPrompt, setReturnPrompt] = useState<QueueRow | null>(null);
  const noteApplyOpened = useCallback((row: QueueRow) => {
    pendingApply.current = { row, left: false };
  }, []);
  useEffect(() => {
    const onLeave = () => {
      if (pendingApply.current !== null) pendingApply.current.left = true;
    };
    const onReturn = () => {
      const pending = pendingApply.current;
      if (pending === null || !pending.left) return;
      pendingApply.current = null;
      setReturnPrompt(pending.row);
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") onLeave();
      else onReturn();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  /*
   * The optimistic half of a follow-up, applied to BOTH copies of the row: the one in the lane
   * and the one the open pane is rendering. They are two objects for one lead, so patching only
   * `data` would leave the pane's date input showing the old value until the next fetch.
   *
   * A follow-up removes nothing, so there is no `removed`/`collapsing` dance here and no
   * successor to focus: the row stays exactly where it is and gains a chip.
   */
  const applyFollowUp = useCallback((postingId: number, value: string | null) => {
    const patch = (row: QueueRow): QueueRow =>
      row.posting_id === postingId ? { ...row, follow_up: value } : row;
    setData((current) =>
      current === null
        ? current
        : { ...current, rows: current.rows.map(patch), review: current.review.map(patch) },
    );
    setDetail((current) =>
      current === null || current.row.posting_id !== postingId
        ? current
        : { ...current, row: patch(current.row) },
    );
  }, []);

  /*
   * Pin a follow-up date, or clear one. The undo restores the PREVIOUS value through the same
   * two routes rather than a local repaint, so a toast that says it put the old date back has
   * actually written it — the rule `unapply` established for the applied toast.
   */
  const followUp = useCallback(
    (row: QueueRow, next: string | null) => {
      const previous = row.follow_up ?? null;
      if (previous === next) return;
      applyFollowUp(row.posting_id, next);
      const write = (value: string | null): Promise<FollowUpResponse> =>
        value === null ? clearFollowUp(row.posting_id) : setFollowUp(row.posting_id, value);
      void write(next)
        .then((response) => {
          /*
           * Reconciled against the ECHO, which is what `FollowUpResponse.follow_up` is for: the
           * value sent and the value stored are the same string only while the route's parser
           * stays strict, and a page that keeps showing what it sent is a page that disagrees
           * with the store until the next fetch.
           *
           * `== null`, never `=== null`: a server older than the echo omits the key, and the
           * optimistic value is the better answer there than blanking a date that was written.
           */
          const stored = response.follow_up == null ? next : response.follow_up;
          if (stored !== next) applyFollowUp(row.posting_id, stored);
          push({
            message:
              stored === null
                ? `Cleared the follow-up on ${row.company} — ${row.title}`
                : `Follow up on ${row.company} — ${row.title} on ${stored}`,
            undo: () => {
              applyFollowUp(row.posting_id, previous);
              void write(previous).catch((caught: unknown) => {
                applyFollowUp(row.posting_id, stored);
                push({
                  message: errorMessage(caught, "Could not undo that follow-up."),
                  tone: "error",
                });
              });
            },
          });
        })
        .catch((caught: unknown) => {
          applyFollowUp(row.posting_id, previous);
          push({
            message: errorMessage(caught, "The write failed and the date was restored."),
            tone: "error",
          });
        });
    },
    [applyFollowUp, push],
  );

  /** Open a job and put the cursor in its workspace. Not on a write control: a held Enter must
   *  never reach "Record application" of a job nobody has read yet. */
  const openAndFocus = useCallback(
    (postingId: number) => {
      openLead(postingId);
      window.setTimeout(() => {
        document.getElementById(PANE_ID)?.focus();
      }, 0);
    },
    [openLead],
  );

  const act = useCallback(
    (row: QueueRow, kind: Removal) => {
      /* The second record inside the lock is refused outright. See `RECORD_LOCK_MS`. */
      if (kind === "applied") {
        if (Date.now() < recordLock.current) return;
        recordLock.current = Date.now() + RECORD_LOCK_MS;
      }
      // Whatever was decided about this lead answers the question the prompt would have asked.
      if (pendingApply.current?.row.posting_id === row.posting_id) pendingApply.current = null;
      setReturnPrompt((current) => (current?.posting_id === row.posting_id ? null : current));

      /*
       * Where to go next, in the VISIBLE order. `forward` is strictly the job below this one: an
       * apply session walks down the list and never turns back, and when there is nothing below it
       * says so rather than quietly picking something else. `successor` is the older rule for the
       * cursor — the job below, or above at the end of a list — and still decides where focus
       * lands when the workspace is not involved.
       */
      const index = navList.findIndex((candidate) => candidate.posting_id === row.posting_id);
      const forward = index === -1 ? undefined : navList[index + 1];
      const successor = index === -1 ? undefined : (navList[index + 1] ?? navList[index - 1]);

      const openedHere = selected === row.posting_id;
      const live = sessionRef.current;
      /* In a session, finishing a job in the open workspace moves the workspace on. */
      const advance = openedHere && live !== null;
      /* Outside one, recording says what happened and offers the next step. */
      const showPanel = openedHere && live === null && kind === "applied";

      /*
       * Set when the write FAILED. The write can be refused on either side of the collapse timer
       * below — a dead connection answers in microseconds — and a restore that runs first would
       * be undone by the timer removing the row a moment later, leaving a job gone from the list
       * after the page had said it was back. Whoever runs second honours this.
       */
      let reverted = false;

      // Optimistic: the row collapses to zero height, then leaves the list.
      setCollapsing((current) => new Set(current).add(row.posting_id));
      window.setTimeout(() => {
        if (reverted) return;
        setRemoved((current) => new Map(current).set(row.posting_id, kind));
        setCollapsing((current) => {
          const next = new Set(current);
          next.delete(row.posting_id);
          return next;
        });
        // The workspace has taken the cursor (or is about to put up its own panel): do not drag
        // it back onto a list row.
        if (advance || showPanel) return;
        if (successor === undefined) {
          // Nothing left to move to — a filtered-down list whose last lead was just acted on.
          // Without this the focused row unmounts and focus falls to `<body>`, which strands a
          // keyboard reader at the top of the document with no way back but Tab. `activeId` is
          // cleared too: leaving it pointing at a deleted posting makes the roving stop resolve
          // to a row that no longer exists.
          setActiveId(null);
          document.getElementById(FILTER_INPUT_ID)?.focus();
          return;
        }
        setActiveId(successor.posting_id);
        document
          .querySelector<HTMLElement>(`[data-row-id="${String(successor.posting_id)}"]`)
          ?.focus();
      }, COLLAPSE_MS);

      if (openedHere) {
        if (advance) {
          if (forward === undefined) {
            openLead(null);
            setSessionEnd("end-of-list");
          } else {
            setActiveId(forward.posting_id);
            openAndFocus(forward.posting_id);
          }
        } else if (showPanel) {
          setRecordedPanel({ row, nextId: forward?.posting_id ?? null });
        } else {
          openLead(null);
        }
      }

      const call =
        kind === "applied" ? markApplied : kind === "skipped" ? markSkipped : report;
      void call(row.posting_id)
        .then(() => {
          if (kind === "skipped") {
            push({
              message: `Skipped ${row.company} — ${row.title}`,
              undo: () => {
                void unskip(row.posting_id)
                  .then(() => {
                    restore(row.posting_id);
                  })
                  .catch((caught: unknown) => {
                    push({
                      message: errorMessage(caught, "Could not un-skip that lead."),
                      tone: "error",
                    });
                  });
              },
            });
            return;
          }
          if (kind === "reported") {
            push({
              message: `Reported ${row.company} — ${row.title} for review. It is held out of the queue until investigated.`,
              undo: () => {
                void unreport(row.posting_id)
                  .then(() => {
                    restore(row.posting_id);
                  })
                  .catch((caught: unknown) => {
                    push({
                      message: errorMessage(caught, "Could not un-report that lead."),
                      tone: "error",
                    });
                  });
              },
            });
            return;
          }

          /*
           * The write LANDED. Only now does anything count it: the progress figure, the session's
           * tally and the batch check all move here, after the server's yes, so a failed write
           * can never leave a number that is higher than the truth.
           */
          setConfirmed((current) => new Map(current).set(row.posting_id, new Date().toISOString()));
          const during = sessionRef.current;
          if (during !== null) {
            const next = { ...during, count: during.count + 1 };
            setSession(next);
            if (next.batch !== null && next.count >= next.batch) {
              openLead(null);
              setSessionEnd("batch");
            }
          }
          push({
            /*
             * Says what happened, in the past tense, and what Undo does: it withdraws the
             * application record and only then puts the row back — the same write-then-restore
             * order as skip and report, so a failed withdrawal leaves the row out rather than
             * showing a job the store still counts as applied.
             */
            message: `Application recorded for ${row.company}.`,
            undo: () => {
              void unapply(row.posting_id)
                .then(() => {
                  restore(row.posting_id);
                  setConfirmed((current) => {
                    const next = new Map(current);
                    next.delete(row.posting_id);
                    return next;
                  });
                  const now = sessionRef.current;
                  if (now !== null) setSession({ ...now, count: Math.max(0, now.count - 1) });
                  setRecordedPanel((panel) =>
                    panel?.row.posting_id === row.posting_id ? null : panel,
                  );
                  setSessionEnd(null);
                  // Put the reader back on the job they just took back — but only when the
                  // workspace had moved on from it. An undo from the list's own key leaves the
                  // reader where they are: stealing focus from whatever they are doing now would
                  // be worse than the row quietly coming back.
                  if (advance || showPanel) openAndFocus(row.posting_id);
                })
                .catch((caught: unknown) => {
                  push({
                    message: errorMessage(caught, "Could not withdraw that application."),
                    tone: "error",
                  });
                });
            },
          });
        })
        .catch((caught: unknown) => {
          reverted = true;
          restore(row.posting_id);
          setRecordedPanel((panel) => (panel?.row.posting_id === row.posting_id ? null : panel));
          setSessionEnd(null);
          // The workspace moved on before the write answered; take the reader back to the job the
          // failure is about, so what went wrong and what to do are in the same place.
          if (advance || showPanel) openAndFocus(row.posting_id);
          push({
            message:
              kind === "applied"
                ? `Could not record the application for ${row.company} — nothing was saved, and the job is back on your list. Try again in a moment.`
                : errorMessage(caught, "The write failed and the row was restored."),
            tone: "error",
          });
        });
    },
    [push, restore, selected, openLead, openAndFocus, navList, setSession],
  );

  /*
   * The selection, INTERSECTED with what the apply table is currently showing. `marked` is a set
   * of ids, and a row can leave the list under it — the filter text changes, a facet goes on, a
   * poll refreshes. Taking the intersection is what makes "N selected" and "Skip N" describe the
   * rows the reader can see, rather than a count that includes leads behind a filter they have
   * since turned on.
   */
  const markedRows = useMemo(
    () => visible.filter((row) => marked.has(row.posting_id)),
    [visible, marked],
  );

  const selection: Selection = useMemo(
    () => ({
      marked,
      onMark: (postingId) => {
        setMarked((current) => {
          const next = new Set(current);
          if (!next.delete(postingId)) next.add(postingId);
          return next;
        });
      },
      onMarkMany: (postingIds, on) => {
        setMarked((current) => {
          const next = new Set(current);
          for (const id of postingIds) {
            if (on) next.add(id);
            else next.delete(id);
          }
          return next;
        });
      },
    }),
    [marked],
  );

  const clearSelection = useCallback(() => {
    setMarked(new Set());
  }, []);

  /* The apply-lane rows listed at a row's company — the ones `c` and the pane's button select. */
  const companyRows = useCallback(
    (row: QueueRow) => {
      const company = row.company.trim().toLowerCase();
      return visible.filter((candidate) => candidate.company.trim().toLowerCase() === company);
    },
    [visible],
  );
  const selectCompany = useCallback(
    (row: QueueRow) => {
      selection.onMarkMany(
        companyRows(row).map((candidate) => candidate.posting_id),
        true,
      );
    },
    [companyRows, selection],
  );

  /*
   * Bulk skip: ONE write for the whole selection and ONE for its undo.
   *
   * The optimistic shape is `act`'s, applied to a block — collapse, then remove after the
   * animation — so a bulk skip looks like N single skips that happened at once rather than a new
   * kind of event. What it CANNOT share with `act` is the write: the point of this ticket is that
   * 40 rows are 40 `mark_job_skipped` calls inside one transaction, not 40 requests.
   *
   * The call is keyed on `job_id` because skip state is, server-side. `byJob` is how a `failed`
   * id from the response gets back to the row that has to be restored.
   */
  const skipSelected = useCallback(() => {
    if (markedRows.length === 0) return;
    const postingIds = markedRows.map((row) => row.posting_id);
    const jobIds = markedRows.map((row) => row.job_id);
    const byJob = new Map(markedRows.map((row) => [row.job_id, row.posting_id]));
    const leaving = new Set(postingIds);

    /*
     * Where the cursor lands. The Skip button is IN the bulk bar, and the bar unmounts the moment
     * the selection is spent — so without this, focus falls to `<body>` and a reader who triaged
     * by keyboard is back at the top of the document. The first surviving row below the block,
     * else the last surviving row, else the filter box.
     */
    const surviving = visible.filter((row) => !leaving.has(row.posting_id));
    const lastLeaving = Math.max(
      ...postingIds.map((id) => visible.findIndex((row) => row.posting_id === id)),
    );
    const successor =
      visible.slice(lastLeaving + 1).find((row) => !leaving.has(row.posting_id)) ??
      surviving[surviving.length - 1];

    clearSelection();
    setCollapsing((current) => {
      const next = new Set(current);
      for (const id of postingIds) next.add(id);
      return next;
    });
    /*
     * `leaving`, not `postingIds` — and it is MUTABLE on purpose. The write can resolve on either
     * side of this timer: an immediate answer lands first, a slow one lands after. So the two
     * closures share one set, the response deletes from it whatever the server refused, and the
     * removal below marks only what is still in it. Reading `postingIds` here instead would let a
     * fast `failed` restore be immediately re-removed by this very callback.
     */
    window.setTimeout(() => {
      setRemoved((current) => {
        const next = new Map(current);
        for (const id of leaving) next.set(id, "skipped");
        return next;
      });
      setCollapsing((current) => {
        const next = new Set(current);
        for (const id of postingIds) next.delete(id);
        return next;
      });
      if (successor === undefined) {
        setActiveId(null);
        document.getElementById(FILTER_INPUT_ID)?.focus();
        return;
      }
      setActiveId(successor.posting_id);
      document
        .querySelector<HTMLElement>(`[data-row-id="${String(successor.posting_id)}"]`)
        ?.focus();
    }, COLLAPSE_MS);
    if (selected !== null && leaving.has(selected)) openLead(null);

    void skipMany(jobIds)
      .then((result) => {
        /*
         * `?? []` on both, not `[]` on neither: the viewer serves this bundle from disk and
         * answers from the Python it imported at start-up, so a server that has the route but
         * omits a field must degrade to "nothing here" rather than throw (D-360).
         */
        const wrote = result.skipped ?? [];
        const refused = result.failed ?? [];
        // Only the server knows which ids it actually wrote, and the optimistic removal covered
        // the whole selection — so anything it refused comes straight back into the list.
        for (const jobId of refused) {
          const postingId = byJob.get(jobId);
          if (postingId === undefined) continue;
          leaving.delete(postingId);
          restore(postingId);
        }
        const message =
          refused.length === 0
            ? `Skipped ${String(wrote.length)}`
            : `Skipped ${String(wrote.length)}, ${String(refused.length)} failed`;
        if (wrote.length === 0) {
          push({ message, tone: "error" });
          return;
        }
        push({
          message,
          // The undo covers the ids the server WROTE and no others: offering to un-skip an id it
          // refused would report a reversal of something that never happened.
          undo: () => {
            void unskipMany(wrote)
              .then(() => {
                for (const jobId of wrote) {
                  const postingId = byJob.get(jobId);
                  if (postingId !== undefined) restore(postingId);
                }
              })
              .catch((caught: unknown) => {
                push({
                  message: errorMessage(caught, "Could not un-skip those leads."),
                  tone: "error",
                });
              });
          },
        });
      })
      .catch((caught: unknown) => {
        leaving.clear();
        for (const id of postingIds) restore(id);
        push({
          message: errorMessage(caught, "The write failed and the rows were restored."),
          tone: "error",
        });
      });
  }, [markedRows, visible, clearSelection, selected, openLead, push, restore]);

  /*
   * The one shortcut that is safe on `window`: it only moves focus. Everything that WRITES is
   * handled on the grid, where a row must already be focused, so no keystroke aimed at the filter
   * box can mark a lead applied. Guarded against firing while the reader is typing.
   */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      const input = document.getElementById(FILTER_INPUT_ID);
      if (input === null) return;
      event.preventDefault();
      input.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const openApply = useCallback(
    (row: QueueRow) => {
      if (!openApplyUrl(row.apply_url)) {
        push({ message: `No usable apply link for ${row.company} — ${row.title}.`, tone: "error" });
        return;
      }
      noteApplyOpened(row);
    },
    [push, noteApplyOpened],
  );

  /*
   * Counted over the WHOLE lane, never over `visibleReview`: these counts are the menu, and a menu
   * that re-counts itself against its own selection offers one entry with the number you already
   * chose and zeroes beside everything else.
   */
  const boardCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of [...(data?.rows ?? []), ...(data?.review ?? [])]) {
      if (row.provider != null) counts.set(row.provider, (counts.get(row.provider) ?? 0) + 1);
    }
    return [...counts].sort(([a], [b]) => a.localeCompare(b));
  }, [data]);
  const modeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of [...(data?.rows ?? []), ...(data?.review ?? [])]) {
      const key = row.remote_policy ?? NO_MODE;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts].sort(([a], [b]) => a.localeCompare(b));
  }, [data]);
  const reasonCounts = useMemo(() => countReviewReasons(data?.review ?? []), [data]);

  const setLens = useCallback(
    (next: Lens) => {
      setLensPref(next);
    },
    [setLensPref],
  );

  const toggleReason = useCallback(
    (next: ReviewReason) => {
      const clearing = reasonFacet === next;
      setReasonFacet(clearing ? null : next);
      // A reason belongs to the review lane, so choosing one shows that lane: a filter whose entire
      // result is on a list that is not on screen would look like an empty page.
      if (!clearing) setLensPref("review");
    },
    [reasonFacet, setReasonFacet, setLensPref],
  );

  // Clicking the active facet's cell again clears it — one control, both directions.
  const toggleFacet = useCallback(
    (next: QueueFacet) => {
      if (next === "review") {
        // A lane, not a row predicate: it is the Needs review list.
        setFacet(null);
        setLensPref(lens === "review" ? "explore" : "review");
        return;
      }
      const clearing = facet === next;
      setFacet(clearing ? null : next);
      // A facet reaches both lanes, so turning one on shows both: the number that was clicked
      // counts jobs across them, and a list that held back half of those would disagree with it.
      if (!clearing) setLensPref("all");
    },
    [facet, lens, setFacet, setLensPref],
  );

  /*
   * The view a saved view captures and restores: every filter, the facet, the list and the sort,
   * each in its session encoding. Restoring decodes through the same functions a reload uses, so a
   * view saved by an older bundle with a facet this one no longer knows drops that facet instead of
   * applying it — and a view saved with the old `review` facet becomes the Needs review list.
   */
  const currentView: QueueView = {
    query,
    location,
    minScore,
    board,
    mode,
    hideThin,
    hideUnverifiable,
    hideSimilar,
    facet: encodeFacet(facet),
    reason: encodeReason(reasonFacet),
    sort: encodeSort(sort),
    lens: encodeLens(lens),
  };
  const applyView = (view: QueueView) => {
    setQuery(view["query"] ?? "");
    setLocation(view["location"] ?? "");
    setMinScore(view["minScore"] ?? "");
    setBoard(view["board"] ?? "");
    setMode(view["mode"] ?? "");
    setHideThin(view["hideThin"] ?? "");
    setHideUnverifiable(view["hideUnverifiable"] ?? "");
    setHideSimilar(view["hideSimilar"] ?? "");
    setFacet(decodeFacet(view["facet"] ?? null));
    const reason = decodeReason(view["reason"] ?? null);
    setReasonFacet(reason);
    setLensPref(
      reason !== null || view["facet"] === "review" ? "review" : decodeLens(view["lens"] ?? null),
    );
    setSort(parseSortState(view["sort"] ?? null) ?? { key: "rank", direction: "asc" });
  };

  /* What the reader turned on, in words, so "Reset filters" is obviously the way back out. Each
     entry is one lever; the count behind "More filters" is how many of them it holds. */
  const moreActive = [
    board !== "",
    minScore.trim() !== "",
    hideThin !== "",
    hideUnverifiable !== "",
    hideSimilar !== "",
  ].filter(Boolean).length;
  const activeFilters = [
    query.trim() === "" ? null : `“${query.trim()}”`,
    location.trim() === "" ? null : `places matching “${location.trim()}”`,
    mode === "" ? null : mode === NO_MODE ? "no work arrangement stated" : mode,
    board === "" ? null : `${board} postings`,
    minScore.trim() === "" ? null : `ranking score of at least ${minScore.trim()}`,
    hideThin === "" ? null : "very short descriptions hidden",
    hideUnverifiable === "" ? null : "postings that can’t be verified hidden",
    hideSimilar === "" ? null : "similar roles collapsed",
    facet === null ? null : FACET_LABELS[facet],
    reasonFacet === null ? null : REVIEW_REASON_LABELS[reasonFacet],
  ].filter((entry): entry is string => entry !== null);
  const resetFilters = () => {
    setQuery("");
    setLocation("");
    setMode("");
    setBoard("");
    setMinScore("");
    setHideThin("");
    setHideUnverifiable("");
    setHideSimilar("");
    setFacet(null);
    setReasonFacet(null);
    if (runFilter !== null) setRouteParams({ run: null });
  };

  // The empty list must name the lever that emptied it.
  const emptyHint =
    activeFilters.length === 0
      ? "There is nothing in this list yet."
      : "Reset the filters above, or loosen one of them.";

  const lensLabel = LENSES.find((entry) => entry.key === lens)?.label ?? "Jobs";
  const laneTotal =
    lens === "explore"
      ? data?.rows.length ?? 0
      : lens === "review"
        ? data?.review.length ?? 0
        : (data?.rows.length ?? 0) + (data?.review.length ?? 0);

  /* Jobs due or new across BOTH lists, after the filters — the figures the summary prints. */
  const bothFiltered = useMemo(() => [...filtered, ...filteredReview], [filtered, filteredReview]);
  const newTotal = useMemo(
    () => bothFiltered.filter((row) => newIds.has(row.posting_id)).length,
    [bothFiltered, newIds],
  );
  const followUpsDue = useMemo(
    () => bothFiltered.filter((row) => isFollowUpDue(row.follow_up)).length,
    [bothFiltered],
  );

  /* ------------------------------------------------------------------------------- the session */

  const startSession = useCallback(() => {
    const first = navList[0];
    if (first === undefined) return;
    if (sessionRef.current === null) setSession({ batch: null, count: 0 });
    setSessionEnd(null);
    setRecordedPanel(null);
    setActiveId(first.posting_id);
    openAndFocus(first.posting_id);
  }, [navList, setSession, openAndFocus]);

  const endSession = useCallback(() => {
    setSession(null);
    setSessionEnd(null);
  }, [setSession]);

  /* What "keep going" means at the end of a LIST: the other list, when it has anything in it. */
  const otherList =
    lens === "explore" && visibleReview.length > 0
      ? { label: `Look at jobs that need review (${visibleReview.length.toLocaleString()})`, lens: "review" as const, first: visibleReview[0] }
      : lens === "review" && visible.length > 0
        ? { label: `Back to jobs to explore (${visible.length.toLocaleString()})`, lens: "explore" as const, first: visible[0] }
        : null;

  /* The neighbours IN THE VISIBLE ORDER, for the workspace's previous and next buttons. */
  const navIndex = selected === null ? -1 : navList.findIndex((row) => row.posting_id === selected);
  const previousRow = navIndex > 0 ? navList[navIndex - 1] : undefined;
  const nextRow = navIndex !== -1 ? navList[navIndex + 1] : undefined;
  const goTo = useCallback(
    (row: QueueRow) => {
      setActiveId(row.posting_id);
      openLead(row.posting_id);
    },
    [openLead],
  );

  if (loadError !== null) {
    /*
     * `role="alert"`, and a line that says what to DO, with the way to do it on the page: this
     * state renders as the whole page, and a status code on its own is not an error a reader can
     * act on. The technical text is kept, under the plain sentence, for whoever has to report it.
     */
    return (
      <div role="alert" className="max-w-2xl rounded-md bg-surface-2 p-5">
        <h2 className="text-base text-fg">The jobs could not be loaded.</h2>
        <p className="mt-1 text-sm text-fg-2">
          The page reads the store the command line maintains. Trying again usually works; if it
          keeps failing, re-open the URL <code className="font-mono text-fg-3">boardwatch web</code>{" "}
          printed — that URL carries the session token.
        </p>
        <p className="mt-2 text-xs text-fg-3">{loadError}</p>
        <button
          type="button"
          onClick={() => {
            setLoadError(null);
            setTokenNonce((current) => current + 1);
          }}
          className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-on-primary transition-colors duration-150 ease-in-out hover:bg-primary-strong"
        >
          <Icon name="refresh" />
          Try again
        </button>
      </div>
    );
  }

  if (data === null) {
    /* The layout of the page, empty: the summary, the lists and the workspace hold their places so
       nothing jumps when the jobs arrive, and the sentence says what is happening. */
    return (
      <div className="mx-auto flex w-full max-w-[100rem] flex-col gap-5" aria-busy="true">
        <p role="status" className="text-sm text-fg-2">
          Loading your jobs…
        </p>
        <span className="skeleton h-24 w-full" />
        <span className="skeleton h-11 w-2/3" />
        <div className="grid gap-4 lg:grid-cols-[minmax(22rem,30rem)_minmax(0,1fr)]">
          <div className="flex flex-col gap-2">
            {[0, 1, 2, 3, 4, 5].map((index) => (
              <span key={index} className="skeleton h-24 w-full" />
            ))}
          </div>
          <span className="skeleton hidden h-96 w-full lg:block" />
        </div>
      </div>
    );
  }

  const showExplore = lens === "explore" || lens === "all";
  const showReview = lens === "review" || lens === "all";
  const bothEmpty = data.rows.length === 0 && data.review.length === 0;

  const apply = (row: QueueRow) => {
    act(row, "applied");
  };

  const table = (kind: "explore" | "review") => {
    const rows = kind === "explore" ? visible : visibleReview;
    return (
      <QueueTable
        label={kind === "explore" ? "Jobs to explore" : "Needs review"}
        rows={rows}
        /* The bulk selection is the apply list's alone: a review job is held for a look, so
           "skip the whole block" is not what that list is for. */
        {...(kind === "explore" ? { selection, onSelectCompany: selectCompany } : {})}
        similarOf={(row) => (kind === "explore" ? similarApply : similarReview).get(row.posting_id)}
        emptyHint={emptyHint}
        selectedId={selected}
        activeId={activeId}
        onActivate={setActiveId}
        collapsing={collapsing}
        onOpenApply={openApply}
        onSelect={(row) => {
          // Re-clicking the open row must not rewrite the hash: the detail effect is keyed on
          // `selected`, and a no-op write that still produced a new value would re-fire it and
          // drop the workspace back to its loading state.
          if (row.posting_id === selected) return;
          openLead(row.posting_id);
        }}
        onApplied={apply}
        onSkip={(row) => {
          act(row, "skipped");
        }}
        onReport={(row) => {
          act(row, "reported");
        }}
        onFollowUp={focusFollowUp}
      />
    );
  };

  const closeWorkspace = () => {
    /* Escape, the back button and the ✕ all land here, and all have to leave the cursor somewhere
       a keyboard reader can carry on from — see `focusRow`. */
    const opener = selected;
    setRecordedPanel(null);
    openLead(null);
    if (opener !== null) focusRow(opener);
  };

  return (
    <div className="mx-auto flex w-full max-w-[100rem] flex-col gap-5">
      {/* Grouped so the summary, the lists' controls and the refresh line take ONE `inert` while
          the narrow sheet covers them. */}
      <div className="flex flex-col gap-5" inert={sheetOpen}>
        <QueueSummary
          newCount={newTotal}
          newActive={facet === "new"}
          onToggleNew={() => {
            toggleFacet("new");
          }}
          recorded={recordedState}
          onRetryRecorded={retryApplied}
          followUpsDue={followUpsDue}
          followUpsActive={facet === "follow_up_due"}
          onToggleFollowUps={() => {
            toggleFacet("follow_up_due");
          }}
          quietApplications={
            applied.kind === "ready" ? (applied.data.counts.quiet ?? 0) : null
          }
          quietHref="#/applied"
          onStart={startSession}
          startLabel={session === null ? "Start applying" : "Continue applying"}
          canStart={navList.length > 0}
        />

        {session === null ? null : (
          <SessionBar
            count={session.count}
            batch={session.batch}
            onSetBatch={(batch) => {
              setSession({ ...session, batch });
            }}
            onEnd={endSession}
          />
        )}

        <LensTabs lens={lens} onLens={setLens} counts={lensCounts} />

        <QueueToolbar
          query={query}
          onQuery={setQuery}
          location={location}
          onLocation={setLocation}
          mode={mode}
          onMode={setMode}
          modes={modeCounts}
          sort={sort}
          onSort={setSort}
          board={board}
          onBoard={setBoard}
          boards={boardCounts}
          minScore={minScore}
          onMinScore={setMinScore}
          hideThin={hideThin !== ""}
          onHideThin={(on) => {
            setHideThin(on ? "1" : "");
          }}
          hideUnverifiable={hideUnverifiable !== ""}
          onHideUnverifiable={(on) => {
            setHideUnverifiable(on ? "1" : "");
          }}
          hideSimilar={hideSimilar !== ""}
          onHideSimilar={(on) => {
            setHideSimilar(on ? "1" : "");
          }}
          views={
            <SavedViews
              current={currentView}
              onApply={applyView}
              onError={(message) => {
                push({ message, tone: "error" });
              }}
            />
          }
          moreActive={moreActive}
          activeFilters={activeFilters}
          onReset={resetFilters}
          selectedCount={markedRows.length}
          onSkipSelected={skipSelected}
          onClearSelection={clearSelection}
        />

        {/* The run filter reads as its own sentence rather than joining the filter list: it comes
            from the URL, not from a control on this page, so the reader needs to be told it is on
            at all before being told how to drop it. */}
        {runFilter === null ? null : (
          <p className="flex flex-wrap items-center gap-x-3 text-sm text-fg-2">
            <span>Showing run {runFilter.toLocaleString()}&rsquo;s jobs only.</span>
            <button
              type="button"
              onClick={() => {
                setRouteParams({ run: null });
              }}
              className="inline-flex min-h-11 items-center rounded-sm px-2 text-sm font-medium text-accent underline underline-offset-4 hover:text-fg"
            >
              Show all runs
            </button>
          </p>
        )}

        {/* Under the controls, because it filters the lists they describe — and only where there
            is a review list to filter. A reason is a lever on the Needs review list. */}
        {data.review.length === 0 || !showReview ? null : (
          <div
            role="group"
            aria-label="Filter by review reason"
            className="flex flex-wrap items-center gap-2"
          >
            <span className="label-micro text-fg-2">Why held</span>
            {reasonCounts.map(({ reason, count }) => (
              <ReasonChip
                key={reason}
                label={REVIEW_REASON_LABELS[reason]}
                count={count}
                active={reasonFacet === reason}
                onToggle={() => {
                  toggleReason(reason);
                }}
              />
            ))}
          </div>
        )}

        {newCount > 0 && stashed !== null ? (
          <p className="flex flex-wrap items-center gap-x-3 text-sm text-fg-2">
            <span className="tabular-nums">{newCount} newly delivered</span>
            <button
              type="button"
              onClick={() => {
                adopt(stashed);
              }}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2 text-sm font-medium text-accent underline underline-offset-4 hover:text-fg"
            >
              <Icon name="refresh" />
              Add them to the list
            </button>
            <span className="text-fg-3">Nothing moves until you ask it to.</span>
          </p>
        ) : null}

        {/* The one sentence that answers "did my filter match anything", scoped to the list it is
            about and announced when it changes (SC 4.1.3). */}
        <p role="status" className="text-sm text-fg-2 tabular-nums">
          Showing {navList.length.toLocaleString()} of {laneTotal.toLocaleString()} in {lensLabel}
        </p>
      </div>

      {sessionEnd === null ? null : (
        <SessionDone
          kind={sessionEnd}
          count={session?.count ?? 0}
          keepGoingLabel={
            sessionEnd === "batch"
              ? navList.length > 0
                ? "Keep going"
                : (otherList?.label ?? null)
              : (otherList?.label ?? null)
          }
          onKeepGoing={() => {
            if (sessionEnd === "batch" && navList.length > 0) {
              if (session !== null) setSession({ ...session, batch: null });
              startSession();
              return;
            }
            if (otherList === null) return;
            if (session !== null) setSession({ ...session, batch: null });
            setLens(otherList.lens);
            setSessionEnd(null);
            if (otherList.first !== undefined) {
              setActiveId(otherList.first.posting_id);
              openAndFocus(otherList.first.posting_id);
            }
          }}
          onFinish={endSession}
        />
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(22rem,30rem)_minmax(0,1fr)] lg:items-start">
        {/* The job lists, and the keys that write with them, behind the sheet at the narrow tier. */}
        <div className="min-w-0" inert={sheetOpen}>
          {bothEmpty ? (
            <p className="rounded-md bg-surface p-6 text-sm text-fg-2 shadow-card">
              There are no jobs yet. A run has to deliver a prepared job before anything appears
              here — this is not a filter result.
            </p>
          ) : (
            <>
              {showExplore ? (
                data.rows.length === 0 ? (
                  <p className="rounded-md bg-surface p-6 text-sm text-fg-2 shadow-card">
                    No jobs to explore right now.
                    {data.review.length === 0
                      ? ""
                      : " Every delivered job is in Needs review — that is how the list was split, not an empty run."}
                  </p>
                ) : (
                  <section aria-labelledby="explore-heading">
                    <h2
                      id="explore-heading"
                      className={lens === "all" ? "mb-2 text-base text-fg" : "sr-only"}
                    >
                      Jobs to explore
                    </h2>
                    {table("explore")}
                  </section>
                )
              ) : null}

              {showReview ? (
                data.review.length === 0 ? (
                  lens === "review" ? (
                    <p className="rounded-md bg-surface p-6 text-sm text-fg-2 shadow-card">
                      Nothing needs review right now.
                    </p>
                  ) : null
                ) : (
                  /*
                   * Contained SEPARATELY from the apply list: the review reasons are exactly the
                   * shape that blanked this page once, and a failure here must not cost the reader
                   * the list they can act on.
                   */
                  <div className={lens === "all" ? "mt-8" : undefined}>
                    <ErrorBoundary
                      title="The review list could not be drawn."
                      hint="The other list is unaffected and still works. These jobs are on disk too, in the queue directory's `_review` folder, so nothing about them is lost."
                      action="Draw the review list again"
                      resetKeys={[data]}
                    >
                      <section aria-labelledby="review-heading">
                        <h2
                          id="review-heading"
                          className={lens === "all" ? "mb-1 text-base text-fg" : "sr-only"}
                        >
                          Needs review
                        </h2>
                        <p className="mb-2 max-w-[72ch] text-sm text-fg-2">
                          {reviewLaneSentence(data.review)} Same split as the{" "}
                          <code className="font-mono text-fg-3">_review</code> folder.
                        </p>
                        {visibleReview.length === 0 ? (
                          <p className="rounded-md bg-surface p-6 text-sm text-fg-2 shadow-card">
                            No job in this list matches. There are{" "}
                            {data.review.length.toLocaleString()} in it.
                          </p>
                        ) : (
                          table("review")
                        )}
                      </section>
                    </ErrorBoundary>
                  </div>
                )
              ) : null}
            </>
          )}
        </div>

        {selected === null ? (
          /* Wide screens keep the workspace's place, so the page does not rearrange itself when a
             job is opened — and the empty workspace says where to start. */
          <aside
            aria-label="Job workspace"
            className="hidden rounded-lg bg-surface p-8 text-center shadow-card lg:sticky lg:top-header lg:flex lg:min-h-80 lg:flex-col lg:items-center lg:justify-center lg:gap-3"
          >
            <h2 className="text-lg text-fg">Pick a job to start</h2>
            <p className="max-w-[44ch] text-sm text-fg-2">
              Open any job to see what to check, the résumé prepared for it, and your application
              answers — all in one place beside the list.
            </p>
            {navList.length === 0 ? null : (
              <button
                type="button"
                onClick={startSession}
                className="mt-2 inline-flex min-h-11 items-center gap-2 rounded-sm bg-primary px-5 text-sm font-semibold text-on-primary transition-colors duration-150 ease-in-out hover:bg-primary-strong"
              >
                Start with the first job
                <Icon name="arrowRight" />
              </button>
            )}
          </aside>
        ) : recordedPanel !== null && recordedPanel.row.posting_id === selected ? (
          <div
            id={PANE_ID}
            tabIndex={-1}
            role={sideBySide ? undefined : "dialog"}
            aria-modal={sideBySide ? undefined : true}
            aria-label="Application recorded"
            className="fixed inset-0 z-40 overflow-y-auto bg-surface lg:sticky lg:inset-auto lg:top-header lg:z-auto lg:rounded-lg lg:shadow-card"
          >
            <RecordedPanel
              company={recordedPanel.row.company}
              title={recordedPanel.row.title}
              hasNext={recordedPanel.nextId !== null}
              onContinue={() => {
                const next = recordedPanel.nextId;
                setRecordedPanel(null);
                if (next === null) {
                  closeWorkspace();
                  return;
                }
                setActiveId(next);
                openAndFocus(next);
              }}
              onUndo={() => {
                const row = recordedPanel.row;
                void unapply(row.posting_id)
                  .then(() => {
                    restore(row.posting_id);
                    setConfirmed((current) => {
                      const next = new Map(current);
                      next.delete(row.posting_id);
                      return next;
                    });
                    setRecordedPanel(null);
                  })
                  .catch((caught: unknown) => {
                    push({
                      message: errorMessage(caught, "Could not withdraw that application."),
                      tone: "error",
                    });
                  });
              }}
              onBack={closeWorkspace}
            />
          </div>
        ) : (
          /*
           * The workspace reads more of the API surface than anything else on the page, so it is
           * the likeliest thing to meet a field the server stopped sending — and it is the easiest
           * to lose safely, because the list beside it is the part being worked through.
           *
           * The recovery action is CLOSE, not redraw: below `lg` this is a sheet, and `sheetOpen` is
           * derived from `selected`, so a failed workspace that stays selected holds `inert` on the
           * list behind it. Clearing `selected` releases the `inert` AND moves `resetKeys`.
           */
          <ErrorBoundary
            title="This job could not be drawn."
            hint="The list beside it is unaffected — close this one and pick another. The job's own résumé and notes are on disk in its queue folder either way."
            action="Close this job"
            onAction={() => {
              /* This click destroys the button that has focus — the boundary unmounts with the
                 workspace — and focus would fall to `<body>`. Back to the row that opened it. */
              const opener = selected;
              openLead(null);
              focusRow(opener);
            }}
            resetKeys={[selected]}
          >
            <DetailPane
              key={selected}
              detail={shownDetail}
              loading={detailLoading}
              error={shownError}
              answers={answers}
              onClose={closeWorkspace}
              onApplied={() => {
                const row = shownDetail?.row;
                if (row) act(row, "applied");
              }}
              onSkip={() => {
                const row = shownDetail?.row;
                if (row) act(row, "skipped");
              }}
              onReport={() => {
                const row = shownDetail?.row;
                if (row) act(row, "reported");
              }}
              onFollowUp={(date) => {
                const row = shownDetail?.row;
                if (row) followUp(row, date);
              }}
              onToast={(message, tone) => {
                push({ message, tone });
              }}
              revealSupported={data.meta?.reveal_supported ?? true}
              onApplyOpened={() => {
                const row = shownDetail?.row;
                if (row) noteApplyOpened(row);
              }}
              {...(shownDetail === null
                ? {}
                : {
                    related: relatedPostings(
                      shownDetail.row,
                      sortedApply.some((row) => row.posting_id === shownDetail.row.posting_id)
                        ? sortedApply
                        : sortedReview,
                    ),
                    onOpenRelated: goTo,
                  })}
              {...(navIndex === -1
                ? {}
                : {
                    position: `${String(navIndex + 1)} of ${navList.length.toLocaleString()}`,
                    ...(previousRow === undefined
                      ? {}
                      : {
                          onPrevious: () => {
                            goTo(previousRow);
                          },
                        }),
                    ...(nextRow === undefined
                      ? {}
                      : {
                          onNext: () => {
                            goTo(nextRow);
                          },
                        }),
                  })}
              {...(shownDetail === null ||
              !visible.some((row) => row.posting_id === shownDetail.row.posting_id)
                ? {}
                : {
                    companyCount: companyRows(shownDetail.row).length,
                    onSelectCompany: () => {
                      selectCompany(shownDetail.row);
                    },
                  })}
            />
          </ErrorBoundary>
        )}
      </div>

      {/*
        * The pipeline's own counts, one fold down. They are how the run decided — useful when
        * something looks wrong, and not what this page is for — so they sit under the work rather
        * than above it. Every cell is still a filter, and still labelled with what it counts.
        */}
      <details className="group rounded-md bg-surface shadow-card" inert={sheetOpen}>
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-md px-4 text-sm font-medium text-fg-2 hover:text-fg [&::-webkit-details-marker]:hidden">
          Pipeline counts
          <Icon name="chevronDown" className="transition-transform group-open:rotate-180" />
        </summary>
        <div className="px-1 pb-2">
          <StatusBand
            counts={bandCounts}
            newSince={newTotal}
            reviewNote={`${reviewLaneSentence(data.review)} Click to show only this list.`}
            activeFacet={facet === null && lens === "review" ? "review" : facet}
            onToggleFacet={toggleFacet}
          />
        </div>
      </details>

      {/* Only while the job is still on the page: one decided some other way meanwhile, or drained
          by a refresh, has nothing left to ask about. */}
      {returnPrompt === null ||
      removed.has(returnPrompt.posting_id) ||
      ![...data.rows, ...data.review].some((row) => row.posting_id === returnPrompt.posting_id) ? null : (
        <ApplyReturnPrompt
          row={returnPrompt}
          onApplied={() => {
            act(returnPrompt, "applied");
          }}
          onDismiss={() => {
            const postingId = returnPrompt.posting_id;
            setReturnPrompt(null);
            // Below `lg` the open job is a sheet over an inert list, where a row cannot take
            // focus; the sheet itself is where the reader was.
            if (sheetOpen) document.getElementById(PANE_ID)?.focus();
            else focusRow(postingId);
          }}
        />
      )}
    </div>
  );
}
