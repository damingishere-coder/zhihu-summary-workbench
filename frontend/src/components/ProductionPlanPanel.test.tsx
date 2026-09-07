import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "antd";
import { MemoryRouter } from "react-router-dom";
import { vi, test, expect } from "vitest";
import { api } from "../api/client";
import { ProductionPlanPanel } from "./ProductionPlanPanel";

test("opening the dashboard only queries; execution and pause require clicks", async () => {
  const today = vi.spyOn(api, "todayPlan").mockResolvedValue({
    id: "manual-plan", plan_date: "2026-09-07", question_limit: 10,
    hot_quota: 6, manual_quota: 4, status: "pending", execute_time: "09:00",
    max_concurrency: 1, max_answers: 500, daily_publish_limit: 10,
    publish_interval_minutes: 30, auto_production: false, auto_publish: false,
    last_executed_at: null, result: { items: [], completed: 0 },
    created_at: "2026-09-07T00:00:00", updated_at: "2026-09-07T00:00:00",
  });
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
