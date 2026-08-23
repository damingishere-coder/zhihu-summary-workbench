import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntApp } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { BrowserBridgeStatus, Question, Task } from "../types";
import { BrowserSettingsPage } from "./BrowserSettingsPage";

const unpaired: BrowserBridgeStatus = {
  connection: "unpaired",
  zhihu_auth: "unknown",
  extension_version: "",
  last_seen_at: null,
  last_check_at: null,
  active_job_id: null,
  message: "尚未配对 Chrome 扩展",
};

function renderBrowserSettings(initialEntry = "/settings/browser") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <AntApp>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes><Route path="/settings/browser" element={<BrowserSettingsPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </AntApp>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("Chrome 扩展桥接", () => {
  it("展示独立连接与知乎实时登录状态并生成一次性配对码", async () => {
    vi.spyOn(api, "browserBridgeStatus").mockResolvedValue(unpaired);
    const createPairing = vi.spyOn(api, "createBridgePairing").mockResolvedValue({
      pairing_code: "A1B2C3D4",
      expires_at: "2026-08-23T14:10:00Z",
      websocket_url: "ws://127.0.0.1:8000/api/settings/browser/bridge/socket",
      message: "一次性配对码",
    });
    renderBrowserSettings();
    await screen.findByText("尚未配对 Chrome 扩展");
    expect(screen.getByText("尚未检查")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /生成一次性配对码/ }));
    await screen.findByText("一次性配对码：A1B2C3D4");
    expect(createPairing).toHaveBeenCalledTimes(1);
  });

  it("等待中的任务使用专用采集恢复接口且不增加普通重试", async () => {
    vi.spyOn(api, "browserBridgeStatus").mockResolvedValue({
      ...unpaired,
      connection: "connected",
      zhihu_auth: "authenticated",
      extension_version: "0.1.0",
      message: "扩展在线，知乎实时登录状态正常",
    });
    vi.spyOn(api, "task").mockResolvedValue({ id: "task-1", question_id: "q-1", status: "waiting_browser" } as Task);
    vi.spyOn(api, "question").mockResolvedValue({ id: "q-1", external_id: "58173613" } as Question);
    const retryCollection = vi.spyOn(api, "retryCollection").mockResolvedValue({
      task_id: "task-1",
      collection_job_id: "job-1",
      status: "waiting_browser",
      dispatched: true,
      message: "采集任务已发送到 Chrome 扩展",
    });
    renderBrowserSettings("/settings/browser?taskId=task-1&returnTo=%2Ftasks");
    const button = await screen.findByRole("button", { name: "用 Chrome 重新获取并继续" });
    fireEvent.click(button);
    await waitFor(() => expect(retryCollection).toHaveBeenCalledTimes(1));
  });
});
