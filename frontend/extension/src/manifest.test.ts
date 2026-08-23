import { describe, expect, it } from "vitest";
import manifest from "../manifest.json";

describe("extension manifest security", () => {
  it("does not request cookie or broad browsing permissions", () => {
    expect(manifest.permissions).not.toContain("cookies");
    expect(manifest.permissions).not.toContain("webRequest");
    expect(manifest.host_permissions).not.toContain("<all_urls>");
    expect(
      manifest.host_permissions.filter((item) => item.startsWith("http:")),
    ).toEqual(["http://127.0.0.1/*", "http://localhost/*"]);
  });
});
