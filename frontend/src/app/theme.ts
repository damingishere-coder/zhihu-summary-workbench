import type { ThemeConfig } from "antd";
import { theme } from "antd";

export type ThemeMode = "light" | "dark";

export function readThemePreference(): ThemeMode {
  const stored = window.localStorage.getItem("workbench-theme");
  if (stored === "dark" || stored === "light") return stored;
  return "light";
}

export function saveThemePreference(mode: ThemeMode) {
  window.localStorage.setItem("workbench-theme", mode);
}

export function createTheme(mode: ThemeMode): ThemeConfig {
  const dark = mode === "dark";
  return {
    algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: dark ? "#5B9CFF" : "#3264D6",
      colorSuccess: dark ? "#45C49B" : "#15805D",
      colorWarning: dark ? "#F0A451" : "#C76B16",
      colorError: dark ? "#FF6B64" : "#D92D20",
      colorText: dark ? "#F2F5F9" : "#202532",
      colorTextSecondary: dark ? "#A6B1C2" : "#667085",
      colorBgLayout: dark ? "#0F1724" : "#F5F6F8",
      colorBgContainer: dark ? "#151F2E" : "#FFFFFF",
      colorBorder: dark ? "#2A394D" : "#E5E8EE",
      borderRadius: 8,
      fontFamily:
        'Inter, "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif',
      fontSize: 16,
      controlHeight: 40,
    },
    components: {
      Table: {
        cellPaddingBlock: 10,
        cellPaddingInline: 12,
        headerBg: dark ? "#1B2737" : "#F8FAFC",
        headerColor: dark ? "#D7DFEA" : "#344054",
        rowHoverBg: dark ? "#1B2E47" : "#F1F7FF",
      },
      Menu: {
        itemHeight: 44,
        itemBorderRadius: 6,
        darkItemBg: "#151F2E",
      },
      Layout: {
        siderBg: dark ? "#151F2E" : "#FFFFFF",
        bodyBg: dark ? "#0F1724" : "#F5F6F8",
        headerBg: dark ? "#151F2E" : "#FFFFFF",
      },
    },
  };
}
