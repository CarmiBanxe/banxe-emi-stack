import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "."),
      "@banxe/tokens": resolve(__dirname, "./tokens/index.ts"),
    },
  },
  css: {
    // Allow CSS imports (tokens.css) in tests
    modules: {},
  },
});
