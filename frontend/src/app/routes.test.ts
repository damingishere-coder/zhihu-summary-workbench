import { describe, expect, it } from "vitest";
import { routeInventory } from "./routes";
import { selectedMenuKey } from "../layouts/AppShell";

describe("第一阶段路由", () => {
  it("包含规格要求的关键页面", () => {
    expect(routeInventory).toEqual(
      expect.arrayContaining([
        "/dashboard",
        "/questions",
        "/questions/:id",
        "/tasks",
        "/drafts/:id/review",
        "/publish",
        "/settings",
        "/settings/ai",
      ]),
    );
  });
});

it.each([
  ["/tasks", "/dashboard"],
  ["/questions/q1", "/questions"],
  ["/drafts/d1/review", "/drafts"],
  ["/publish", "/drafts"],
  ["/prompts", "/settings"],
  ["/settings/ai", "/settings"],
])("旧入口 %s 正确归入 %s", (path, group) => {
  expect(selectedMenuKey(path)).toBe(group);
});
