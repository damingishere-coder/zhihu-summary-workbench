import {
  BulbOutlined,
  DashboardOutlined,
  FileDoneOutlined,
  MoonOutlined,
  SettingOutlined,
  SunOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Tooltip } from "antd";
import { useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTaskEvents } from "../api/events";
import { useThemeMode } from "../contexts/ThemeModeContext";
import { SectionNav } from "../components/SectionNav";
import { ConnectionBadge } from "../components/ConnectionBadge";

const { Sider, Content } = Layout;

export function selectedMenuKey(pathname: string) {
  if (pathname.startsWith("/questions")) return "/questions";
  if (pathname.startsWith("/drafts") || pathname.startsWith("/publish"))
    return "/drafts";
  if (pathname.startsWith("/settings") || pathname.startsWith("/prompts"))
    return "/settings";
  return "/dashboard";
}

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { mode, setMode } = useThemeMode();
  const connection = useTaskEvents();
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 900px)");
    const sync = () => setCollapsed(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  const items = useMemo(
    () => [
      { key: "/dashboard", icon: <DashboardOutlined />, label: "今天" },
      { key: "/questions", icon: <BulbOutlined />, label: "选题" },
      { key: "/drafts", icon: <FileDoneOutlined />, label: "作品" },
    ],
    [],
  );

  return (
    <Layout className="app-shell">
      <Sider
        className="app-sider"
        width={208}
        collapsedWidth={72}
        collapsed={collapsed}
        theme={mode === "dark" ? "dark" : "light"}
        trigger={null}
      >
        <div className="brand" aria-label="知乎问题总结工作台">
          <img className="brand__mark" src="/brand-mark.png" alt="" />
          {!collapsed && (
            <span className="brand__text">
              <strong>知乎创作台</strong>
              <small>从一个问题，到一篇作品</small>
            </span>
          )}
        </div>
        <Menu
          className="main-nav"
          mode="inline"
          selectedKeys={[selectedMenuKey(location.pathname)]}
          items={items}
          onClick={({ key }) => navigate(key)}
        />
        <div className="sider-footer">
          {!collapsed && <ConnectionBadge state={connection} />}
          <Tooltip
            title={mode === "light" ? "切换到暗色模式" : "切换到亮色模式"}
          >
            <Button
              type="text"
              icon={mode === "light" ? <MoonOutlined /> : <SunOutlined />}
              onClick={() => setMode(mode === "light" ? "dark" : "light")}
              aria-label={
                mode === "light" ? "切换到暗色模式" : "切换到亮色模式"
              }
            />
          </Tooltip>
          <Button
            type={
              selectedMenuKey(location.pathname) === "/settings"
                ? "primary"
                : "text"
            }
            icon={<SettingOutlined />}
            onClick={() => navigate("/settings")}
            aria-label="设置"
          >
            {!collapsed && "设置"}
          </Button>
        </div>
      </Sider>
      <Content className="app-content">
        {(location.pathname.startsWith("/settings") ||
          location.pathname === "/prompts") && (
          <div className="settings-navigation">
            <SectionNav section="settings" />
          </div>
        )}
        <Outlet />
      </Content>
    </Layout>
  );
}
