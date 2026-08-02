import { describe, expect, it, vi } from "vitest";
import { copyPromptText } from "./ImagePromptWorkspace";


describe("图片 Prompt 工作区", () => {
  it("把完整 Prompt 写入浏览器剪贴板", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    await copyPromptText("图片内不得生成中文文字");

    expect(writeText).toHaveBeenCalledWith("图片内不得生成中文文字");
  });

  it("剪贴板权限不可用时使用传统复制方式", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("permission denied"));
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand,
    });

    await copyPromptText("保留完整图片 Prompt");

    expect(writeText).toHaveBeenCalledWith("保留完整图片 Prompt");
    expect(execCommand).toHaveBeenCalledWith("copy");
  });
});
