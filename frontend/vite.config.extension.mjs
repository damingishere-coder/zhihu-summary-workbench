import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    environmentOptions: {
      jsdom: { url: "https://www.zhihu.com/question/58173613" },
    },
    include: ["extension/src/**/*.test.ts"],
  },
});
