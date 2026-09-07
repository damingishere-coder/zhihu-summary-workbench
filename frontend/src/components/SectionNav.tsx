import { NavLink, useLocation } from "react-router-dom";

export function SectionNav({
  section,
}: {
  section: "today" | "works" | "settings";
}) {
  const location = useLocation();
  const links =
    section === "today"
      ? [
          ["/dashboard", "今日概览"],
          ["/tasks", "任务记录"],
        ]
      : section === "works"
        ? [
            ["/drafts", "全部作品"],
            ["/publish", "导出与发布"],
          ]
        : [
            ["/settings", "工作流与模型"],
            ["/settings/browser", "浏览器连接"],
            ["/prompts", "提示词管理"],
            ["/settings/open-source", "关于与开源"],
          ];
  return (
    <nav className="section-nav" aria-label="页面分组">
      {links.map(([to, label]) => (
        <NavLink
          end
          key={to}
          to={to}
          className={({ isActive }) =>
            isActive ||
            (to === "/settings" && location.pathname === "/settings/ai")
              ? "active"
              : ""
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
