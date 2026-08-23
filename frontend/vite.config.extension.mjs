import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["extension/src/**/*.test.ts"],
  },
});
