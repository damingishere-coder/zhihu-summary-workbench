import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App, ConfigProvider } from "antd";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../api/client";
import type { Draft, PublishReadiness } from "../types";
import { DraftReviewPage } from "./DraftReviewPage";

vi.mock("../components/ImagePromptWorkspace", () => ({
  ImagePromptWorkspace: () => <div>测试配图工作区</div>,
}));
const draft: Draft = {
  id: "d1",
  question_id: "q1",
  question_title: "测试问题",
  status: "waiting_review",
  current_version: 1,
  title: "测试文章",
  content: "第一段原文。\n\n第二段原文。",
  analysis_snapshot: { answer_count: 2 },
  review_result: {
    score: 80,
    passed: true,
    checks: {},
    issues: [],
    summary: "待人工检查",
    risk_level: "normal",
    requires_human_review: true,
  },
  reviewed_at: null,
  paragraph_sources: [],
  created_at: "2026-09-07T00:00:00Z",
  updated_at: "2026-09-07T00:00:00Z",
};
const readiness: PublishReadiness = {
  draft_id: "d1",
  ready: false,
  article_approved: false,
  article_version_id: "v1",
  article_version: 1,
  image_rendered: false,
  image_version_id: null,
  image_version: null,
  risk_level: "low",
  blockers: ["尚未通过人工审核", "配图尚未渲染"],
  warnings: [],
};
let client: QueryClient;
beforeEach(() => {
  vi.spyOn(api, "draft").mockResolvedValue(draft);
  vi.spyOn(api, "draftVersions").mockResolvedValue([
    {
      id: "v1",
      version: 1,
      title: draft.title,
      content: draft.content,
      source_task_id: null,
      created_at: draft.created_at,
    },
  ]);
  vi.spyOn(api, "publishReadiness").mockResolvedValue(readiness);
  client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
});
afterEach(() => {
  cleanup();
  client.clear();
  vi.restoreAllMocks();
});

function setup(url = "/drafts/d1/review") {
  const router = createMemoryRouter(
    [
      { path: "/drafts/:id/review", element: <DraftReviewPage /> },
      { path: "/drafts", element: <div>作品列表已打开</div> },
    ],
    { initialEntries: ["/drafts", url], initialIndex: 1 },
  );
  render(
    <ConfigProvider theme={{ token: { motion: false } }}>
      <App>
        <QueryClientProvider client={client}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </App>
    </ConfigProvider>,
  );
  return router;
}
async function edit() {
  fireEvent.click(await screen.findByRole("button", { name: "编辑文章" }));
  fireEvent.change(screen.getByRole("textbox", { name: "文章正文" }), {
    target: { value: "尚未保存的新正文" },
  });
}

test("defaults to readable article; steps preserve edits and do not trigger writes", async () => {
  const update = vi.spyOn(api, "updateDraft");
  const review = vi.spyOn(api, "reviewDraft");
  const regenerate = vi.spyOn(api, "regenerateDraft");
  const router = setup();
  expect(await screen.findByText("第一段原文。")).toBeVisible();
  expect(
    screen.queryByRole("textbox", { name: "文章正文" }),
  ).not.toBeInTheDocument();
  await edit();
  fireEvent.click(screen.getByRole("button", { name: "下一步：检查配图" }));
  expect(router.state.location.search).toContain("step=image");
  fireEvent.click(screen.getByRole("button", { name: "上一步" }));
  expect(screen.getByRole("textbox", { name: "文章正文" })).toHaveValue(
    "尚未保存的新正文",
  );
  expect(update).not.toHaveBeenCalled();
  expect(review).not.toHaveBeenCalled();
  expect(regenerate).not.toHaveBeenCalled();
});

test("background refresh and failed save preserve unsaved input", async () => {
  vi.spyOn(api, "updateDraft").mockRejectedValue(new Error("保存失败，请重试"));
  setup();
  await edit();
  act(() => {
    client.setQueryData(["drafts", "d1"], {
      ...draft,
      content: "后台返回的旧正文",
    });
  });
  expect(screen.getByRole("textbox", { name: "文章正文" })).toHaveValue(
    "尚未保存的新正文",
  );
  fireEvent.click(screen.getByRole("button", { name: /保存新版本/ }));
  await screen.findByText("保存失败，请重试");
  expect(screen.getByRole("textbox", { name: "文章正文" })).toHaveValue(
    "尚未保存的新正文",
  );
});

test("browser back is blocked; stay preserves edits; explicit discard leaves", async () => {
  const router = setup();
  await edit();
  await act(() => router.navigate(-1));
  await waitFor(() =>
    expect(
      screen.getByRole("dialog", { name: "还有未保存的修改" }),
    ).toBeVisible(),
  );
  fireEvent.click(screen.getByRole("button", { name: "留在这里" }));
  expect(screen.getByRole("textbox", { name: "文章正文" })).toHaveValue(
    "尚未保存的新正文",
  );
  fireEvent.click(screen.getByRole("button", { name: /返回作品列表/ }));
  fireEvent.click(
    await screen.findByRole("button", { name: "放弃修改并离开" }),
  );
  expect(await screen.findByText("作品列表已打开")).toBeVisible();
});

test("save and leave waits for success and creates the new article version", async () => {
  const update = vi
    .spyOn(api, "updateDraft")
    .mockImplementation(async (_, value) => {
      const next = { ...draft, ...value, current_version: 2 };
      vi.mocked(api.draft).mockResolvedValue(next);
      return next;
    });
  setup();
  await edit();
  fireEvent.click(screen.getByRole("button", { name: /返回作品列表/ }));
  fireEvent.click(await screen.findByRole("button", { name: "保存并离开" }));
  await screen.findByText("作品列表已打开");
  expect(update).toHaveBeenCalledWith("d1", {
    title: "测试文章",
    content: "尚未保存的新正文",
  });
});

test("restore requires confirmation when local edits exist", async () => {
  setup();
  await edit();
  fireEvent.click(screen.getByRole("tab", { name: "历史版本 1" }));
  fireEvent.click(await screen.findByRole("button", { name: "恢复到编辑器" }));
  await screen.findByRole("dialog", { name: "用历史版本替换未保存修改？" });
  fireEvent.click(screen.getByRole("button", { name: "保留修改" }));
  fireEvent.click(screen.getByRole("tab", { name: "Markdown 编辑" }));
  expect(screen.getByRole("textbox", { name: "文章正文" })).toHaveValue(
    "尚未保存的新正文",
  );
});

test("review deep link respects server readiness and updates after explicit approval", async () => {
  vi.spyOn(api, "approveDraft").mockImplementation(async () => {
    vi.mocked(api.publishReadiness).mockResolvedValue({
      ...readiness,
      ready: true,
      article_approved: true,
      image_rendered: true,
      blockers: [],
    });
    const approved = { ...draft, status: "review_approved" };
    vi.mocked(api.draft).mockResolvedValue(approved);
    return approved;
  });
  setup("/drafts/d1/review?step=review");
  expect(
    await screen.findByRole("button", { name: /下载发布包/ }),
  ).toBeDisabled();
  await screen.findByText("配图尚未渲染");
  fireEvent.click(screen.getByRole("button", { name: /人工审核通过/ }));
  await waitFor(() =>
    expect(screen.getByRole("link", { name: /下载发布包/ })).toHaveAttribute(
      "href",
      "/api/drafts/d1/publish-package",
    ),
  );
});
