import { useEffect, useState } from "react";

import { getVersion } from "../api/client";

/*
 * Says when the viewer has fallen behind what is on disk — the skew `boardwatch web` creates by
 * construction (D-360): it serves the bundle from DISK per request, while its API is the Python it
 * imported at STARTUP. After a merge or a pull either half can be stale, and nothing on the page
 * said so; a missing field then read as "no data" instead of "restart me".
 *
 * Three different remedies, so three different sentences:
 *   - the API's code changed under it: only restarting `boardwatch web` fixes that;
 *   - a newer page is on disk than the one this tab loaded: a reload fixes that;
 *   - the store is behind the API's code: the viewer never migrates it (D-279), so only the next
 *     run, or any command that opens the store read-write, fixes that. Every page that reads the
 *     store is answering 503 meanwhile, and this is where the owner is told why.
 *
 * Checked on load and then every minute. A failed check — an older server with no
 * `/api/version`, a restart in progress — is silence, never an error: this is advice, and the
 * pages around it already say when the API itself is down.
 */

const CHECK_MS = 60_000;

/** The entry script this tab loaded, by the same name the server reads off its index document.
 *  None under the dev server, whose module scripts are not in `/assets/`. */
function loadedBundle(): string | null {
  const src = document
    .querySelector<HTMLScriptElement>('script[type="module"][src^="/assets/"]')
    ?.getAttribute("src");
  return src == null ? null : src.slice("/assets/".length);
}

export function StaleViewerBanner() {
  const [codeChanged, setCodeChanged] = useState(false);
  const [newerPage, setNewerPage] = useState(false);
  const [storeBehind, setStoreBehind] = useState(false);

  useEffect(() => {
    const loaded = loadedBundle();
    let live = true;
    const check = () => {
      // Started inside the chain, so a throw on the way to the request lands in the same `.catch`
      // as a refused one: either way, nothing to say.
      void Promise.resolve()
        .then(() => getVersion())
        .then((version) => {
          if (!live) return;
          setCodeChanged(version.code_changed === true);
          setNewerPage(loaded !== null && version.bundle != null && version.bundle !== loaded);
          // Absent from an older server, which cannot say: that reads as "not behind".
          setStoreBehind(version.store_needs_migration === true);
        })
        .catch(() => {
          /* Advice, not a page failure: an older server simply has no route to ask. */
        });
    };
    check();
    const timer = window.setInterval(check, CHECK_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);

  if (!codeChanged && !newerPage && !storeBehind) return null;
  return (
    <div
      role="status"
      className="mx-auto flex max-w-[160rem] flex-wrap items-center gap-3 px-6 pt-4 text-sm text-fg"
    >
      {storeBehind ? (
        <span className="rounded-md border border-fg-2 bg-surface-2 px-3 py-2">
          The store needs a database upgrade, so pages that read it cannot load. The next
          `boardwatch run` does it, or run `boardwatch stats` now, then reload this page.
        </span>
      ) : null}
      {codeChanged || newerPage ? (
        <span className="rounded-md border border-fg-2 bg-surface-2 px-3 py-2">
          {codeChanged
            ? "This viewer is running older code than the checkout on disk. Stop it and start `boardwatch web` again to pick up the change."
            : "A newer version of this page is on disk."}
        </span>
      ) : null}
      {!codeChanged && newerPage ? (
        <button
          type="button"
          onClick={() => {
            window.location.reload();
          }}
          className="min-h-11 rounded-sm border border-fg-2 px-3 text-sm text-fg transition-colors duration-150 ease-in-out hover:bg-surface"
        >
          Reload
        </button>
      ) : null}
    </div>
  );
}
