import type { BridgeState } from "./protocol";

const byId = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const urlInput = byId<HTMLInputElement>("workbench-url");
const codeInput = byId<HTMLInputElement>("pairing-code");
const pairButton = byId<HTMLButtonElement>("pair-button");
const checkButton = byId<HTMLButtonElement>("check-button");
const exportButton = byId<HTMLButtonElement>("export-button");
const forgetButton = byId<HTMLButtonElement>("forget-button");

async function refresh() {
  const stored = await chrome.storage.local.get(["workbenchUrl", "bridgeState", "lastBundle"]);
  urlInput.value = String(stored.workbenchUrl || "http://127.0.0.1:8000");
  const state = (stored.bridgeState || { connected: false, zhihuAuth: "unknown", message: "尚未配对" }) as BridgeState;
  byId("status-title").textContent = state.connected ? "扩展已连接" : "扩展未连接";
  byId("status-message").textContent = `${state.message} · 知乎：${state.zhihuAuth}`;
  byId("status-dot").classList.toggle("connected", state.connected);
  exportButton.disabled = !stored.lastBundle;
}

pairButton.addEventListener("click", async () => {
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
  await chrome.runtime.sendMessage({ type: "connect" });
  setTimeout(() => void refresh(), 500);
});
checkButton.addEventListener("click", async () => { await chrome.runtime.sendMessage({ type: "check_auth" }); await refresh(); });
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
void refresh();
