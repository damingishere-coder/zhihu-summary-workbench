import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { collectInPage } from "./collector";

function response(status: number, text: string, url = "https://www.zhihu.com/api/v4/me") {
  return { status, ok: status >= 200 && status < 300, url, text: async () => text } as Response;
}

function answerCard(id: string, content: string, author = "作者") {
  return `
    <article class="AnswerItem" data-zop='{"itemId":"${id}"}'>
      <a href="/question/58173613/answer/${id}">回答链接</a>
      <a class="UserLink-link" href="/people/author-${id}">${author}</a>
      <div class="RichContent-inner"><p>${content}</p></div>
      <button class="VoteButton--up" aria-label="赞同 1.2 万">赞同</button>
      <button>3 条评论</button>
      <meta itemprop="dateCreated" content="2026-08-20T12:00:00Z" />
    </article>`;
}

beforeEach(() => {
  window.history.replaceState({}, "", "/question/58173613");
  document.head.innerHTML = '<title>DOM 采集测试问题 - 知乎</title><meta name="description" content="测试摘要" />';
  document.body.innerHTML = '<h1 class="QuestionHeader-title">DOM 采集测试问题</h1>';
  vi.stubGlobal("fetch", vi.fn());
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Zhihu DOM-first collector", () => {
  it("collects rendered answers and records provenance", async () => {
    document.body.insertAdjacentHTML("beforeend", `${answerCard("900001", "第一条不同内容")}${answerCard("900002", "第二条不同内容", "匿名用户")}`);
    const result = await collectInPage({ question_external_id: "58173613", mode: "representative", max_answers: 2 });
    expect(result.kind).toBe("completed");
    if (result.kind !== "completed") return;
    const bundle = result.bundle as { format: string; answers: Array<Record<string, unknown>>; capture: Record<string, unknown> };
    expect(bundle.format).toBe("CollectionBundleV2");
    expect(bundle.answers).toHaveLength(2);
    expect(bundle.answers[0]).toMatchObject({ id: "900001", voteup_count: 12_000, comment_count: 3 });
    expect(bundle.capture).toMatchObject({ method: "rendered_dom", visible_answer_count: 2, collected_answer_count: 2 });
    expect(fetch).not.toHaveBeenCalled;
  });

  it("keeps identical text from different answer IDs for author statistics", async () => {
    document.body.insertAdjacentHTML("beforeend", `<button id="expand">展开阅读全文</button>${answerCard("900003", "重复正文")}${answerCard("900004", "重复正文")}`);
    document.querySelector("#expand")?.addEventListener("click", () => {
      document.querySelector("#expand")?.remove();
    });
    let appended = false;
    vi.stubGlobal("scrollTo", vi.fn(() => {
      if (!appended) {
        appended = true;
        document.body.insertAdjacentHTML("beforeend", answerCard("900005", "滚动后新增正文"));
      }
    }));
    const result = await collectInPage({
      question_external_id: "58173613",
      mode: "representative",
      max_answers: 3,
      max_scroll_rounds: 2,
      scroll_delay_ms: 0,
    });
    expect(result.kind).toBe("completed");
    if (result.kind !== "completed") return;
    const bundle = result.bundle as { answers: Array<Record<string, unknown>>; capture: { diagnostics: Array<{ code: string }> }; warnings: string[] };
    expect(bundle.answers.map((answer) => answer.id)).toEqual(["900003", "900004", "900005"]);
    expect(bundle.capture.diagnostics.map((item) => item.code)).toContain("answers_expanded");
    expect(bundle.warnings).toEqual([]);
  });

  it("reports page changes instead of fabricating answers", async () => {
    document.body.insertAdjacentHTML("beforeend", '<article class="AnswerItem"><div class="RichContent-inner">没有回答 id</div></article>');
    const result = await collectInPage({
      question_external_id: "58173613",
      mode: "representative",
      max_answers: 20,
      max_scroll_rounds: 1,
      scroll_delay_ms: 0,
    });
    expect(result).toMatchObject({ kind: "failed", capture: { visible_answer_count: 1, collected_answer_count: 0 } });
    if (result.kind === "failed") {
      expect(result.capture.diagnostics.map((item) => item.code)).toContain("answer_structure_changed");
    }
  });

  it("pauses for login and verification without calling APIs", async () => {
    window.history.replaceState({}, "", "/signin");
    const login = await collectInPage({ question_external_id: "58173613", mode: "representative", max_answers: 20 });
    expect(login).toMatchObject({ kind: "blocked", reason: "login_required" });
    window.history.replaceState({}, "", "/question/58173613");
    document.body.textContent = "当前请求存在异常，请完成安全验证";
    const verification = await collectInPage({ question_external_id: "58173613", mode: "representative", max_answers: 20 });
    expect(verification).toMatchObject({ kind: "blocked", reason: "verification_required" });
    expect(fetch).not.toHaveBeenCalled;
  });
});

describe("Zhihu explicit same-origin API collector", () => {
  it("maps 401 to login_required", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(401, "")));
    const result = await collectInPage({
      question_external_id: "58173613",
      mode: "complete",
      max_answers: 20,
      capture_strategy: "same_origin_api",
    });
    expect(result).toMatchObject({ kind: "blocked", reason: "login_required", capture: { method: "same_origin_api" } });
  });

  it("maps 403 and verification text to verification_required", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(403, "当前请求存在异常")));
    const result = await collectInPage({
      question_external_id: "58173613",
      mode: "complete",
      max_answers: 20,
      capture_strategy: "same_origin_api",
    });
    expect(result).toMatchObject({ kind: "blocked", reason: "verification_required" });
  });
});
