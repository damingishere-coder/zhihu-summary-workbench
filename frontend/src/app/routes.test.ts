import { describe, expect, it } from "vitest";
import { routeInventory } from "./routes";


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

