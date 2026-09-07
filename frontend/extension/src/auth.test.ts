import { afterEach, expect, test } from "vitest";
import { inspectZhihuAuth } from "./auth";

afterEach(() => { document.body.innerHTML = ""; });

test("recognizes the current signed-in header without mistaking answer avatars for login", () => {
  document.body.innerHTML = '<article><img class="Avatar" /></article>';
  expect(inspectZhihuAuth()).toBe("unknown");
  document.body.innerHTML += '<button class="AppHeader-profileEntry"><img class="AppHeader-profileAvatar" alt="点击打开用户的主页" /></button>';
  expect(inspectZhihuAuth()).toBe("authenticated");
  document.body.innerHTML += '<div>请完成安全验证</div>';
  expect(inspectZhihuAuth()).toBe("verification_required");
});
