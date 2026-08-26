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
import { DetailPane } from "../components/DetailPane";
import { QueueTable } from "../components/QueueTable";
import { QueueToolbar } from "../components/QueueToolbar";
import { StatusBand } from "../components/StatusBand";
import type { ToastRequest } from "../hooks/useToasts";
import { matchesQuery, sortRows } from "../lib/sort";
import type { SortKey, SortState } from "../lib/sort";

const COLLAPSE_MS = 200;
const POLL_MS = 30_000;

type Removal = "applied" | "skipped";

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

export function QueuePage({ push }: { push: (request: ToastRequest) => void }) {
  const [data, setData] = useState<QueueResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [removed, setRemoved] = useState<Map<number, Removal>>(new Map());
  const [collapsing, setCollapsing] = useState<Set<number>>(new Set());
  const [stashed, setStashed] = useState<QueueResponse | null>(null);
  const [newCount, setNewCount] = useState(0);

  const [query, setQuery] = useState("");
  const [minScore, setMinScore] = useState("");
  const [sort, setSort] = useState<SortState>({ key: "rank", direction: "asc" });

  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<QueueDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answers | null>(null);

  const knownIds = useRef<Set<number>>(new Set());

  const adopt = useCallback((response: QueueResponse) => {
    setData(response);
    knownIds.current = new Set(response.rows.map((row) => row.posting_id));
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
          const fresh = response.rows.filter((row) => !knownIds.current.has(row.posting_id));
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

  const rankByPosting = useMemo(() => {
    const map = new Map<number, number>();
    (data?.rows ?? []).forEach((row, index) => {
      map.set(row.posting_id, index + 1);
    });
    return map;
  }, [data]);

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
      applied_ever: (data?.counts.applied_ever ?? 0) + appliedDelta,
      skipped: (data?.counts.skipped ?? 0) + skippedDelta,
      // Run-scoped facts, not filter-scoped: they come from the server unchanged.
      delivered_last_run: data?.counts.delivered_last_run ?? 0,
      last_run_finished: data?.counts.last_run_finished ?? null,
    };
  }, [filtered, removed, data]);

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
      // Optimistic: the row collapses to zero height, then leaves the list.
      setCollapsing((current) => new Set(current).add(row.posting_id));
      window.setTimeout(() => {
        setRemoved((current) => new Map(current).set(row.posting_id, kind));
        setCollapsing((current) => {
          const next = new Set(current);
          next.delete(row.posting_id);
          return next;
        });
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
    [push, restore, selected],
  );

  const onSort = useCallback((key: SortKey) => {
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: key === "rank" || key === "age" ? "asc" : "desc" },
    );
  }, []);

  if (loadError !== null) {
    return (
      <p className="rounded border border-fg-2 bg-surface p-4 text-sm text-fg">{loadError}</p>
    );
  }

  if (data === null) {
    return (
      <p className="p-4 text-sm text-fg-2">
        Loading the queue — a first sync holds roughly 540 delivered, unapplied leads.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
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
            className="min-h-11 rounded border border-control px-3 text-sm text-fg-2 transition-colors duration-150 ease-in-out hover:border-fg-2 hover:text-fg"
          >
            refresh
          </button>
          <span className="text-fg-3">Nothing moves until you ask it to.</span>
        </p>
      ) : null}

      <div
        className={
          selected === null
            ? ""
            : "grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(26rem,32rem)] lg:items-start"
        }
      >
        <div className="min-w-0">
          {data.rows.length === 0 ? (
            <p className="rounded border border-divider bg-surface p-6 text-sm text-fg-2">
              The queue is empty. A run has to deliver a tailored lead before anything appears
              here — this is not a filter result.
            </p>
          ) : (
            <QueueTable
              rows={visible}
              rankOf={rankOf}
              sort={sort}
              onSort={onSort}
              selectedId={selected}
              collapsing={collapsing}
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
