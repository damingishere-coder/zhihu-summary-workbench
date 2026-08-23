export type CollectRequest = {
  question_external_id: string;
  mode: "representative" | "complete";
  max_answers: number;
};

export type PageCollectResult =
  | { kind: "completed"; bundle: Record<string, unknown> }
  | { kind: "blocked"; reason: "login_required" | "verification_required"; message: string }
  | { kind: "failed"; message: string };

export async function collectInPage(request: CollectRequest): Promise<PageCollectResult> {
  const verificationPhrases = [
    "当前请求存在异常",
    "您的请求存在异常",
    "请完成安全验证",
    "检测到异常行为",
    "暂时限制访问",
  ];
  const fetchJson = async (path: string) => {
    const response = await fetch(path, {
      credentials: "include",
      headers: { Accept: "application/json, text/plain, */*" },
    });
    const text = await response.text();
    const finalPath = new URL(response.url, window.location.origin).pathname;
    if (response.status === 401 || finalPath.startsWith("/signin")) {
      throw { kind: "blocked", reason: "login_required", message: "知乎实时登录已失效，请在当前 Chrome 标签页登录" };
    }
    if (response.status === 403 || verificationPhrases.some((phrase) => text.includes(phrase))) {
      throw { kind: "blocked", reason: "verification_required", message: "知乎要求人工完成安全验证，请在当前标签页处理后重试" };
    }
    if (!response.ok) throw new Error(`知乎接口返回 ${response.status}`);
    try { return JSON.parse(text) as Record<string, unknown>; }
    catch { throw new Error("知乎接口没有返回合法 JSON"); }
  };
  try {
    const questionId = request.question_external_id;
    if (!/^\d+$/.test(questionId)) throw new Error("问题 id 无效");
    await fetchJson("/api/v4/me");
    const question = await fetchJson(`/api/v4/questions/${questionId}`);
    const include = encodeURIComponent("data[*].target.content,voteup_count,comment_count,created_time,updated_time,author,url,question");
    const rawAnswers: Array<Record<string, unknown>> = [];
    let offset = 0;
    let isEnd = false;
    const mode = request.mode === "complete" ? "complete" : "representative";
    const answerLimit = Math.max(1, Math.min(request.max_answers, 500));
    while (!isEnd && rawAnswers.length < answerLimit) {
      const limit = Math.min(20, answerLimit - rawAnswers.length);
      const endpoint = mode === "representative"
        ? `/api/v4/questions/${questionId}/feeds?include=${include}&limit=${limit}&offset=${offset}`
        : `/api/v4/questions/${questionId}/answers?include=${include}&limit=${limit}&offset=${offset}&sort_by=default`;
      const payload = await fetchJson(endpoint);
      const data = Array.isArray(payload.data) ? payload.data : [];
      for (const row of data) {
        if (!row || typeof row !== "object") continue;
        const record = row as Record<string, unknown>;
        const target = mode === "representative" && record.target && typeof record.target === "object"
          ? record.target as Record<string, unknown>
          : record;
        if (target.type === "answer" || target.id) rawAnswers.push(target);
        if (rawAnswers.length >= answerLimit) break;
      }
      const paging = payload.paging && typeof payload.paging === "object"
        ? payload.paging as Record<string, unknown>
        : {};
      isEnd = paging.is_end === true || data.length === 0 || mode === "representative";
      offset += data.length;
    }
    const answers = rawAnswers.map((answer) => {
      const author = answer.author && typeof answer.author === "object"
        ? answer.author as Record<string, unknown>
        : {};
      return {
        id: String(answer.id ?? ""),
        question_id: questionId,
        author: { name: String(author.name ?? "匿名用户"), url_token: String(author.url_token ?? "") },
        url: String(answer.url ?? ""),
        content: String(answer.content ?? ""),
        voteup_count: Number(answer.voteup_count ?? 0),
        comment_count: Number(answer.comment_count ?? 0),
        created_time: answer.created_time == null ? null : Number(answer.created_time),
        updated_time: answer.updated_time == null ? null : Number(answer.updated_time),
      };
    }).filter((answer) => /^\d+$/.test(answer.id));
    if (!answers.length) throw new Error("知乎接口没有返回可用回答");
    return {
      kind: "completed",
      bundle: {
        format: "ImportBundleV1",
        version: 1,
        collected_at: new Date().toISOString(),
        mode,
        question: {
          id: String(question.id ?? questionId),
          title: String(question.title ?? document.title),
          url: `https://www.zhihu.com/question/${questionId}`,
          detail: String(question.detail ?? ""),
          excerpt: String(question.excerpt ?? ""),
          answer_count: Number(question.answer_count ?? 0),
          follower_count: Number(question.follower_count ?? 0),
        },
        answers,
        warnings: [],
      },
    };
  } catch (error) {
    if (error && typeof error === "object" && (error as { kind?: string }).kind === "blocked") {
      return error as PageCollectResult;
    }
    const detail = error instanceof Error ? error.message : "知乎页面采集失败";
    return {
      kind: "failed",
      message: request.mode === "complete"
        ? `完整回答接口当前不可用：${detail}。请改用代表性模式或人工导入 ImportBundleV1。`
        : detail,
    };
  }
}
