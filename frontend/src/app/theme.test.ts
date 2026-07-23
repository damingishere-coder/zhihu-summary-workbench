import { beforeEach, describe, expect, it } from "vitest";
import { createTheme, readThemePreference, saveThemePreference } from "./theme";


describe("主题偏好", () => {
  beforeEach(() => window.localStorage.clear());

  it("首次访问默认使用设计稿的亮色模式", () => {
    expect(readThemePreference()).toBe("light");
  });

  it("保存并读取暗色模式", () => {
    saveThemePreference("dark");
    expect(readThemePreference()).toBe("dark");
  });

  it("亮暗主题使用不同的背景和主色", () => {
    const light = createTheme("light");
    const dark = createTheme("dark");
    expect(light.token?.colorBgLayout).not.toBe(dark.token?.colorBgLayout);
    expect(light.token?.colorPrimary).not.toBe(dark.token?.colorPrimary);
  });
});
