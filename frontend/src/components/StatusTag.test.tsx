import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusTag, statusLabel } from "./StatusTag";


describe("StatusTag", () => {
  it("用中文和图标显示已知状态", () => {
    render(<StatusTag status="waiting_review" />);
    expect(screen.getByText("待审核")).toBeInTheDocument();
    expect(statusLabel("failed")).toBe("失败");
  });

  it("未知状态仍然显示原始值", () => {
    render(<StatusTag status="custom_state" />);
    expect(screen.getByText("custom_state")).toBeInTheDocument();
  });
});

