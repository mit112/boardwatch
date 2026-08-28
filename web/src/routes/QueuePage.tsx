import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getAnswers,
  getDetail,
  getQueue,
  markApplied,
  markSkipped,
  unskip,
} from "../api/client";
import type { Answers, QueueCounts, QueueDetail, QueueResponse, QueueRow } from "../api/types";
import { openApplyUrl } from "../components/ApplyLink";
import { DetailPane, SIDE_BY_SIDE } from "../components/DetailPane";
import { QueueTable } from "../components/QueueTable";
import { FILTER_INPUT_ID, QueueToolbar } from "../components/QueueToolbar";
import { StatusBand } from "../components/StatusBand";
import { useMediaQuery } from "../hooks/useMediaQuery";
import type { ToastRequest } from "../hooks/useToasts";
import { matchesQuery, sortRows } from "../lib/sort";
import type { SortKey, SortState } from "../lib/sort";

const COLLAPSE_MS = 200;
const POLL_MS = 30_000;

type Removal = "applied" | "skipped";

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
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
   * Collapsed by default, and that IS the feature: the top of the page has to be the list you can
   * work through without re-deriving anything. Open is one click and the count is always visible,
   * so the lane is never hidden — only folded.
   */
  const [reviewOpen, setReviewOpen] = useState(false);

  const [query, setQuery] = useState("");
  const [minScore, setMinScore] = useState("");
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

  const knownIds = useRef<Set<number>>(new Set());

  const adopt = useCallback((response: QueueResponse) => {
    setData(response);
    // BOTH lanes. A lead that moves between them on a re-evaluation is not new, and counting it
    // as new would put a permanent "N new" nag on the page that refreshing never clears.
    knownIds.current = new Set(
      [...response.rows, ...response.review].map((row) => row.posting_id),
    );
    setStashed(null);
    setNewCount(0);
    setRemoved(new Map());
  }, []);

  useEffect(() => {
    let live = true;
    void getQueue()
      .then((response) => {
        if (live) adopt(response);
      })
      .catch((caught: unknown) => {
        if (live) setLoadError(errorMessage(caught, "Could not load the queue."));
      });
    return () => {
      live = false;
    };
  }, [adopt]);

  /*
   * A background refresh NEVER re-orders the list or moves a row under the pointer. It stashes the
   * newer response and surfaces a quiet count; adopting it is the reader's decision.
   */
  useEffect(() => {
    const timer = window.setInterval(() => {
      void getQueue()
        .then((response) => {
          const fresh = [...response.rows, ...response.review].filter(
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

  const visible = useMemo(() => sortRows(filtered, sort, rankOf), [filtered, sort, rankOf]);

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

  const visibleReview = useMemo(
    () => sortRows(filteredReview, reviewSort, reviewRankOf),
    [filteredReview, reviewSort, reviewRankOf],
  );

  const bandCounts: QueueCounts = useMemo(() => {
    let appliedDelta = 0;
    let skippedDelta = 0;
    for (const kind of removed.values()) {
      if (kind === "applied") appliedDelta += 1;
      else skippedDelta += 1;
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
      // Recomputed against the active filter, unlike `ineligible`: a review lead IS in the
      // payload, so a client-side filter can see one and the cell must agree with the list the
      // reader is looking at.
      review: filteredReview.length,
      applied_ever: (data?.counts.applied_ever ?? 0) + appliedDelta,
      skipped: (data?.counts.skipped ?? 0) + skippedDelta,
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

      const call = kind === "applied" ? markApplied : markSkipped;
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
          push({
            /*
             * The contract has no un-apply route, so this Undo puts the ROW back and says so. It
             * does not claim to reverse the application record — a false claim there would be
             * worse than no undo at all.
             */
            message: `Marked applied: ${row.company} — ${row.title}. Undo puts the row back; the application record stays until it is withdrawn.`,
            undo: () => {
              restore(row.posting_id);
            },
            undoLabel: "Put the row back",
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
        <StatusBand counts={bandCounts} showing={visible.length} total={data.rows.length} />
        <QueueToolbar
          query={query}
          onQuery={setQuery}
          minScore={minScore}
          onMinScore={setMinScore}
        />

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
          {data.rows.length === 0 && data.review.length === 0 ? (
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
            />
          )}

          {data.review.length === 0 ? null : (
            <section aria-labelledby="review-heading" className="mt-12">
              <header className="flex flex-wrap items-baseline gap-x-4 gap-y-2 border-t border-divider pt-8">
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
                    setReviewOpen((open) => !open);
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
                  Open these before applying. Each one is either outside the US, or carries a
                  title the role gate will not positively call software — so it is not
                  blindly appliable. Same split as the{" "}
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
                  />
                )}
              </div>
            </section>
          )}
        </div>

        {selected === null ? null : (
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
            onToast={(message, tone) => {
              push({ message, tone });
            }}
          />
        )}
      </div>
    </div>
  );
}
