import { describe, expect, it } from "vitest";
import { websocketUrl, collectionStopReason } from "./protocol";

describe("extension protocol", () => {
  it("finishes immediately when page scrolling has exhausted its retries", () => {
    expect(collectionStopReason({ stop_reason: "no_progress", reached_end: false }, 20, 600, 0)).toBe("no_progress");
    expect(collectionStopReason({}, 20, 600, 0)).toBe("");
    expect(collectionStopReason({}, 600, 600, 0)).toBe("time_budget");
    expect(collectionStopReason({ reached_end: true }, 20, 600, 0)).toBe("page_end");
  });
  it("only builds the local bridge path", () => {
    expect(websocketUrl("http://127.0.0.1:8000")).toBe("ws://127.0.0.1:8000/api/settings/browser/bridge/socket");
  });

  it("rejects non-http workbench schemes", () => {
    expect(() => websocketUrl("file:///tmp/workbench")).toThrow("http");
  });
});
