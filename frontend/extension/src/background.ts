import { collectInPage, type CollectRequest } from "./collector";
import { PROTOCOL_VERSION, randomNonce, websocketUrl, type BridgeState } from "./protocol";

type StoredConfig = { workbenchUrl?: string; token?: string; pairingCode?: string; lastBundle?: unknown };
let socket: WebSocket | null = null;
let reconnectAttempt = 0;
let heartbeat: number | null = null;

async function stored(): Promise<StoredConfig> {
  return chrome.storage.local.get(["workbenchUrl", "token", "pairingCode", "lastBundle"]);
}

async function updateState(values: Partial<BridgeState>) {
  const current = await chrome.storage.local.get("bridgeState") as { bridgeState?: BridgeState };
  await chrome.storage.local.set({ bridgeState: { connected: false, zhihuAuth: "unknown", message: "尚未连接", lastBundleAvailable: false, ...current.bridgeState, ...values } });
}

function send(payload: Record<string, unknown>) {
  if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("扩展桥接尚未连接");
  socket.send(JSON.stringify({ protocol_version: PROTOCOL_VERSION, ...payload }));
}

async function connect() {
  const config = await stored();
  if (!config.token && !config.pairingCode) return;
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
  try {
    socket = new WebSocket(websocketUrl(config.workbenchUrl || "http://127.0.0.1:8000"));
    socket.onopen = () => {
      reconnectAttempt = 0;
      send({ type: "hello", job_id: null, nonce: randomNonce(), extension_version: chrome.runtime.getManifest().version, token: config.token, pairing_code: config.pairingCode });
      void updateState({ connected: true, message: "扩展桥接已连接" });
      if (heartbeat !== null) clearInterval(heartbeat);
      heartbeat = setInterval(() => void checkAuth(), 20_000) as unknown as number;
    };
    socket.onmessage = (event) => void handleServerMessage(JSON.parse(String(event.data)) as Record<string, unknown>);
    socket.onclose = () => {
      socket = null;
      if (heartbeat !== null) clearInterval(heartbeat);
      heartbeat = null;
      void updateState({ connected: false, message: "连接已断开，正在自动重连" });
      const delay = Math.min(30_000, 1_000 * 2 ** reconnectAttempt++);
      setTimeout(() => void connect(), delay);
    };
    socket.onerror = () => void updateState({ connected: false, message: "无法连接本机工作台" });
  } catch (error) {
    await updateState({ connected: false, message: error instanceof Error ? error.message : "连接失败" });
  }
}

async function findZhihuTab(questionId?: string) {
  const tabs = await chrome.tabs.query({ url: ["https://www.zhihu.com/*", "https://zhihu.com/*"] });
  const matching = questionId ? tabs.find((tab) => tab.url?.includes(`/question/${questionId}`)) : tabs[0];
  if (matching?.id) return matching;
  if (!questionId) return null;
  return chrome.tabs.create({ url: `https://www.zhihu.com/question/${questionId}`, active: true });
}

async function waitForTab(tabId: number) {
  const current = await chrome.tabs.get(tabId);
  if (current.status === "complete") return;
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => { chrome.tabs.onUpdated.removeListener(listener); reject(new Error("知乎标签页加载超时")); }, 30_000);
    const listener = (id: number, info: { status?: string }) => {
      if (id === tabId && info.status === "complete") { clearTimeout(timeout); chrome.tabs.onUpdated.removeListener(listener); resolve(); }
    };
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function executeCollection(request: CollectRequest) {
  const tab = await findZhihuTab(request.question_external_id);
  if (!tab?.id) throw new Error("无法打开知乎问题标签页");
  await waitForTab(tab.id);
  const [execution] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: "MAIN", func: collectInPage, args: [request] });
  if (!execution?.result) throw new Error("知乎页面没有返回采集结果");
  return execution.result;
}

async function handleServerMessage(message: Record<string, unknown>) {
  if (message.type === "paired" && typeof message.token === "string") {
    await chrome.storage.local.set({ token: message.token });
    await chrome.storage.local.remove("pairingCode");
    await updateState({ connected: true, message: "配对成功" });
    await checkAuth();
    return;
  }
  if (message.type === "hello_ack") { await checkAuth(); return; }
  if (message.type !== "collect_question") return;
  const jobId = String(message.job_id ?? "");
  const nonce = String(message.nonce ?? "");
  try {
    send({ type: "progress", job_id: jobId, nonce, progress: 10, message: "正在正常知乎标签页采集" });
    const result = await executeCollection({
      question_external_id: String(message.question_external_id ?? ""),
      mode: message.mode === "complete" ? "complete" : "representative",
      max_answers: Number(message.max_answers ?? 20),
    });
    if (result.kind === "completed") {
      await chrome.storage.local.set({ lastBundle: result.bundle });
      await updateState({ lastBundleAvailable: true, zhihuAuth: "authenticated", message: "最近一次采集已完成" });
      send({ type: "completed", job_id: jobId, nonce, bundle: result.bundle });
    } else if (result.kind === "blocked") {
      await updateState({ zhihuAuth: result.reason, message: result.message });
      send({ type: "blocked", job_id: jobId, nonce, reason: result.reason, message: result.message });
    } else {
      send({ type: "failed", job_id: jobId, nonce, message: result.message });
    }
  } catch (error) {
    send({ type: "failed", job_id: jobId, nonce, message: error instanceof Error ? error.message : "扩展采集失败" });
  }
}

async function checkAuth() {
  const tab = await findZhihuTab();
  if (!tab?.id || !socket || socket.readyState !== WebSocket.OPEN) {
    await updateState({ zhihuAuth: "unknown", message: "请先打开一个知乎标签页" });
    return;
  }
  const [execution] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, world: "MAIN", func: async () => {
      try {
        const response = await fetch("/api/v4/me", { credentials: "include" });
        const text = await response.text();
        if (response.status === 401 || response.url.includes("/signin")) return "login_required";
        if (response.status === 403 || ["当前请求存在异常", "请完成安全验证"].some((value) => text.includes(value))) return "verification_required";
        return response.ok ? "authenticated" : "unknown";
      } catch { return "unknown"; }
    },
  });
  const auth = String(execution?.result ?? "unknown") as BridgeState["zhihuAuth"];
  await updateState({ zhihuAuth: auth, message: auth === "authenticated" ? "知乎实时登录状态正常" : "请在正常知乎标签页完成登录或验证" });
  send({ type: "auth_state", job_id: null, nonce: randomNonce(), zhihu_auth: auth });
}

chrome.runtime.onInstalled.addListener(() => chrome.alarms.create("bridge-reconnect", { periodInMinutes: 0.5 }));
chrome.runtime.onStartup.addListener(() => void connect());
chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === "bridge-reconnect") void connect(); });
chrome.runtime.onMessage.addListener((message, _sender, respond) => {
  if (message?.type === "connect") void connect().then(() => respond({ ok: true }));
  else if (message?.type === "check_auth") void checkAuth().then(() => respond({ ok: true }));
  else if (message?.type === "status") void chrome.storage.local.get(["bridgeState", "lastBundle"]).then(respond);
  else return false;
  return true;
});
void connect();
