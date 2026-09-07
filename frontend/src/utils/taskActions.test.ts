import { expect, test } from "vitest";
import { taskAction } from "./taskActions";
test.each([
  ["waiting_login", "处理知乎登录", "/settings/browser"],
  ["waiting_verification", "处理人工验证", "/settings/browser"],
  ["waiting_browser", "连接浏览器扩展", "/settings/browser"],
  ["image_result_unknown", "核对已有图片", "/questions/q1"],
  ["failed", "查看原因并处理", "/questions/q1"],
  ["waiting_review", "检查作品", "/drafts/d1/review"],
])("%s offers its specific next step", (status, label, href) => {
  expect(
    taskAction({
      id: "t1",
      question_id: "q1",
      status,
      error_message: null,
      result: { draft_id: "d1" },
    }),
  ).toMatchObject({ label, href: expect.stringContaining(href) });
});
test("partial collection offers inspection rather than an automatic retry", () => {
  expect(
    taskAction({
      id: "t1",
      question_id: "q1",
      status: "paused",
      error_message: "资料不足：仅采集到 2 条",
      result: {},
    }).label,
  ).toBe("检查资料并继续");
});
