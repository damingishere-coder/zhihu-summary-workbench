import {
  BulbOutlined,
  CalendarOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileDoneOutlined,
  ExperimentOutlined,
  MoonOutlined,
  SettingOutlined,
  SunOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Tooltip } from "antd";
import { useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTaskEvents } from "../api/events";
import { useThemeMode } from "../contexts/ThemeModeContext";
import { ConnectionBadge } from "../components/ConnectionBadge";

const { Sider, Content } = Layout;

function selectedMenuKey(pathname: string) {
  if (pathname.startsWith("/questions")) return "/questions";
  if (pathname.startsWith("/tasks")) return "/tasks";
  if (pathname.startsWith("/drafts")) return "/drafts";
  if (pathname.startsWith("/publish")) return "/publish";
  if (pathname.startsWith("/prompts")) return "/prompts";
  if (pathname.startsWith("/settings")) return "/settings";
  return "/dashboard";
}

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { mode, setMode } = useThemeMode();
  const connection = useTaskEvents();
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1180px)");
    const sync = () => setCollapsed(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  const items = useMemo(
    () => [
      { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘" },
      { key: "/questions", icon: <DatabaseOutlined />, label: "问题池" },
      { key: "/tasks", icon: <UnorderedListOutlined />, label: "任务中心" },
      { key: "/drafts", icon: <FileDoneOutlined />, label: "草稿审核" },
      { key: "/publish", icon: <CalendarOutlined />, label: "发布中心" },
      { key: "/prompts", icon: <ExperimentOutlined />, label: "Prompt 管理" },
      { key: "/settings", icon: <SettingOutlined />, label: "设置" },
    ],
    [],
  );

  return (
    <Layout className="app-shell">
      <Sider
        className="app-sider"
        width={232}
        collapsedWidth={72}
        collapsed={collapsed}
        theme={mode === "dark" ? "dark" : "light"}
        trigger={null}
      >
        <div className="brand" aria-label="知乎问题总结工作台">
          <img className="brand__mark" src="/brand-mark.png" alt="" />
          {!collapsed && <strong>知乎问题总结工作台</strong>}
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
          <Tooltip title={mode === "light" ? "切换到暗色模式" : "切换到亮色模式"}>
            <Button
              type="text"
              icon={mode === "light" ? <MoonOutlined /> : <SunOutlined />}
              onClick={() => setMode(mode === "light" ? "dark" : "light")}
              aria-label={mode === "light" ? "切换到暗色模式" : "切换到亮色模式"}
            />
          </Tooltip>
          <div className="operator">
            <span className="operator__avatar">
              <UserOutlined />
            </span>
            {!collapsed && (
              <span>
                <strong>内容运营组</strong>
                <small>运营专员</small>
              </span>
            )}
          </div>
        </div>
      </Sider>
      <Content className="app-content">
        <Outlet />
      </Content>
    </Layout>
  );
}
