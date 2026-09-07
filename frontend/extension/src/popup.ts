import type { BridgeState } from "./protocol";

const byId = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const urlInput = byId<HTMLInputElement>("workbench-url");
const codeInput = byId<HTMLInputElement>("pairing-code");
const pairButton = byId<HTMLButtonElement>("pair-button");
const checkButton = byId<HTMLButtonElement>("check-button");
const exportButton = byId<HTMLButtonElement>("export-button");
const forgetButton = byId<HTMLButtonElement>("forget-button");

async function refresh(initialize = false) {
  const stored = await chrome.storage.local.get(["workbenchUrl", "bridgeState", "lastBundle"]);
  if (initialize) urlInput.value = String(stored.workbenchUrl || "http://127.0.0.1:8002");
  const state = (stored.bridgeState || { connected: false, zhihuAuth: "unknown", message: "尚未配对" }) as BridgeState;
  byId("status-title").textContent = state.connected ? "扩展已连接" : "扩展未连接";
  const authLabels = { authenticated: "已登录", login_required: "请登录", verification_required: "需要人工验证", unknown: "尚未识别登录" };
  byId("status-message").textContent = `${state.message} · 知乎：${authLabels[state.zhihuAuth] || "尚未识别登录"}`;
  pairButton.textContent = state.connected ? "已连接 · 刷新状态" : "配对并连接";
  byId("status-dot").classList.toggle("connected", state.connected);
  exportButton.disabled = !stored.lastBundle;
}

async function withFeedback(button: HTMLButtonElement, action: () => Promise<void>) {
  button.disabled = true;
  try { await action(); }
  catch (error) { byId("status-message").textContent = error instanceof Error ? error.message : "操作失败，请重新打开扩展后重试"; }
  finally { button.disabled = false; }
}

pairButton.addEventListener("click", () => void withFeedback(pairButton, async () => {
  const { bridgeState } = await chrome.storage.local.get("bridgeState") as { bridgeState?: BridgeState };
  if (bridgeState?.connected) {
    await refresh();
    byId("status-message").textContent = `已连接工作台，无需重复配对。${byId("status-message").textContent}`;
    return;
  }
  const workbenchUrl = urlInput.value.trim().replace(/\/$/, "");
  const pairingCode = codeInput.value.trim().toUpperCase();
  if (!/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(workbenchUrl)) {
    byId("status-message").textContent = "只允许连接本机 127.0.0.1 或 localhost";
    return;
  }
  if (!/^[A-Z0-9]{8}$/.test(pairingCode)) {
    byId("status-message").textContent = "请输入 8 位配对码";
    return;
  }
  await chrome.storage.local.set({ workbenchUrl, pairingCode });
  byId("status-message").textContent = "正在连接工作台，请稍候…";
  await chrome.runtime.sendMessage({ type: "connect" });
}));
checkButton.addEventListener("click", () => void withFeedback(checkButton, async () => {
  byId("status-message").textContent = "正在检查知乎登录…";
  const response = await chrome.runtime.sendMessage({ type: "check_auth" });
  if (response?.ok === false) throw new Error(response.error || "知乎登录检查失败");
  await refresh();
}));
forgetButton.addEventListener("click", async () => { await chrome.storage.local.remove(["token", "pairingCode", "bridgeState"]); await refresh(); });
exportButton.addEventListener("click", async () => {
  const { lastBundle } = await chrome.storage.local.get("lastBundle");
  if (!lastBundle) return;
  const href = URL.createObjectURL(new Blob([JSON.stringify(lastBundle, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `zhihu-import-${Date.now()}.json`;
  anchor.click();
  URL.revokeObjectURL(href);
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && (changes.bridgeState || changes.lastBundle)) void refresh();
});
void refresh(true);
