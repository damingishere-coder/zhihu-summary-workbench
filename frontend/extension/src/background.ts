import { collectHotInPage } from "./hot-collector";
import { collectInPage, type CollectRequest } from "./collector";
import { PROTOCOL_VERSION, randomNonce, websocketUrl, type BridgeState } from "./protocol";

type StoredConfig = { workbenchUrl?: string; token?: string; pairingCode?: string; lastBundle?: unknown };
let socket: WebSocket | null = null;
let reconnectAttempt = 0;
let heartbeat: number | null = null;
let operationChain: Promise<void> = Promise.resolve();
const activeJobs = new Set<string>();
const acknowledgements = new Map<string, (value: Record<string, unknown>) => void>();

async function acknowledgedSend(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  const batchId = String(payload.batch_id);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { acknowledgements.delete(batchId); reject(new Error("批次确认超时；已保存批次将在继续时去重")); }, 30_000);
    acknowledgements.set(batchId, (value) => { clearTimeout(timer); acknowledgements.delete(batchId); resolve(value); });
    try { send(payload); } catch (error) { clearTimeout(timer); acknowledgements.delete(batchId); reject(error); }
  });
}


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
    socket = new WebSocket(websocketUrl(config.workbenchUrl || "http://127.0.0.1:8002"));
    socket.onopen = () => {
      reconnectAttempt = 0;
      send({ type: "hello", job_id: null, nonce: randomNonce(), extension_version: chrome.runtime.getManifest().version, token: config.token, pairing_code: config.pairingCode });
      void updateState({ connected: true, message: "扩展桥接已连接" });
      if (heartbeat !== null) clearInterval(heartbeat);
      heartbeat = setInterval(() => void checkAuth(), 20_000) as unknown as number;
    };
    socket.onmessage = (event) => {
      try {
        void handleServerMessage(JSON.parse(String(event.data)) as Record<string, unknown>)
          .catch((error) => void updateState({
            message: error instanceof Error ? error.message : "处理桥接消息失败",
          }));
      } catch {
        void updateState({ message: "工作台返回了无法识别的桥接消息" });
      }
    };
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
  if (message.type === "batch_ack") {
    acknowledgements.get(String(message.batch_id))?.(message.result as Record<string, unknown>);
    return;
  }
  if (message.type === "collect_hot") {
    operationChain = operationChain.then(async () => {
      try {
        const tabs = await chrome.tabs.query({ url: "https://www.zhihu.com/hot*" });
        const tab = tabs[0] || await chrome.tabs.create({ url: "https://www.zhihu.com/hot", active: true });
        if (!tab.id) throw new Error("无法打开热榜");
        await waitForTab(tab.id);
        let result: ReturnType<typeof collectHotInPage> = { items: [], error: "热榜未加载" };
        for (let attempt = 0; attempt < 10; attempt += 1) {
          const [execution] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: "MAIN", func: collectHotInPage, args: [Number(message.limit || 30)] });
          result = execution.result || result;
          if (result.items.length || result.error.includes("验证")) break;
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        send({ type: "hot_result", nonce: message.nonce, job_id: message.job_id, ...result });
      } catch (error) {
        if (socket?.readyState === WebSocket.OPEN) send({ type: "hot_result", nonce: message.nonce, job_id: message.job_id, error: String(error), items: [] });
      }
    });
    return;
  }
  if (message.type !== "collect_question") return;
  const jobId = String(message.job_id ?? "");
  if (activeJobs.has(jobId)) return;
  activeJobs.add(jobId);
  operationChain = operationChain.then(() => collectJob(message)).finally(() => activeJobs.delete(jobId));
}

async function collectJob(message: Record<string, unknown>) {
  const jobId = String(message.job_id ?? "");
  const nonce = String(message.nonce ?? "");
  const known = new Set((message.known_answer_ids as string[]) || []);
  const initialElapsed = Number(message.elapsed_seconds || 0);
  const started = Date.now();
  let emptyRounds = 0;
  const budget = Math.min(1800, Number(message.capture_budget_seconds || 1800));
  try {
    while (true) {
      if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("桥接已断开，采集暂停");
      const elapsed = initialElapsed + (Date.now() - started) / 1000;
      if (elapsed >= budget) {
        await acknowledgedSend({ type: "answer_batch", job_id: jobId, nonce, batch_id: randomNonce(), finished: true, elapsed_seconds: Math.min(elapsed,1800), stop_reason: "time_budget" });
        return;
      }
      const result = await executeCollection({
        question_external_id: String(message.question_external_id || ""),
        mode: message.mode === "complete" ? "complete" : "representative",
        max_answers: message.chunked ? 20 : Number(message.max_answers || 100),
        capture_strategy: message.capture_strategy === "same_origin_api" ? "same_origin_api" : "rendered_dom",
        known_answer_ids: [...known], allow_empty: known.size > 0,
        max_scroll_rounds: 12, scroll_delay_ms: 1200,
      });
      if (result.kind === "completed") {
        if (!message.chunked) {
          await chrome.storage.local.set({ lastBundle: result.bundle });
          send({ type: "completed", job_id: jobId, nonce, bundle: result.bundle });
          return;
        }
        const answers = result.bundle.answers as Array<{ id: string }>;
        const capture = result.bundle.capture as { reached_end?: boolean };
        emptyRounds = answers.length ? 0 : emptyRounds + 1;
        const nowElapsed = Math.min(1800, initialElapsed + (Date.now() - started) / 1000);
        const reason = capture.reached_end ? "page_end" : nowElapsed >= budget ? "time_budget" : emptyRounds >= 3 ? "no_progress" : "";
        const ack = await acknowledgedSend({ type: "answer_batch", job_id: jobId, nonce, batch_id: randomNonce(),
          bundle: answers.length ? result.bundle : null, finished: Boolean(reason), stop_reason: reason, elapsed_seconds: nowElapsed });
        for (const answer of answers) known.add(answer.id);
        await updateState({ message: `已保存 ${ack.saved || known.size} 条回答`, zhihuAuth: "authenticated" });
        if (!ack.continue) return;
      } else if (result.kind === "blocked") {
        await updateState({ zhihuAuth: result.reason, message: result.message });
        // Previously acknowledged batches remain in SQLite, ready for explicit continuation.
        send({ type: "blocked", job_id: jobId, nonce, reason: result.reason, message: result.message, capture: result.capture });
        return;
      } else {
        send({ type: "failed", job_id: jobId, nonce, message: result.message, capture: result.capture });
        return;
      }
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : "扩展采集中断";
    if (socket?.readyState === WebSocket.OPEN) send({ type: "failed", job_id: jobId, nonce, message: detail });
    await updateState({ message: detail });
  }
}

async function checkAuth() {
  const tab = await findZhihuTab();
  if (!tab?.id || !socket || socket.readyState !== WebSocket.OPEN) {
    await updateState({ zhihuAuth: "unknown", message: "请先打开一个知乎标签页" });
    return;
  }
  const [execution] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, world: "MAIN", func: () => {
      const path = window.location.pathname.toLowerCase();
      const text = (document.body?.innerText || document.body?.textContent || "").replace(/\s+/g, " ").slice(0, 100_000);
      if (path.startsWith("/signin") || path.startsWith("/account/login")) return "login_required";
      if (
        ["当前请求存在异常", "请完成安全验证", "暂时限制访问", "验证后继续访问"].some((value) => text.includes(value))
        || document.querySelector("[class*='Captcha']:not([class*='Login']), [class*='Verification'], iframe[src*='captcha']")
      ) return "verification_required";
      if (document.querySelector(".AppHeader-profile, .AppHeader-userInfo .Avatar")) return "authenticated";
      if (document.querySelector(".SignFlow, .SignFlowHomepage")) return "login_required";
      return "unknown";
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
