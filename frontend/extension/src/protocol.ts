export const PROTOCOL_VERSION = 1;

export type BridgeState = {
  connected: boolean;
  zhihuAuth: "authenticated" | "login_required" | "verification_required" | "unknown";
  message: string;
  lastBundleAvailable: boolean;
};

export function randomNonce() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

export function websocketUrl(workbenchUrl: string) {
  const url = new URL(workbenchUrl);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("工作台地址必须使用 http 或 https");
  }
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/api/settings/browser/bridge/socket";
  url.search = "";
  url.hash = "";
  return url.toString();
}
