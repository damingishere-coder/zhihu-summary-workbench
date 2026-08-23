import { afterEach, describe, expect, it, vi } from "vitest";
import { collectInPage } from "./collector";

function response(status: number, text: string, url = "https://www.zhihu.com/api/v4/me") {
  return { status, ok: status >= 200 && status < 300, url, text: async () => text } as Response;
}

afterEach(() => vi.unstubAllGlobals());

describe("Zhihu same-origin collector blocks", () => {
  it("maps 401 to login_required", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(401, "")));
    const result = await collectInPage({ question_external_id: "58173613", mode: "representative", max_answers: 20 });
    expect(result).toMatchObject({ kind: "blocked", reason: "login_required" });
  });

  it("maps 403 and verification text to verification_required", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(403, "当前请求存在异常")));
    const result = await collectInPage({ question_external_id: "58173613", mode: "representative", max_answers: 20 });
    expect(result).toMatchObject({ kind: "blocked", reason: "verification_required" });
  });
});
