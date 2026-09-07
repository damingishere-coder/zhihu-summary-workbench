import { expect, test } from "vitest";
import { collectPages } from "./collections";
test("reads all pages instead of treating the first 50 results as the total", async () => {
  const rows = Array.from({ length: 121 }, (_, index) => ({
    id: String(index),
  }));
  const offsets: number[] = [];
  const result = await collectPages(async (offset) => {
    offsets.push(offset);
    return { items: rows.slice(offset, offset + 50), total: rows.length };
  });
  expect(result.total).toBe(121);
  expect(offsets).toEqual([0, 50, 100]);
  expect(result.items.at(-1)?.id).toBe("120");
});
test("inconsistent empty pages fail instead of silently hiding outstanding work", async () => {
  await expect(
    collectPages(async () => ({ items: [], total: 1 })),
  ).rejects.toThrow("列表在读取时发生变化");
});
