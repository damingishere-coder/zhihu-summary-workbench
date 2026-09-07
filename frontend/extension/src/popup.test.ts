import { afterEach, expect, test, vi } from "vitest";

afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = ""; });

test("connected pair button gives feedback and storage updates keep unfinished address edits", async () => {
  document.body.innerHTML = '<input id="workbench-url"><input id="pairing-code"><button id="pair-button"></button><button id="check-button"></button><button id="export-button"></button><button id="forget-button"></button><div id="status-title"></div><div id="status-message"></div><div id="status-dot"></div>';
  let changed: (changes: object, area: string) => void = () => {};
  const sendMessage = vi.fn();
  const state = { workbenchUrl: "http://127.0.0.1:8002", bridgeState: { connected: true, zhihuAuth: "unknown", message: "请先打开一个知乎标签页" } };
  vi.stubGlobal("chrome", {
    storage: { local: { get: vi.fn().mockResolvedValue(state) }, onChanged: { addListener: (listener: typeof changed) => { changed = listener; } } },
    runtime: { sendMessage },
  });
  await import("./popup");
  const button = document.getElementById("pair-button") as HTMLButtonElement;
  await vi.waitFor(() => expect(button.textContent).toBe("已连接 · 刷新状态"));
  button.click();
  await vi.waitFor(() => expect(document.getElementById("status-message")?.textContent).toContain("无需重复配对"));
  expect(sendMessage).not.toHaveBeenCalled();
  const input = document.getElementById("workbench-url") as HTMLInputElement;
  input.value = "http://localhost:8002";
  changed({ bridgeState: {} }, "local");
  await vi.waitFor(() => expect(document.getElementById("status-message")?.textContent).toContain("尚未识别登录"));
  expect(input.value).toBe("http://localhost:8002");
});
