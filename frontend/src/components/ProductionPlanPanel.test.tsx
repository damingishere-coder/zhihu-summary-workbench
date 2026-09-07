import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "antd";
import { MemoryRouter } from "react-router-dom";
import { vi, test, expect } from "vitest";
import { api } from "../api/client";
import { ProductionPlanPanel } from "./ProductionPlanPanel";

test("opening the dashboard only queries; execution and pause require clicks", async () => {
  const today = vi.spyOn(api, "todayPlan").mockResolvedValue({ question_limit: 10, status: "pending", result: { items: [], completed: 0 } } as Awaited<ReturnType<typeof api.todayPlan>>);
  const run = vi.spyOn(api, "runTodayPlan").mockResolvedValue({ message: "已执行", queued_task_ids: [], plan: await api.todayPlan() });
  const pause = vi.spyOn(api, "pauseTodayPlan").mockResolvedValue({ message: "已暂停" });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<MemoryRouter><QueryClientProvider client={client}><App><ProductionPlanPanel /></App></QueryClientProvider></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole("button", { name: "执行 / 继续今日计划" })).toBeEnabled());
  expect(today).toHaveBeenCalled();
  expect(run).not.toHaveBeenCalled();
  expect(pause).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "执行 / 继续今日计划" }));
  await waitFor(() => expect(run).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "暂停计划" }));
  await waitFor(() => expect(pause).toHaveBeenCalledTimes(1));
  view.unmount();
  client.clear();
  vi.restoreAllMocks();
});
