import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntApp } from "antd";
import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
} from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { ManagedBrowserSession, Task } from "../types";
import { BrowserSettingsPage } from "./BrowserSettingsPage";

const authenticatedSession: ManagedBrowserSession = {
  state: "authenticated",
  authenticated: true,
  message: "知乎登录会话可用",
  qr_code_url: null,
  updated_at: "2026-07-26T15:14:36Z",
};

function renderBrowserSettings(
  initialEntry = "/settings/browser?taskId=task-1&returnTo=%2Ftasks",
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <StrictMode>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter
            initialEntries={[initialEntry]}
          >
            <Routes>
              <Route
                path="/settings/browser"
                element={<BrowserSettingsPage />}
              />
              <Route path="/tasks" element={<div>已返回任务页</div>} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </AntApp>
    </StrictMode>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("知乎登录后的任务恢复", () => {
  it("失败状态使用明确的错误提示展示简短原因", async () => {
    vi.spyOn(api, "browserSession").mockResolvedValue({
      state: "failed",
      authenticated: false,
      message: "工作台浏览器显示服务异常，请重启工作台后再试。",
      qr_code_url: null,
      updated_at: "2026-07-29T13:34:28Z",
    });

    renderBrowserSettings("/settings/browser");

    await screen.findByText("工作台浏览器操作失败");
    expect(
      screen.getByText("工作台浏览器显示服务异常，请重启工作台后再试。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("本次登录检查未完成，请按下方提示处理后重试。"),
    ).toBeInTheDocument();
  });

  it("自动恢复失败后不随重新渲染循环请求，并允许手动重试", async () => {
    const browserSession = vi
      .spyOn(api, "browserSession")
      .mockResolvedValue(authenticatedSession);
    const resume = vi
      .spyOn(api, "resumeTaskAfterLogin")
      .mockRejectedValue(new Error("知乎登录尚未完成，请重新扫码登录"));

    renderBrowserSettings();

    await screen.findByText("任务恢复失败");
    await waitFor(() => expect(browserSession).toHaveBeenCalledTimes(2));
    expect(resume).toHaveBeenCalledTimes(1);
    expect(
      screen.getAllByText("知乎登录尚未完成，请重新扫码登录"),
    ).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "重新恢复任务" }));

    await waitFor(() => expect(resume).toHaveBeenCalledTimes(2));
    await screen.findByText("任务恢复失败");
  });

  it("自动恢复成功后只请求一次并返回原页面", async () => {
    vi.spyOn(api, "browserSession").mockResolvedValue(authenticatedSession);
    const resume = vi
      .spyOn(api, "resumeTaskAfterLogin")
      .mockResolvedValue({ status: "queued" } as Task);

    renderBrowserSettings();

    await screen.findByText("已返回任务页");
    expect(resume).toHaveBeenCalledTimes(1);
  });

  it("人工验证恢复使用专用接口且不会再次调用登录恢复", async () => {
    vi.spyOn(api, "browserSession").mockResolvedValue(authenticatedSession);
    const loginResume = vi.spyOn(api, "resumeTaskAfterLogin");
    const verificationResume = vi
      .spyOn(api, "resumeTaskAfterVerification")
      .mockResolvedValue({ status: "queued" } as Task);

    renderBrowserSettings(
      "/settings/browser?taskId=task-1&recovery=verification&returnTo=%2Ftasks",
    );

    await screen.findByText("已返回任务页");
    expect(verificationResume).toHaveBeenCalledTimes(1);
    expect(loginResume).not.toHaveBeenCalled();
  });
});
