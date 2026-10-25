import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  // tsconfig.json sets jsx: "preserve" for Next's own compiler, so the test
  // transform has to be told to use the automatic runtime itself — otherwise
  // every render fails with "React is not defined".
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // The panels poll on timers; without this a hung fetch mock would stall
    // the whole run instead of failing the one test.
    testTimeout: 10000,
  },
});
