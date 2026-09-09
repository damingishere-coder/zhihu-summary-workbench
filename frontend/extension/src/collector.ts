export type CollectRequest = {
  question_external_id: string;
  mode: "representative" | "complete";
  max_answers: number;
  capture_strategy?: "rendered_dom" | "same_origin_api";
  max_scroll_rounds?: number;
  scroll_delay_ms?: number;
  known_answer_ids?: string[];
  allow_empty?: boolean;
};

export type CaptureDiagnostic = {
  code: string;
  level: "info" | "warning" | "error";
  message: string;
};

export type CaptureAttempt = {
  method: "rendered_dom" | "same_origin_api";
  page_url: string;
  visible_answer_count: number;
  collected_answer_count: number;
  diagnostics: CaptureDiagnostic[];
  reached_end?: boolean;
};

export type PageCollectResult =
  | { kind: "completed"; bundle: Record<string, unknown> }
  | {
      kind: "blocked";
      reason: "login_required" | "verification_required";
      message: string;
      capture: CaptureAttempt;
    }
  | { kind: "failed"; message: string; capture: CaptureAttempt };

export async function collectInPage(request: CollectRequest): Promise<PageCollectResult> {
  const verificationPhrases = [
    "当前请求存在异常",
    "您的请求存在异常",
    "请完成安全验证",
    "检测到异常行为",
    "暂时限制访问",
    "验证后继续访问",
  ];
  const verificationSelectors = [
    "[class*='Captcha']:not([class*='Login'])",
    "[class*='Verification']",
    "iframe[src*='captcha']",
    "iframe[src*='verification']",
  ];
  const answerCardSelectors = [
    ".List-item .AnswerItem",
    ".AnswerItem",
    "[itemprop='answer']",
    "article[data-zop]",
  ];
  const contentSelectors = [
    ".RichContent-inner",
    "[itemprop='text']",
    ".RichText",
  ];
  const diagnostics: CaptureDiagnostic[] = [];
  const pageUrl = window.location.href;
  const method = request.capture_strategy === "same_origin_api"
    ? "same_origin_api"
    : "rendered_dom";
  const answerLimit = Math.max(1, Math.min(Number(request.max_answers) || 20, 500));
  const normalizeText = (value: string) => value.replace(/\s+/g, " ").trim();
  const diagnostic = (code: string, level: CaptureDiagnostic["level"], message: string) => {
    if (!diagnostics.some((item) => item.code === code && item.message === message)) {
      diagnostics.push({ code, level, message });
    }
  };
  const captureAttempt = (
    visibleAnswerCount: number,
    collectedAnswerCount: number,
  ): CaptureAttempt => ({
    method,
    page_url: pageUrl,
    visible_answer_count: Math.max(visibleAnswerCount, collectedAnswerCount),
    collected_answer_count: collectedAnswerCount,
    diagnostics: diagnostics.slice(0, 30),
  });
  const blockedState = (): PageCollectResult | null => {
    const path = window.location.pathname.toLowerCase();
    const bodyText = normalizeText(document.body?.innerText || document.body?.textContent || "").slice(0, 100_000);
    if (path.startsWith("/signin") || path.startsWith("/account/login")) {
      diagnostic("login_required", "warning", "知乎页面已跳转到登录入口");
      return {
        kind: "blocked",
        reason: "login_required",
        message: "知乎实时登录已失效，请在当前 Chrome 标签页登录",
        capture: captureAttempt(0, 0),
      };
    }
    if (
      verificationPhrases.some((phrase) => bodyText.includes(phrase))
      || verificationSelectors.some((selector) => document.querySelector(selector))
    ) {
      diagnostic("verification_required", "warning", "知乎页面要求人工完成安全验证");
      return {
        kind: "blocked",
        reason: "verification_required",
        message: "知乎要求人工完成安全验证，请在当前标签页处理后重试",
        capture: captureAttempt(0, 0),
      };
    }
    return null;
  };
  const parseCount = (value: string | null | undefined) => {
    const normalized = normalizeText(value || "").replace(/,/g, "");
    const match = normalized.match(/(\d+(?:\.\d+)?)/);
    if (!match) return 0;
    const number = Number(match[1]);
    if (!Number.isFinite(number)) return 0;
    if (normalized.includes("万")) return Math.round(number * 10_000);
    if (normalized.includes("千")) return Math.round(number * 1_000);
    return Math.round(number);
  };
  const parseTimestamp = (value: string | null | undefined) => {
    if (!value) return null;
    if (/^\d{10,13}$/.test(value)) {
      const numeric = Number(value);
      return value.length === 13 ? Math.floor(numeric / 1000) : numeric;
    }
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : Math.floor(parsed / 1000);
  };
  const queryFirst = (root: ParentNode, selectors: string[]) => {
    for (const selector of selectors) {
      const element = root.querySelector(selector);
      if (element) return element as HTMLElement;
    }
    return null;
  };
  const questionId = String(request.question_external_id || "");
  if (!/^\d+$/.test(questionId)) {
    diagnostic("invalid_question_id", "error", "问题 id 无效");
    return { kind: "failed", message: "问题 id 无效", capture: captureAttempt(0, 0) };
  }

  const collectViaApi = async (): Promise<PageCollectResult> => {
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
      const initialBlock = blockedState();
      if (initialBlock) return initialBlock;
      await fetchJson("/api/v4/me");
      const question = await fetchJson(`/api/v4/questions/${questionId}`);
      const include = encodeURIComponent("data[*].content,voteup_count,comment_count,created_time,updated_time,author,url,question");
      const rawAnswers: Array<Record<string, unknown>> = [];
      let offset = 0;
      let isEnd = false;
      while (!isEnd && rawAnswers.length < answerLimit) {
        const limit = Math.min(20, answerLimit - rawAnswers.length);
        const endpoint = `/api/v4/questions/${questionId}/answers?include=${include}&limit=${limit}&offset=${offset}&sort_by=default`;
        const payload = await fetchJson(endpoint);
        const data = Array.isArray(payload.data) ? payload.data : [];
        for (const row of data) {
          if (!row || typeof row !== "object") continue;
          const record = row as Record<string, unknown>;
          if (record.type === "answer" || record.id) rawAnswers.push(record);
          if (rawAnswers.length >= answerLimit) break;
        }
        const paging = payload.paging && typeof payload.paging === "object"
          ? payload.paging as Record<string, unknown>
          : {};
        isEnd = paging.is_end === true || data.length === 0;
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
      diagnostic("api_capture", "info", "本次任务显式使用知乎同源回答接口");
      const capture = captureAttempt(answers.length, answers.length);
      return {
        kind: "completed",
        bundle: {
          format: "CollectionBundleV2",
          version: 2,
          collected_at: new Date().toISOString(),
          mode: request.mode,
          capture,
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
        const blocked = error as { reason: "login_required" | "verification_required"; message: string };
        diagnostic(blocked.reason, "warning", blocked.message);
        return { kind: "blocked", ...blocked, capture: captureAttempt(0, 0) };
      }
      const detail = error instanceof Error ? error.message : "知乎接口采集失败";
      diagnostic("api_capture_failed", "error", detail);
      return {
        kind: "failed",
        message: `显式 API 采集失败：${detail}。请改用默认页面采集或人工导入 ImportBundleV1。`,
        capture: captureAttempt(0, 0),
      };
    }
  };

  if (method === "same_origin_api") return collectViaApi();

  const initialBlock = blockedState();
  if (initialBlock) return initialBlock;
  const pageQuestionMatch = window.location.pathname.match(/\/question\/(\d+)/);
  if (!pageQuestionMatch || pageQuestionMatch[1] !== questionId) {
    diagnostic("question_page_mismatch", "error", "当前标签页不是目标知乎问题");
    return {
      kind: "failed",
      message: "当前标签页不是目标知乎问题，请重新打开后采集",
      capture: captureAttempt(0, 0),
    };
  }

  const titleElement = queryFirst(document, [
    "h1.QuestionHeader-title",
    "[data-za-detail-view-element_name='Title']",
    "main h1",
  ]);
  const metaTitle = document.querySelector("meta[itemprop='name']")?.getAttribute("content") || "";
  const title = normalizeText(titleElement?.textContent || metaTitle || document.title.replace(/\s*-\s*知乎\s*$/, ""));
  if (!title) {
    diagnostic("question_title_missing", "error", "未识别知乎问题标题，页面结构可能已经变化");
    return {
      kind: "failed",
      message: "未识别知乎问题标题，页面结构可能已经变化",
      capture: captureAttempt(0, 0),
    };
  }

  const knownIds = new Set(request.known_answer_ids || []);
  const answersById = new Map<string, Record<string, unknown>>();
  const seenUrls = new Set<string>();
  let visibleAnswerCount = 0;
  let expandedCount = 0;
  const maxRounds = Math.max(1, Math.min(Number(request.max_scroll_rounds ?? 8), 20));
  const scrollDelay = Math.max(0, Math.min(Number(request.scroll_delay_ms ?? 1200), 2_000));
  let stagnantRounds = 0;
  let previousVisible = -1;
  let scrollRetriggers = 0;

  const answerCards = () => {
    const cards = new Set<HTMLElement>();
    for (const selector of answerCardSelectors) {
      document.querySelectorAll(selector).forEach((element) => cards.add(element as HTMLElement));
    }
    return [...cards];
  };
  const answerIdFromCard = (card: HTMLElement) => {
    const answerLink = card.querySelector<HTMLAnchorElement>(`a[href*="/question/${questionId}/answer/"]`);
    const fromLink = answerLink?.href.match(/\/answer\/(\d+)/)?.[1];
    if (fromLink) return fromLink;
    const itemPropUrl = card.querySelector("meta[itemprop='url']")?.getAttribute("content") || "";
    const fromMeta = itemPropUrl.match(/\/answer\/(\d+)/)?.[1];
    if (fromMeta) return fromMeta;
    const zop = card.getAttribute("data-zop") || card.querySelector("[data-zop]")?.getAttribute("data-zop");
    if (zop) {
      try {
        const payload = JSON.parse(zop) as Record<string, unknown>;
        const itemId = String(payload.itemId ?? payload.item_id ?? "");
        if (/^\d+$/.test(itemId)) return itemId;
      } catch {
        diagnostic("invalid_data_zop", "warning", "一个回答卡片包含无法解析的 data-zop");
      }
    }
    const fromId = card.id.match(/(?:answer[-_])?(\d{5,})/)?.[1];
    return fromId || "";
  };
  const parseCard = (card: HTMLElement) => {
    const id = answerIdFromCard(card);
    const contentElement = queryFirst(card, contentSelectors);
    const content = contentElement?.innerHTML?.trim() || "";
    const plainContent = normalizeText(contentElement?.textContent || "");
    if (!/^\d+$/.test(id) || !content || !plainContent) return null;
    const answerUrl = `https://www.zhihu.com/question/${questionId}/answer/${id}`;
    if (knownIds.has(id)) return null;
    const previous = answersById.get(id);
    if (previous && String(previous.content).length >= content.length) return null;
    if (!previous && seenUrls.has(answerUrl)) return null;
    if ([...card.querySelectorAll("button, [role='button']")].some((button) => /展开阅读全文|展开全部|继续阅读/.test(normalizeText(button.textContent || "")))) return null;
    const authorLink = queryFirst(card, [".AuthorInfo-name a", ".UserLink-link", "a[href*='/people/']"]);
    const authorName = normalizeText(
      authorLink?.textContent
      || queryFirst(card, [".AuthorInfo-name", "[itemprop='name']"])?.textContent
      || "匿名用户",
    );
    const authorHref = authorLink instanceof HTMLAnchorElement ? authorLink.href : "";
    const authorToken = authorHref.match(/\/people\/([^/?#]+)/)?.[1] || "";
    const voteElement = queryFirst(card, ["button.VoteButton--up", "button[aria-label*='赞同']", "[itemprop='upvoteCount']"]);
    const commentElement = [...card.querySelectorAll("button, a")].find((element) => /评论/.test(element.textContent || ""));
    const created = card.querySelector("meta[itemprop='dateCreated']")?.getAttribute("content")
      || card.querySelector("time")?.getAttribute("datetime");
    const updated = card.querySelector("meta[itemprop='dateModified']")?.getAttribute("content") || created;
    seenUrls.add(answerUrl);
    return {
      id,
      question_id: questionId,
      author: { name: authorName || "匿名用户", url_token: authorToken },
      url: answerUrl,
      content,
      voteup_count: parseCount(voteElement?.getAttribute("content") || voteElement?.getAttribute("aria-label") || voteElement?.textContent),
      comment_count: parseCount(commentElement?.textContent),
      created_time: parseTimestamp(created),
      updated_time: parseTimestamp(updated),
    };
  };

  for (let round = 0; round < maxRounds && answersById.size < answerLimit; round += 1) {
    const blocked = blockedState();
    if (blocked?.kind === "blocked") {
      return { ...blocked, capture: captureAttempt(visibleAnswerCount, answersById.size) };
    }
    const expandButtons = [...document.querySelectorAll<HTMLElement>("button, [role='button']")]
      .filter((element) => /展开阅读全文|展开全部|继续阅读/.test(normalizeText(element.textContent || "")))
      .slice(0, Math.max(0, answerLimit - answersById.size));
    for (const button of expandButtons) {
      button.click();
      expandedCount += 1;
    }
    if (expandedCount && scrollDelay > 0) {
      // Expansion often fetches asynchronously; wait for content to settle.
      let previousText = "";
      for (let settle = 0; settle < 5; settle += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 400));
        const currentText = answerCards().map((card) => card.textContent || "").join("");
        if (currentText === previousText) break;
        previousText = currentText;
      }
    }
    const cards = answerCards();
    visibleAnswerCount = Math.max(visibleAnswerCount, cards.length);
    for (const card of cards) {
      const answer = parseCard(card);
      if (answer) answersById.set(String(answer.id), answer);
      if (answersById.size >= answerLimit) break;
    }
    if (answersById.size >= answerLimit) break;
    if (answersById.size === previousVisible) stagnantRounds += 1;
    else stagnantRounds = 0;
    previousVisible = answersById.size;
    if (stagnantRounds >= 3) break;
    const pageHeight = Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight || 0);
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 800;
    const bottom = Math.max(0, pageHeight - viewportHeight);
    const currentTop = window.scrollY || document.scrollingElement?.scrollTop || 0;
    if (bottom > 0 && currentTop >= bottom - 4) {
      // A second scroll to the same bottom does not re-enter the lazy-load trigger.
      // Leave the bottom first, then scroll down again as a reader would.
      window.scrollTo({ top: Math.max(0, bottom - Math.max(240, viewportHeight * 0.75)), behavior: "auto" });
      await new Promise((resolve) => window.setTimeout(resolve, Math.min(scrollDelay, 300)));
      scrollRetriggers += 1;
    }
    window.scrollTo({ top: pageHeight, behavior: "auto" });
    await new Promise((resolve) => window.setTimeout(resolve, scrollDelay));
  }

  const answers = [...answersById.values()].slice(0, answerLimit);
  if (!answers.length && !request.allow_empty) {
    diagnostic(
      visibleAnswerCount ? "answer_structure_changed" : "no_rendered_answers",
      "error",
      visibleAnswerCount
        ? "发现回答卡片但无法识别回答 ID 或正文，页面结构可能已经变化"
        : "当前页面没有可采集的已渲染回答",
    );
    return {
      kind: "failed",
      message: diagnostics[diagnostics.length - 1].message,
      capture: captureAttempt(visibleAnswerCount, 0),
    };
  }
  if (expandedCount) diagnostic("answers_expanded", "info", `自动展开了 ${expandedCount} 个回答正文`);
  if (scrollRetriggers) diagnostic("scroll_retrigger", "info", `已执行 ${scrollRetriggers} 次向上回滑再下滑，重新触发后续回答加载`);
  diagnostic("dom_capture", "info", `从当前可见页面采集 ${answers.length} 条回答`);
  const warnings: string[] = [];
  if (answers.length < answerLimit) {
    const warning = `当前页面实际采集 ${answers.length} 条回答，少于目标 ${answerLimit} 条`;
    warnings.push(warning);
    diagnostic("answer_limit_not_reached", "warning", warning);
  }
  const detailElement = queryFirst(document, [".QuestionHeader-detail", ".QuestionRichText", "[itemprop='description']"]);
  const excerpt = document.querySelector("meta[name='description']")?.getAttribute("content") || "";
  const answerCountElement = queryFirst(document, [".List-headerText", "[itemprop='answerCount']"]);
  const followerElement = [...document.querySelectorAll<HTMLElement>("button, strong")]
    .find((element) => /关注者/.test(element.textContent || ""));
  const capture = captureAttempt(visibleAnswerCount, answers.length);
  const endMarkers = [...document.querySelectorAll(".List-footer, .List-end, .EmptyState, [data-za-detail-view-element_name='ListEnd']")];
  capture.reached_end = endMarkers.some((el) => /没有更多|已显示全部|没有更多回答|已经到底/.test(el.textContent || ""));
  return {
    kind: "completed",
    bundle: {
      format: "CollectionBundleV2",
      version: 2,
      collected_at: new Date().toISOString(),
      mode: request.mode,
      capture,
      question: {
        id: questionId,
        title,
        url: `https://www.zhihu.com/question/${questionId}`,
        detail: detailElement?.innerHTML || "",
        excerpt,
        answer_count: Math.max(parseCount(answerCountElement?.getAttribute("content") || answerCountElement?.textContent), answers.length),
        follower_count: parseCount(followerElement?.textContent),
      },
      answers,
      warnings,
    },
  };
}
