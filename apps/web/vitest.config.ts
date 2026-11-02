import { defineConfig } from "vitest/config";

// Pure-logic unit tests only (no DOM). The app's vite.config.ts carries the react-router plugin, so it is not reused.
export default defineConfig({
  resolve: { alias: { "@": import.meta.dirname } },
  test: { include: ["ee/**/*.test.ts"], environment: "node" },
});
