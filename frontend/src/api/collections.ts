import { api } from "./client";
import type { Paginated } from "../types";

export async function collectPages<T extends { id: string }>(
  fetchPage: (offset: number) => Promise<Paginated<T>>,
): Promise<Paginated<T>> {
  const items = new Map<string, T>();
  let offset = 0;
  let total = 0;
  do {
    const page = await fetchPage(offset);
    total = page.total;
    if (!page.items.length && offset < total)
      throw new Error("列表在读取时发生变化，请刷新重试");
    page.items.forEach((item) => items.set(item.id, item));
    offset += page.items.length;
  } while (offset < total);
  if (items.size !== total) throw new Error("列表在读取时发生变化，请刷新重试");
  return { items: [...items.values()], total: items.size };
}

export const allDrafts = () =>
  collectPages((offset) => api.drafts({ offset, limit: 200 }));
export const allTasks = (status = "") =>
  collectPages((offset) => api.tasks({ status, offset, limit: 200 }));
