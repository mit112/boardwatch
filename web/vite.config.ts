import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// PACKAGING TRAP — read before changing `outDir`.
//
// The repository's `.gitignore` line 6 is `dist/`, unanchored, so it matches a directory named
// `dist` at ANY depth. Vite's default `outDir` is `dist`, so the built bundle would be untracked,
// absent from every published wheel, and the shipped UI would be an empty page. The output must
// land inside the package tree instead, where hatchling picks it up as package data with no extra
// configuration. Do not "fix" this with a packaging include: that re-adds the file to the wheel
// while leaving it untracked, so a wheel built from a clean checkout still ships nothing.
const OUT_DIR = "../src/boardwatch/web/static";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Served from the loopback server's root; absolute asset URLs keep working on every route.
  base: "/",
  build: {
    outDir: OUT_DIR,
    emptyOutDir: true,
    // Content-hashed names, stated explicitly rather than inherited, because the CI job compares
    // per-asset content hashes against the committed bundle.
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
  server: { port: 5173, strictPort: true },
});
