import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "antd";
import { MemoryRouter } from "react-router-dom";
import { vi, test, expect, afterEach } from "vitest";
import { api } from "../api/client";
import { ProductionPlanPanel } from "./ProductionPlanPanel";
import type { DailyPlan } from "../types";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("changing the target needs explicit save and does not execute the plan", async () => {
  const initial = {
    id: "p1",
    status: "pending",
    question_limit: 10,
    result: { items: [] },
  } as unknown as DailyPlan;
  const today = vi.spyOn(api, "todayPlan").mockResolvedValue(initial);
  const save = vi
    .spyOn(api, "updateTodayPlan")
    .mockImplementation(async (value) => {
      const next = { ...initial, ...value };
      today.mockResolvedValue(next);
      return next;
    });
  const run = vi.spyOn(api, "runTodayPlan");
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <App>
          <ProductionPlanPanel />
        </App>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("spinbutton", { name: "今日目标题数" }),
    ).toBeEnabled(),
  );
  fireEvent.change(screen.getByRole("spinbutton", { name: "今日目标题数" }), {
    target: { value: "6" },
  });
  fireEvent.blur(screen.getByRole("spinbutton", { name: "今日目标题数" }));
  expect(save).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: /开始今日计划/ })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "保存目标" }));
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith({
      question_limit: 6,
      hot_quota: 4,
      manual_quota: 2,
    }),
  );
  expect(run).not.toHaveBeenCalled();
  view.unmount();
  client.clear();
});

test("opening the dashboard only queries; execution and pause require clicks", async () => {
  const today = vi.spyOn(api, "todayPlan").mockResolvedValue({
    id: "manual-plan",
    plan_date: "2026-09-07",
    question_limit: 10,
    hot_quota: 6,
    manual_quota: 4,
    status: "pending",
    execute_time: "09:00",
    max_concurrency: 1,
    max_answers: 500,
    daily_publish_limit: 10,
    publish_interval_minutes: 30,
    auto_production: false,
    auto_publish: false,
    last_executed_at: null,
    result: { items: [], completed: 0 },
    created_at: "2026-09-07T00:00:00",
    updated_at: "2026-09-07T00:00:00",
  });
  const initial = await api.todayPlan();
  const run = vi.spyOn(api, "runTodayPlan").mockImplementation(async () => {
    const running = {
      ...initial,
      status: "running",
      result: { items: [{ task_id: "t1", status: "generating_article" }] },
    };
    today.mockResolvedValue(running);
    return { message: "已执行", queued_task_ids: ["t1"], plan: running };
  });
  const pause = vi
    .spyOn(api, "pauseTodayPlan")
    .mockResolvedValue({ message: "已暂停" });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <App>
          <ProductionPlanPanel />
        </App>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /开始今日计划/ })).toBeEnabled(),
  );
  expect(today).toHaveBeenCalled();
  expect(run).not.toHaveBeenCalled();
  expect(pause).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /开始今日计划/ }));
  await waitFor(() => expect(run).toHaveBeenCalledTimes(1));
  fireEvent.click(await screen.findByRole("button", { name: /暂停计划/ }));
  await waitFor(() => expect(pause).toHaveBeenCalledTimes(1));
  view.unmount();
  client.clear();
  vi.restoreAllMocks();
});
