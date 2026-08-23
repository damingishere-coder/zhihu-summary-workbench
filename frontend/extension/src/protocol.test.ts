import { describe, expect, it } from "vitest";
import { websocketUrl } from "./protocol";

describe("extension protocol", () => {
  it("only builds the local bridge path", () => {
    expect(websocketUrl("http://127.0.0.1:8000")).toBe("ws://127.0.0.1:8000/api/settings/browser/bridge/socket");
  });

  it("rejects non-http workbench schemes", () => {
    expect(() => websocketUrl("file:///tmp/workbench")).toThrow("http");
  });
});
