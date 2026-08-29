import { defineConfig } from "vitest/config";

/*
 * The frontend's own gate. Separate from `vite.config.ts` on purpose: nothing here may reach a
 * production build, and the two configs share no `outDir`, no plugin list and no `base`. The
 * tests are transformed by esbuild against `tsconfig.json`'s `jsx: "react-jsx"`, so no react
 * plugin is needed — fast refresh is a dev-server feature and there is no dev server here.
 *
 * The test files live under `src/` so that `tsc --noEmit` and eslint cover them exactly as they
 * cover the components. They are NOT bundled: Vite emits the module graph reachable from
 * `index.html`, nothing in it imports a `.test.tsx`, and none of them imports `src/fixtures/` —
 * which is what keeps placeholder identity data out of every wheel (see `api/client.ts`).
 */
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.tsx"],
    setupFiles: ["./src/test/setup.ts"],
    // Spies and module mocks are restored between tests, so one test's stub cannot silently
    // satisfy the next one's assertion.
    restoreMocks: true,
  },
});
