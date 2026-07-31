"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { normalizeTheme, THEME_STORAGE_KEY, type FormaTheme } from "./theme";

type ThemeContextValue = {
  theme: FormaTheme;
  setTheme: (theme: FormaTheme) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyTheme(theme: FormaTheme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<FormaTheme>("dark");

  const setTheme = useCallback((nextTheme: FormaTheme) => {
    const normalizedTheme = normalizeTheme(nextTheme);
    setThemeState(normalizedTheme);
    applyTheme(normalizedTheme);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, normalizedTheme);
    } catch {
      // The active theme still applies when storage is unavailable.
    }
  }, []);

  useEffect(() => {
    const initialTheme = normalizeTheme(document.documentElement.dataset.theme);
    setThemeState(initialTheme);
    applyTheme(initialTheme);

    function syncTheme(event: StorageEvent) {
      if (event.key !== THEME_STORAGE_KEY) return;
      const nextTheme = normalizeTheme(event.newValue);
      setThemeState(nextTheme);
      applyTheme(nextTheme);
    }

    window.addEventListener("storage", syncTheme);
    return () => window.removeEventListener("storage", syncTheme);
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [setTheme, theme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider.");
  return value;
}
