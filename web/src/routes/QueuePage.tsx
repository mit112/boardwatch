import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getAnswers,
  getDetail,
  getQueue,
  markApplied,
  markSkipped,
  report,
  unapply,
  unreport,
  unskip,
} from "../api/client";
import type {
  Answers,
  QueueCounts,
  QueueDetail,
  QueueResponse,
  QueueRow,
  ReviewReason,
} from "../api/types";
import { TOKEN_EVENT } from "../api/token";
import { openApplyUrl } from "../components/ApplyLink";
import { DetailPane, SIDE_BY_SIDE } from "../components/DetailPane";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { QueueTable } from "../components/QueueTable";
import { FILTER_INPUT_ID, QueueToolbar } from "../components/QueueToolbar";
import { StatusBand } from "../components/StatusBand";
import type { QueueFacet } from "../components/StatusBand";
import { useMediaQuery } from "../hooks/useMediaQuery";
import type { ToastRequest } from "../hooks/useToasts";
import {
  REVIEW_REASON_LABELS,
  countReviewReasons,
  reviewBreakdown,
  reviewLaneSentence,
} from "../lib/reviewReasons";
import { matchesQuery, sortRows } from "../lib/sort";
import type { SortKey, SortState } from "../lib/sort";

const COLLAPSE_MS = 200;
const POLL_MS = 30_000;

/*
 * Working state kept across a tab switch and a reload, in `sessionStorage` and never in
 * `localStorage`: this is what the reader is doing RIGHT NOW, so it should die with the tab rather
 * than greet them a week later with a filter they have forgotten setting.
 *
 * Every access is wrapped, exactly as `api/token.ts` wraps its own: storage throws outright when
 * it is disabled or the quota is gone, and a viewer that cannot remember a filter must still be a
 * viewer that runs.
 */
const REVIEW_OPEN_KEY = "boardwatch.review-open";

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

/** A stored flag, or `null` when nothing is stored — which is NOT the same as `false`, because a
 *  default only applies while the reader has expressed no preference. */
function readStoredFlag(key: string): boolean | null {
  const stored = readSession(key);
  return stored === "true" ? true : stored === "false" ? false : null;
}

type Removal = "applied" | "skipped" | "reported";

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

/*
 * One review reason, as a toggle. The pressed treatment is the band's own (`Metric` in
 * `StatusBand`): a fill plus an inset accent bar plus brighter text — three channels, never colour
 * alone (SC 1.4.1) — and the `aria-label` starts with the visible label and count so Label in Name
 * holds (SC 2.5.3) before it names the action `aria-pressed` cannot convey.
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
          ? "bg-surface-3 text-fg shadow-[inset_0_-2px_0_0_var(--color-accent)]"
          : "text-fg-2 hover:bg-surface-2"
      }`}
    >
      <span>{label}</span>
      <span className="tabular-nums text-fg-3">{count.toLocaleString()}</span>
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
   * Collapsed by default while there is an apply queue to work down, and that IS the feature: the
   * top of the page has to be the list you can work through without re-deriving anything. Open is
   * one click and the count is always visible, so the lane is never hidden — only folded.
   *
   * With an EMPTY apply lane the default flips, because then the fold hides the only work on the
   * page: the reader met a placeholder above a closed section and had to click "show" every day
   * the engine version moved. A stored preference outranks both — the reader who folded it did so
   * on purpose.
   */
  const [reviewOpenPref, setReviewOpenPref] = useState<boolean | null>(() =>
    readStoredFlag(REVIEW_OPEN_KEY),
  );
  const setReviewOpen = useCallback((next: boolean) => {
    setReviewOpenPref(next);
    writeSession(REVIEW_OPEN_KEY, String(next));
  }, []);

  const [query, setQuery] = useState("");
  const [minScore, setMinScore] = useState("");
  /*
   * The verdict facet from the status band, shared across BOTH lanes exactly like `query` and
   * `minScore` — it expresses "what am I looking for", which spans the apply queue and the review
   * list. `null` is "all". Applied AFTER `filtered`/`filteredReview` below, never inside them, so
   * the band's own counts stay put and the reader can switch straight from one facet to another
   * instead of the cell they need to click dropping to zero.
   */
  const [facet, setFacet] = useState<QueueFacet | null>(null);
  /*
   * The REVIEW-REASON facet, alongside the verdict one and composed with it. Every review row
   * already carried its reason as a chip and nothing could filter by one, so on a 149-lead lane
   * the chips were nine repeating labels to scan past rather than a control. Applied after
   * `filteredReview` for the same reason the verdict facet is: the chip counts must not collapse
   * to the current selection, or the chip the reader wants next reads zero.
   */
  const [reasonFacet, setReasonFacet] = useState<ReviewReason | null>(null);
  const [sort, setSort] = useState<SortState>({ key: "rank", direction: "asc" });
  /*
   * The review lane sorts INDEPENDENTLY. Sharing one `sort` meant clicking a header in the review
   * table silently re-ordered the apply list above it — a list the reader is working top-down and
   * is not currently looking at, with no visible cue, because `#` prints the server rank rather
   * than the display position. Query and score floor are still shared, deliberately: those
   * express "what am I looking for", which spans both lanes, while sort expresses "how do I want
   * THIS list arranged".
   */
  const [reviewSort, setReviewSort] = useState<SortState>({ key: "rank", direction: "asc" });

  const [selected, setSelected] = useState<number | null>(null);
  /*
   * The keyboard CURSOR, which is not the selection: ↓/↑ walk the list without opening a pane and
   * without fetching a detail per row, and Enter opens the one you stopped on. One cursor for both
   * tables, because a posting id is unique across them and arrow keys never leave the table that
   * has focus anyway.
   */
  const [activeId, setActiveId] = useState<number | null>(null);
  const [detail, setDetail] = useState<QueueDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answers | null>(null);

  const reviewOpen =
    reviewOpenPref ?? (data !== null && data.rows.length === 0 && data.review.length > 0);

  const knownIds = useRef<Set<number>>(new Set());

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
    if (selected === null) return;
    let live = true;
    void getDetail(selected)
      .then((response) => {
        if (live) setDetail(response);
      })
      .catch((caught: unknown) => {
        if (live) setDetailError(errorMessage(caught, "Could not load this lead."));
      });
    return () => {
      live = false;
    };
  }, [selected]);

  useEffect(() => {
    if (selected === null || answers !== null) return;
    void getAnswers()
      .then(setAnswers)
      .catch(() => {
        /* The panel shows its own loading line; a missing answers.yaml is not a page failure. */
      });
  }, [selected, answers]);

  const detailLoading = selected !== null && detail === null && detailError === null;

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

  const filtered = useMemo(() => {
    const floor = minScore.trim() === "" ? null : Number(minScore);
    return (data?.rows ?? []).filter((row) => {
      if (removed.has(row.posting_id)) return false;
      if (!matchesQuery(row, query.trim())) return false;
      // A null score is not below a floor, it is unmeasured — so a floor excludes it rather than
      // silently treating "unknown" as zero.
      if (floor !== null && !Number.isNaN(floor) && (row.score === null || row.score < floor)) {
        return false;
      }
      return true;
    });
  }, [data, removed, query, minScore]);

  const visible = useMemo(() => {
    // `review` selects a LANE, not a verdict: the apply queue is hidden entirely for it, so its
    // list is empty. The verdict facets narrow it; `null` shows all.
    const base =
      facet === "review"
        ? []
        : facet === null
          ? filtered
          : filtered.filter((row) => row.verdict === facet);
    return sortRows(base, sort, rankOf);
  }, [filtered, facet, sort, rankOf]);

  /*
   * The toolbar's search and score floor apply to BOTH lanes. A filter that silently skipped the
   * review list would make it look empty for a query that matches, which is the worst version of
   * this feature: a reader concludes there is nothing to review when there is.
   */
  const filteredReview = useMemo(() => {
    const floor = minScore.trim() === "" ? null : Number(minScore);
    return (data?.review ?? []).filter((row) => {
      if (removed.has(row.posting_id)) return false;
      if (!matchesQuery(row, query.trim())) return false;
      if (floor !== null && !Number.isNaN(floor) && (row.score === null || row.score < floor)) {
        return false;
      }
      return true;
    });
  }, [data, removed, query, minScore]);

  const visibleReview = useMemo(() => {
    // A verdict facet reaches the review lane too: a review lead can be `eligible` — held only for
    // its location — so filtering "eligible" while skipping this list is the documented "make the
    // review list look empty for a matching filter" failure. `review` shows the whole lane.
    const byVerdict =
      facet === null || facet === "review"
        ? filteredReview
        : filteredReview.filter((row) => row.verdict === facet);
    const base =
      reasonFacet === null
        ? byVerdict
        : byVerdict.filter((row) => row.review_reason === reasonFacet);
    return sortRows(base, reviewSort, reviewRankOf);
  }, [filteredReview, facet, reasonFacet, reviewSort, reviewRankOf]);

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
      // Passed through, NOT recomputed: an ineligible lead is never in `rows`, so no
      // client-side filter can see one. Recomputing it here would always yield 0 and quietly
      // contradict the server.
      ineligible: data?.counts.ineligible ?? 0,
      // Passed through for the same reason as `ineligible`: a closed posting is drained on disk,
      // so it is never a row and no client-side filter can see one.
      closed: data?.counts.closed ?? 0,
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

  const act = useCallback(
    (row: QueueRow, kind: Removal) => {
      /*
       * Where the cursor lands once this row leaves. Without it, marking a lead by keyboard
       * destroyed the focused element and focus fell back to `<body>` — so triaging ten leads
       * meant ten trips back through Tab. The neighbour BELOW, or above at the end of a list.
       */
      let successor: QueueRow | undefined;
      for (const list of [visible, visibleReview]) {
        const index = list.findIndex((candidate) => candidate.posting_id === row.posting_id);
        if (index !== -1) {
          successor = list[index + 1] ?? list[index - 1];
          break;
        }
      }

      // Optimistic: the row collapses to zero height, then leaves the list.
      setCollapsing((current) => new Set(current).add(row.posting_id));
      window.setTimeout(() => {
        setRemoved((current) => new Map(current).set(row.posting_id, kind));
        setCollapsing((current) => {
          const next = new Set(current);
          next.delete(row.posting_id);
          return next;
        });
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
      if (selected === row.posting_id) setSelected(null);

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
          push({
            /*
             * Says what the button DOES, now that there is an inverse route to call: the undo
             * withdraws the application record and only then puts the row back — the same
             * write-then-restore order as skip and report, so a failed withdrawal leaves the row
             * out rather than showing a lead the store still counts as applied.
             */
            message: `Marked applied: ${row.company} — ${row.title}. Undo withdraws it and puts the row back.`,
            undo: () => {
              void unapply(row.posting_id)
                .then(() => {
                  restore(row.posting_id);
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
          restore(row.posting_id);
          push({
            message: errorMessage(caught, "The write failed and the row was restored."),
            tone: "error",
          });
        });
    },
    [push, restore, selected, visible, visibleReview],
  );

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
      }
    },
    [push],
  );

  const nextSort = (current: SortState, key: SortKey): SortState =>
    current.key === key
      ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
      : { key, direction: key === "rank" || key === "age" ? "asc" : "desc" };

  const onSort = useCallback((key: SortKey) => {
    setSort((current) => nextSort(current, key));
  }, []);

  const onReviewSort = useCallback((key: SortKey) => {
    setReviewSort((current) => nextSort(current, key));
  }, []);

  /*
   * Counted over the WHOLE lane, never over `visibleReview`: these counts are the menu, and a menu
   * that re-counts itself against its own selection offers one entry with the number you already
   * chose and zeroes beside everything else.
   */
  const reasonCounts = useMemo(() => countReviewReasons(data?.review ?? []), [data]);

  const toggleReason = useCallback(
    (next: ReviewReason) => {
      const clearing = reasonFacet === next;
      setReasonFacet(clearing ? null : next);
      // Same reason `review` opens the lane: with the apply queue off the page, a folded review
      // section would leave a filter whose entire result is invisible.
      if (!clearing) setReviewOpen(true);
    },
    [reasonFacet, setReviewOpen],
  );

  // Clicking the active facet's band cell again clears it — one control, both directions.
  const toggleFacet = useCallback(
    (next: QueueFacet) => {
      const clearing = facet === next;
      setFacet(clearing ? null : next);
      /*
       * Selecting the `review` lane opens its section: it is collapsed by default, and with the
       * apply queue hidden a collapsed one would leave the page showing only a header. Done here on
       * the click — not in an effect keyed on `facet`, because a setState synchronised into an
       * effect body is a cascading render the lint rule rejects, and the event already knows the
       * answer. The reader can still collapse it afterward.
       */
      if (!clearing && next === "review") setReviewOpen(true);
    },
    [facet, setReviewOpen],
  );

  /*
   * The apply lane is off the page entirely — the `review` facet asks for that lane alone. The
   * band's readout then describes the review lane, because describing a hidden list is describing
   * nothing.
   */
  const laneOnly = facet === "review" || reasonFacet !== null;

  /*
   * The lane's copy, GENERATED from the lane. Both sentences below used to name two of the nine
   * reasons by hand and described none of the 149 leads on the measured day, which is what copy
   * that enumerates a closed catalog eventually does.
   */
  const reviewSentence = reviewLaneSentence(data?.review ?? []);
  const reviewNote = (() => {
    const breakdown = reviewBreakdown(data?.review ?? []);
    const lead = "Held for a look, not blindly appliable";
    return `${breakdown === "" ? `${lead}.` : `${lead} — ${breakdown}.`} Click to show only this lane.`;
  })();

  // The empty grid must name the lever that emptied it. With a facet on, the two default
  // sentences point at the text box and the score floor — neither of which is what is filtering.
  const emptyHint =
    facet === null
      ? "Clear the text box or lower the minimum score."
      : `Clear the text box, lower the minimum score, or turn off the ${facet}-only filter.`;

  /* What the reader turned on, in words, so "Show all" is obviously the way back out. */
  const activeFilters = [
    facet === null ? null : facet === "review" ? "the review lane only" : `${facet} only`,
    reasonFacet === null ? null : `${REVIEW_REASON_LABELS[reasonFacet]} only`,
  ].filter((entry): entry is string => entry !== null);

  if (loadError !== null) {
    /*
     * `role="alert"`, and a second line that says what to DO. This state renders as the whole page
     * and the first line is whatever the transport said — `404 from /api/queue` on its own is a
     * status code, not an error a reader can act on.
     */
    return (
      <div role="alert" className="rounded-md border border-fg-2 bg-surface p-4">
        <p className="text-sm text-fg">{loadError}</p>
        <p className="mt-1 text-sm text-fg-2">
          The page reads the store the CLI maintains. Reload once, and if it persists re-open the
          URL <code className="text-fg-3">boardwatch web</code> printed — that URL carries the
          session token.
        </p>
      </div>
    );
  }

  if (data === null) {
    return (
      <p role="status" className="p-4 text-sm text-fg-2">
        Loading the queue…
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Grouped, and carrying its own `gap-4` so the spacing is unchanged, only so that the band,
          the toolbar and the refresh line take ONE `inert` while the sheet covers them. */}
      <div className="flex flex-col gap-4" inert={sheetOpen}>
        <StatusBand
          counts={bandCounts}
          /*
           * What is VISIBLE ON THE PAGE, which is both lanes whenever both are drawn. Counting the
           * apply lane alone printed "Showing 0 of 0" above 149 listed review leads on the day the
           * apply lane emptied — the one sentence that answers "did my filter match anything"
           * contradicting the list directly under it. `laneOnly` is the case where the apply queue
           * is genuinely off the page, so its zero belongs in neither figure.
           */
          reviewNote={reviewNote}
          showing={laneOnly ? visibleReview.length : visible.length + visibleReview.length}
          total={laneOnly ? data.review.length : data.rows.length + data.review.length}
          activeFacet={facet}
          onToggleFacet={toggleFacet}
        />
        {/* Under the band, because it filters the same lists the band's cells do — and rendered
            only when there is a lane to filter, so a page with no review leads has no dead row. */}
        {data.review.length === 0 ? null : (
          <div
            role="group"
            aria-label="Filter by review reason"
            className="flex flex-wrap items-center gap-2"
          >
            <span className="label-micro text-fg-3">reason</span>
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

        <QueueToolbar
          query={query}
          onQuery={setQuery}
          minScore={minScore}
          onMinScore={setMinScore}
        />

        {/* The active facet stated in words next to a plain clear, so it is obvious a filter is on
            and how to drop it — the pressed band cell shows which, this shows that. */}
        {activeFilters.length === 0 ? null : (
          <p className="flex items-center gap-3 text-sm text-fg-2">
            <span>Showing {activeFilters.join(", ")}.</span>
            <button
              type="button"
              onClick={() => {
                setFacet(null);
                setReasonFacet(null);
              }}
              className="min-h-11 rounded-sm border border-control px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:border-fg-2 hover:text-fg"
            >
              Show all
            </button>
          </p>
        )}

        {newCount > 0 && stashed !== null ? (
          <p className="flex items-center gap-3 text-sm text-fg-2">
            <span className="tabular-nums">{newCount} new</span>
            <button
              type="button"
              onClick={() => {
                adopt(stashed);
              }}
              className="min-h-11 rounded-sm border border-control px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:border-fg-2 hover:text-fg"
            >
              refresh
            </button>
            <span className="text-fg-3">Nothing moves until you ask it to.</span>
          </p>
        ) : null}
      </div>

      <div
        className={
          selected === null
            ? ""
            : "grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(26rem,32rem)] lg:items-start"
        }
      >
        {/* The triage grid, and the row `a`/`s` writes with it, behind the sheet at the narrow
            tier. */}
        <div className="min-w-0" inert={sheetOpen}>
          {/*
            * BOTH lanes, because `rows` is now the apply lane alone. With every delivered lead in
            * review this said "the queue is empty … this is not a filter result" directly above a
            * populated review section — and both halves were false: leads WERE delivered, and the
            * reason they are not above is the lane split.
            */}
          {/* The `review` facet hides the apply queue entirely — it is a request to see that lane
              alone. Its own empty/populated states below are unaffected. */}
          {laneOnly ? null : data.rows.length === 0 && data.review.length === 0 ? (
            <p className="rounded-md border border-divider bg-surface p-6 text-sm text-fg-2">
              The queue is empty. A run has to deliver a tailored lead before anything appears
              here — this is not a filter result.
            </p>
          ) : data.rows.length === 0 ? (
            <p className="rounded-md border border-divider bg-surface p-6 text-sm text-fg-2">
              Nothing is blindly appliable right now. Every delivered lead is in the review
              section below — that is a lane split, not an empty run.
            </p>
          ) : (
            <QueueTable
              label="Queue"
              rows={visible}
              rankOf={rankOf}
              sort={sort}
              onSort={onSort}
              emptyHint={emptyHint}
              selectedId={selected}
              activeId={activeId}
              onActivate={setActiveId}
              collapsing={collapsing}
              onOpenApply={openApply}
              onSelect={(row) => {
                // Re-clicking the open row must not clear `detail`. `setSelected` bails out on
                // an unchanged value, so the effect keyed on it never re-fires and the pane
                // would sit on its loading state for good.
                if (row.posting_id === selected) return;
                setSelected(row.posting_id);
                setDetail(null);
                setDetailError(null);
              }}
              onApplied={(row) => {
                act(row, "applied");
              }}
              onSkip={(row) => {
                act(row, "skipped");
              }}
              onReport={(row) => {
                act(row, "reported");
              }}
            />
          )}

          {data.review.length === 0 ? null : (
            /*
             * The lane is contained SEPARATELY from the apply queue above it, and that asymmetry
             * is the point: `ReviewReasonBadge` renders a field only these rows carry, which is
             * precisely the shape that blanked this page once. A failure here must not cost the
             * reader the list they can actually act on. The whole `<section>` is inside, header
             * included, so `aria-controls="review-list"` can never be left pointing at an element
             * the fallback replaced. `mt-12` moved out to the wrapper so the card inherits it.
             */
            <div className={laneOnly ? undefined : "mt-12"}>
              <ErrorBoundary
                title="The review lane could not be drawn."
                hint="The queue above is unaffected and still works. These leads are on disk too, in the queue directory's `_review` folder, so nothing about them is lost."
                action="Draw the review lane again"
                resetKeys={[data]}
              >
                <section aria-labelledby="review-heading">
                  {/* No top rule when the review lane stands alone — the `review` facet or a
                      reason facet: a rule at the top of the content has nothing to divide it
                      from. */}
                  <header
                    className={`flex flex-wrap items-baseline gap-x-4 gap-y-2 ${laneOnly ? "" : "border-t border-divider pt-8"}`}
                  >
                    <h2
                      id="review-heading"
                      className="font-display text-base tracking-[0.12em] text-fg uppercase"
                    >
                      Review
                    </h2>
                    <span className="text-sm text-fg-2 tabular-nums">
                      {visibleReview.length.toLocaleString()}
                      {visibleReview.length === data.review.length
                        ? ""
                        : ` of ${data.review.length.toLocaleString()}`}
                    </span>
                    <button
                      type="button"
                      aria-expanded={reviewOpen}
                      aria-controls="review-list"
                      onClick={() => {
                        setReviewOpen(!reviewOpen);
                      }}
                      className="min-h-11 rounded-sm px-2 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:bg-surface hover:text-fg"
                    >
                      {reviewOpen ? "hide" : "show"}
                    </button>
                    {/*
                      * Says what the lane IS, not what is wrong with it. These leads were not
                      * rejected — the gate declined to vouch for them, which is a different claim,
                      * and calling them "off target" here would assert the decision it declined to
                      * make. The folder path is named because the two must stay legible as the same
                      * split; if they ever disagree, the folder tree wins.
                      */}
                    <p className="w-full text-sm text-fg-2">
                      Open these before applying. {reviewSentence} Same split as the{" "}
                      <code className="text-fg-3">_review</code> folder.
                    </p>
                  </header>

                  {/*
                    * The container stays MOUNTED and is emptied instead of being unmounted, so
                    * `aria-controls="review-list"` resolves in the collapsed state — which is the
                    * default, and therefore the state a screen reader meets first. Unmounting it left
                    * a dangling IDREF that AT drops silently. The ROWS are still not rendered while
                    * collapsed, so nothing is paid for the leads themselves.
                    */}
                  <div id="review-list" className={reviewOpen ? "mt-4" : undefined}>
                    {!reviewOpen ? null : visibleReview.length === 0 ? (
                        <p className="rounded-md border border-divider bg-surface p-6 text-sm text-fg-2">
                          No review lead matches the current filter. There are{" "}
                          {data.review.length.toLocaleString()} in the lane.
                        </p>
                    ) : (
                        <QueueTable
                          label="Review"
                          rows={visibleReview}
                          rankOf={reviewRankOf}
                          sort={reviewSort}
                          onSort={onReviewSort}
                          selectedId={selected}
                          activeId={activeId}
                          onActivate={setActiveId}
                          collapsing={collapsing}
                          onOpenApply={openApply}
                          onSelect={(row) => {
                            if (row.posting_id === selected) return;
                            setSelected(row.posting_id);
                            setDetail(null);
                            setDetailError(null);
                          }}
                          onApplied={(row) => {
                            act(row, "applied");
                          }}
                          onSkip={(row) => {
                            act(row, "skipped");
                          }}
                          onReport={(row) => {
                            act(row, "reported");
                          }}
                      />
                    )}
                  </div>
                </section>
              </ErrorBoundary>
            </div>
          )}
        </div>

        {selected === null ? null : (
          /*
           * The pane reads more of the API surface than anything else on the page, so it is the
           * likeliest thing to meet a field the server stopped sending — and it is the easiest to
           * lose safely, because the queue beside it is the part being worked through.
           *
           * The recovery action is CLOSE, not redraw, and that is not a style choice: below `lg`
           * this pane is a sheet, and `sheetOpen` is derived from `selected`, so a failed pane
           * that stays selected holds `inert` on the list behind it. Redrawing would hand back a
           * card with a frozen queue behind it. Clearing `selected` releases the `inert` AND moves
           * `resetKeys`, so the boundary is reset by the same click.
           */
          <ErrorBoundary
            title="This lead could not be drawn."
            hint="The queue beside it is unaffected — close this one and pick another. The lead's own résumé and notes are on disk in its queue folder either way."
            action="Close this lead"
            onAction={() => {
              /*
               * Where the cursor lands, for the same reason the mark-applied path does it: this
               * click destroys the button that has focus — the boundary unmounts with the pane —
               * and focus would fall to `<body>`, stranding a keyboard reader at the top of the
               * document. Back to the row that opened the pane, which is reachable again the
               * moment `selected` is null and the sheet's `inert` lifts. `DetailPane`'s own
               * restore cannot cover this: at the narrow tier it already fired against an inert
               * row, and at `lg` it never registers one.
               */
              const opener = selected;
              setSelected(null);
              window.setTimeout(() => {
                const row = document.querySelector<HTMLElement>(
                  `[data-row-id="${String(opener)}"]`,
                );
                if (row === null) document.getElementById(FILTER_INPUT_ID)?.focus();
                else row.focus();
              }, 0);
            }}
            resetKeys={[selected]}
          >
            <DetailPane
              key={selected}
              detail={detail}
              loading={detailLoading}
              error={detailError}
              answers={answers}
              onClose={() => {
                setSelected(null);
              }}
              onApplied={() => {
                const row = detail?.row;
                if (row) act(row, "applied");
              }}
              onSkip={() => {
                const row = detail?.row;
                if (row) act(row, "skipped");
              }}
              onReport={() => {
                const row = detail?.row;
                if (row) act(row, "reported");
              }}
              onToast={(message, tone) => {
                push({ message, tone });
              }}
            />
          </ErrorBoundary>
        )}
      </div>
    </div>
  );
}
