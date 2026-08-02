import { describe, expect, it } from "vitest";
import { validateZhihuUrl } from "./QuestionModals";


describe("validateZhihuUrl", () => {
  it("接受标准知乎问题链接", () => {
    expect(validateZhihuUrl("https://www.zhihu.com/question/123456")).toBe(true);
    expect(validateZhihuUrl("https://zhihu.com/question/987654?utm_source=test")).toBe(true);
  });

  it("拒绝非知乎地址和非问题页", () => {
    expect(validateZhihuUrl("https://example.com/question/123")).toBe(false);
    expect(validateZhihuUrl("https://www.zhihu.com/people/test")).toBe(false);
  });
});

