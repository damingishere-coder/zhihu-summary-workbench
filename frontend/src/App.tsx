import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { useEffect, useMemo, useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { AppRoutes } from "./app/routes";
import {
  createTheme,
  readThemePreference,
  saveThemePreference,
  type ThemeMode,
} from "./app/theme";
import { ThemeModeContext } from "./contexts/ThemeModeContext";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  const [mode, setModeState] = useState<ThemeMode>(readThemePreference);
  const theme = useMemo(() => createTheme(mode), [mode]);
  const context = useMemo(
    () => ({
      mode,
      setMode: (next: ThemeMode) => {
        saveThemePreference(next);
        setModeState(next);
      },
    }),
    [mode],
  );
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.colorScheme = mode;
  }, [mode]);

  return (
    <ConfigProvider locale={zhCN} theme={theme}>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <ThemeModeContext.Provider value={context}>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </ThemeModeContext.Provider>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  );
}
