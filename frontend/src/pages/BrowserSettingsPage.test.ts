import { describe, expect, it } from "vitest";
import {
  safeBrowserReturnPath,
  shouldPollBrowserSession,
} from "./BrowserSettingsPage";
import { PERMANENT_DELETE_WARNING } from "./QuestionsPage";


describe("知乎扫码登录页面辅助逻辑", () => {
  it("只允许返回工作台内部路径", () => {
    expect(safeBrowserReturnPath("/questions/q1")).toBe("/questions/q1");
    expect(safeBrowserReturnPath("//example.com")).toBe("/tasks");
    expect(safeBrowserReturnPath("https://example.com")).toBe("/tasks");
    expect(safeBrowserReturnPath(null)).toBe("/tasks");
  });

  it("仅在启动和等待扫码时持续轮询", () => {
    expect(shouldPollBrowserSession("starting")).toBe(true);
    expect(shouldPollBrowserSession("qr_ready")).toBe(true);
    expect(shouldPollBrowserSession("scanned")).toBe(true);
    expect(shouldPollBrowserSession("authenticated")).toBe(false);
    expect(shouldPollBrowserSession("failed")).toBe(false);
  });
});


describe("问题永久删除提示", () => {
  it("明确关联数据、不可恢复和知乎站外边界", () => {
    expect(PERMANENT_DELETE_WARNING).toContain("关联任务");
    expect(PERMANENT_DELETE_WARNING).toContain("无法恢复");
    expect(PERMANENT_DELETE_WARNING).toContain("不会删除知乎网站");
  });
});
