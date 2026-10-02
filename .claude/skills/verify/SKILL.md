---
name: verify
description: Run and drive the boardwatch web viewer (the real built bundle, served by the real Python server) against a synthetic isolated store. Use to verify any change under web/ or src/boardwatch/delivery/.
---

The surface is `boardwatch web`: the committed bundle (`src/boardwatch/web/static/`) served by the loopback
server. Verify there, never on the owner's viewer (port 8799) or the live store.

**Never** touch the live store, port 8799, or `--port 0`; use a scratch dir and a fixed free port (8811).

1. Rebuild only if `web/` changed: `cd web && npm run build` then
   `.venv/bin/python tests/unit/test_web_bundle_freshness.py` (node 20; the worktree needs `uv sync --frozen`).
2. Seed a store: `.venv/bin/python .claude/skills/verify/seed_store.py <scratch>/store`. It reuses the server test's
   helpers to make 9 leads (long title, no location, a `javascript:` apply URL, no résumé, review-lane, closed),
   two prior applications, run 1 (with a funnel) and run 2 (a manual re-render with NO funnel).
   The seed's funnel for run 1 is deliberately thin: the Runs page must say it "can't be drawn" and not throw. To
   see a funnel render, replace `out/2026-08-26/funnel-1.json` with a FULL-shape one (`FUNNELS` in
   `web/src/fixtures/runs.ts`).
3. Start it: `BOARDWATCH_CONFIG_DIR=<s>/config BOARDWATCH_DATA_DIR=<s>/data .venv/bin/boardwatch web --no-open
   --port 8811 --out-root <s>/out --queue-root <s>/queue`. The token is `<s>/config/web-token`; open
   `http://127.0.0.1:8811/#<token>`. Stop it by its pid, never `pkill -f`.
4. Drive with Playwright (`browser_run_code_unsafe` batches steps). Worth driving: record from the workspace
   (pending heading "Recording…" then "Application recorded", counts move after, `GET /api/applied` shows the row);
   panel Undo by keyboard (focus lands on `#lead-detail`; status becomes `withdrawn`); a refused write via
   `page.route('**/api/queue/*/applied', r => r.abort())` (row stays, counts unchanged, error toast); a double click on
   Record (one row); `o` on the `javascript:` lead (no new tab); Runs (404 for run 2 falls back to run 1 with a notice);
   widths 375 / 640x450 / 1280 for horizontal overflow (header is `static` below 42rem x 34rem, `sticky` above); dark
   theme persists; at 375 a job opens as a modal dialog and Escape returns focus to its row.
5. A route abort logs one expected console error; the Runs 404 logs another. Both are the probe, not a bug.

Gotchas: the page's own 404 for a funnel-less run is expected; `npx esbuild` (to dump a fixture to JSON) will
install esbuild into the npx cache; after a toast's Undo or Dismiss, focus lands on `main#view`.
