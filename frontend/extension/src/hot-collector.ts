// Self-contained because Chrome serializes this function into the page.
export function collectHotInPage(limit: number) {
  const text = document.body?.innerText || "";
  if (/^\/signin/.test(location.pathname) || /请完成安全验证|当前请求存在异常|暂时限制访问/.test(text)) {
    return { items: [], error: "知乎需要登录或验证，请在当前热榜页面处理" };
  }
  const rows = [...document.querySelectorAll(".HotItem, [data-za-detail-view-path-module='HotItem']")];
  const items: Array<{ id: string; title: string; rank: number }> = [];
  const seen = new Set<string>();
  for (const row of rows) {
    const anchor = row.querySelector<HTMLAnchorElement>("a[href*='/question/']");
    const id = anchor?.href.match(/\/question\/(\d+)/)?.[1];
    const title = (row.querySelector(".HotItem-title, h2, h3")?.textContent || anchor?.getAttribute("title") || "").trim();
    if (!id || !title || seen.has(id)) continue;
    seen.add(id);
    items.push({ id, title: title.slice(0, 500), rank: items.length + 1 });
    if (items.length >= limit) break;
  }
  return { items, error: items.length ? "" : "热榜页面尚未加载或结构发生变化" };
}
