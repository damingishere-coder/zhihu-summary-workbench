import { describe, expect, it } from "vitest";
import {
  groupParagraphSources,
  markdownToSafeHtml,
  paragraphRange,
  replaceTextRange,
} from "./DraftReviewPage";


describe("草稿段落来源映射", () => {
  it("按 paragraph_id 分组且不丢失回答与观点簇来源", () => {
    const grouped = groupParagraphSources([
      {
        paragraph_id: "p001",
        answer_id: "a1",
        answer_author: "答主一",
        answer_url: "https://example.com/a1",
        answer_excerpt: "来源回答",
        cluster_id: null,
        cluster_name: null,
      },
      {
        paragraph_id: "p001",
        answer_id: null,
        answer_author: null,
        answer_url: null,
        answer_excerpt: null,
        cluster_id: "c1",
        cluster_name: "行动门槛",
      },
      {
        paragraph_id: "p002",
        answer_id: "a2",
        answer_author: "答主二",
        answer_url: "https://example.com/a2",
        answer_excerpt: "另一条来源",
        cluster_id: null,
        cluster_name: null,
      },
    ]);

    expect(grouped.p001).toHaveLength(2);
    expect(grouped.p001[1].cluster_name).toBe("行动门槛");
    expect(grouped.p002[0].answer_id).toBe("a2");
  });

  it("支持局部重写替换、段落定位和安全富文本预览", () => {
    const source = "# 标题\n\n第一段内容\n\n第二段内容";
    const range = paragraphRange(source, source.indexOf("第一段"));

    expect(source.slice(range.start, range.end)).toBe("第一段内容");
    expect(replaceTextRange(source, range.start, range.end, "重写后的第一段"))
      .toContain("重写后的第一段");
    expect(markdownToSafeHtml("# <危险标题>"))
      .toBe("<h1>&lt;危险标题&gt;</h1>");
  });
});
