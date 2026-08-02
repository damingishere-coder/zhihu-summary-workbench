import { createContext, useContext } from "react";
import type { ThemeMode } from "../app/theme";

export const ThemeModeContext = createContext<{
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}>({
  mode: "light",
  setMode: () => undefined,
});

export function useThemeMode() {
  return useContext(ThemeModeContext);
}

