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
import { afterEach, expect, test, vi } from "vitest";
import { api } from "../api/client";
import type { ImageWorkspace } from "../types";
import { ImagePromptWorkspace } from "./ImagePromptWorkspace";

const workspace: ImageWorkspace = {
  id: "image-1",
  article_draft_id: "draft-1",
  status: "draft",
  current_version: 1,
  use_css_background: true,
  versions: [],
  templates: [],
  current: {
    id: "v1",
    version: 1,
    content_json: { title: "配图标题", one_line_conclusion: "一句话结论" },
    prompt_zh: "",
    prompt_en: "",
    background_url: null,
    thumbnail_url: null,
    rendered_url: null,
    download_url: null,
    html_snapshot_available: false,
    render_status: "pending",
    canvas_width: 1080,
    canvas_height: 1440,
    overflow: [],
    render_log: [],
    uploaded_name: null,
    content_type: null,
    byte_size: 0,
    background_deleted: false,
    copy_state: {},
    created_at: "2026-09-07T00:00:00Z",
  },
};
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("image edits survive background refresh and failed save; render waits for saved content", async () => {
  vi.spyOn(api, "imageWorkspace").mockResolvedValue(workspace);
  vi.spyOn(api, "updateInfographic").mockRejectedValue(
    new Error("配图保存失败"),
  );
  const renderImage = vi.spyOn(api, "renderInfographic");
  const dirty = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <ConfigProvider theme={{ token: { motion: false } }}>
      <App>
        <QueryClientProvider client={client}>
          <ImagePromptWorkspace draftId="draft-1" onDirtyChange={dirty} />
        </QueryClientProvider>
      </App>
    </ConfigProvider>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: /打开完整编辑器/ }),
  );
  fireEvent.change(await screen.findByDisplayValue("配图标题"), {
    target: { value: "正在编辑的配图" },
  });
  await waitFor(() => expect(dirty).toHaveBeenLastCalledWith(true));
  act(() => {
    client.setQueryData(["image-workspace", "draft-1"], {
      ...workspace,
      current: {
        ...workspace.current,
        id: "v2",
        content_json: { title: "服务端刷新标题" },
      },
    });
  });
  expect(screen.getByDisplayValue("正在编辑的配图")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /渲染 PNG/ })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: /保存新版本/ }));
  await screen.findByText("配图保存失败");
  expect(screen.getByDisplayValue("正在编辑的配图")).toBeInTheDocument();
  expect(renderImage).not.toHaveBeenCalled();
  cleanup();
  client.clear();
});
