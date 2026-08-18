"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  normalizeTheme,
  parseAutoThemeConfig,
  resolveAutoTheme,
  themeColorScheme,
  THEME_CONFIG_STORAGE_KEY,
  THEME_STORAGE_KEY,
  type AutoThemeConfig,
  type FormaTheme,
} from "./theme";
import { getDefaultLocationFromTimezone } from "./solar";

export interface SolarInfo {
  isDaylight: boolean;
  sunrise: Date;
  sunset: Date;
  solarNoon: Date;
  nextEvent: "sunrise" | "sunset";
  nextTime: Date;
  msRemaining: number;
}

export interface ThemeContextValue {
  theme: FormaTheme;
  themeMode: "manual" | "auto";
  autoConfig: AutoThemeConfig;
  solarInfo: SolarInfo | null;
  isLocating: boolean;
  locationError: string | null;
  setTheme: (theme: FormaTheme) => void;
  setThemeMode: (mode: "manual" | "auto") => void;
  setAutoConfig: (updater: Partial<AutoThemeConfig> | ((prev: AutoThemeConfig) => AutoThemeConfig)) => void;
  requestBrowserLocation: () => Promise<boolean>;
  setCustomLocation: (label: string, lat: number, lng: number) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyThemeToDocument(theme: FormaTheme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = themeColorScheme(theme);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<FormaTheme>("dark");
  const [autoConfig, setAutoConfigState] = useState<AutoThemeConfig>(() => ({
    mode: "manual",
    dayTheme: "light",
    nightTheme: "solarized-dark",
    locationMode: "auto",
    latitude: 37.7749,
    longitude: -122.4194,
    locationLabel: "San Francisco, CA, USA",
  }));
  const [solarInfo, setSolarInfo] = useState<SolarInfo | null>(null);
  const [isLocating, setIsLocating] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);

  const evaluateTheme = useCallback((config: AutoThemeConfig, explicitManualTheme?: FormaTheme) => {
    if (config.mode === "auto") {
      const { theme: autoResolvedTheme, solarTimes, transition } = resolveAutoTheme(config);
      setSolarInfo({
        isDaylight: solarTimes.isDaylight,
        sunrise: solarTimes.sunrise,
        sunset: solarTimes.sunset,
        solarNoon: solarTimes.solarNoon,
        nextEvent: transition.nextEvent,
        nextTime: transition.nextTime,
        msRemaining: transition.msRemaining,
      });
      setThemeState(autoResolvedTheme);
      applyThemeToDocument(autoResolvedTheme);
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, autoResolvedTheme);
      } catch {
        // ignore
      }
    } else {
      const activeManual = normalizeTheme(explicitManualTheme || document.documentElement.dataset.theme);
      const { solarTimes, transition } = resolveAutoTheme(config);
      setSolarInfo({
        isDaylight: solarTimes.isDaylight,
        sunrise: solarTimes.sunrise,
        sunset: solarTimes.sunset,
        solarNoon: solarTimes.solarNoon,
        nextEvent: transition.nextEvent,
        nextTime: transition.nextTime,
        msRemaining: transition.msRemaining,
      });
      setThemeState(activeManual);
      applyThemeToDocument(activeManual);
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, activeManual);
      } catch {
        // ignore
      }
    }
  }, []);

  const saveConfig = useCallback((newConfig: AutoThemeConfig) => {
    setAutoConfigState(newConfig);
    try {
      window.localStorage.setItem(THEME_CONFIG_STORAGE_KEY, JSON.stringify(newConfig));
    } catch {
      // ignore
    }
    evaluateTheme(newConfig);
  }, [evaluateTheme]);

  const setAutoConfig = useCallback((updater: Partial<AutoThemeConfig> | ((prev: AutoThemeConfig) => AutoThemeConfig)) => {
    setAutoConfigState((prev) => {
      const updated = typeof updater === "function" ? updater(prev) : { ...prev, ...updater };
      try {
        window.localStorage.setItem(THEME_CONFIG_STORAGE_KEY, JSON.stringify(updated));
      } catch {
        // ignore
      }
      evaluateTheme(updated);
      return updated;
    });
  }, [evaluateTheme]);

  const setTheme = useCallback((nextTheme: FormaTheme) => {
    const normalized = normalizeTheme(nextTheme);
    setAutoConfigState((prev) => {
      const updated: AutoThemeConfig = { ...prev, mode: "manual" };
      try {
        window.localStorage.setItem(THEME_CONFIG_STORAGE_KEY, JSON.stringify(updated));
        window.localStorage.setItem(THEME_STORAGE_KEY, normalized);
      } catch {
        // ignore
      }
      setThemeState(normalized);
      applyThemeToDocument(normalized);
      return updated;
    });
  }, []);

  const setThemeMode = useCallback((mode: "manual" | "auto") => {
    setAutoConfig((prev) => ({ ...prev, mode }));
  }, [setAutoConfig]);

  const setCustomLocation = useCallback((label: string, lat: number, lng: number) => {
    setLocationError(null);
    setAutoConfig((prev) => ({
      ...prev,
      locationMode: "custom",
      locationLabel: label,
      latitude: lat,
      longitude: lng,
    }));
  }, [setAutoConfig]);

  const requestBrowserLocation = useCallback(async (): Promise<boolean> => {
    if (typeof window === "undefined" || !("geolocation" in navigator)) {
      setLocationError("Geolocation is not supported by your browser.");
      return false;
    }

    setIsLocating(true);
    setLocationError(null);

    return new Promise<boolean>((resolve) => {
      navigator.geolocation.getCurrentPosition(
        async (position) => {
          const lat = position.coords.latitude;
          const lng = position.coords.longitude;
          let label = `${lat.toFixed(2)}°, ${lng.toFixed(2)}°`;

          try {
            const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}`, {
              headers: { "Accept-Language": "en" },
            });
            if (res.ok) {
              const data = await res.json();
              const city = data.address?.city || data.address?.town || data.address?.village || data.address?.municipality || data.address?.county;
              const country = data.address?.country;
              const state = data.address?.state;
              if (city && state && country === "United States") {
                label = `${city}, ${state}, USA`;
              } else if (city && country) {
                label = `${city}, ${country}`;
              } else if (data.display_name) {
                label = data.display_name.split(",").slice(0, 3).join(",").trim();
              }
            }
          } catch {
            // Keep coordinates label
          }

          setIsLocating(false);
          setAutoConfig((prev) => ({
            ...prev,
            locationMode: "auto",
            locationLabel: label,
            latitude: lat,
            longitude: lng,
          }));
          resolve(true);
        },
        (err) => {
          setIsLocating(false);
          let message = "Unable to retrieve your location.";
          if (err.code === err.PERMISSION_DENIED) {
            message = "Location permission was denied. You can search or enter your city manually.";
          } else if (err.code === err.POSITION_UNAVAILABLE) {
            message = "Location information is unavailable.";
          } else if (err.code === err.TIMEOUT) {
            message = "Location request timed out.";
          }
          setLocationError(message);
          resolve(false);
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
      );
    });
  }, [setAutoConfig]);

  useEffect(() => {
    let savedConfig: AutoThemeConfig | null = null;
    try {
      const raw = window.localStorage.getItem(THEME_CONFIG_STORAGE_KEY);
      if (raw) savedConfig = parseAutoThemeConfig(JSON.parse(raw));
    } catch {
      // ignore
    }

    if (!savedConfig) {
      const tzLocation = getDefaultLocationFromTimezone();
      savedConfig = {
        ...DEFAULT_AUTO_THEME_CONFIG,
        latitude: tzLocation.lat,
        longitude: tzLocation.lng,
        locationLabel: tzLocation.label,
      };
    }

    setAutoConfigState(savedConfig);
    evaluateTheme(savedConfig);

    function handleStorageChange(event: StorageEvent) {
      if (event.key === THEME_CONFIG_STORAGE_KEY) {
        try {
          const updated = parseAutoThemeConfig(event.newValue ? JSON.parse(event.newValue) : null);
          setAutoConfigState(updated);
          evaluateTheme(updated);
        } catch {
          // ignore
        }
      } else if (event.key === THEME_STORAGE_KEY) {
        const nextTheme = normalizeTheme(event.newValue);
        setThemeState(nextTheme);
        applyThemeToDocument(nextTheme);
      }
    }

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, [evaluateTheme]);

  useEffect(() => {
    const checkSolar = () => {
      setAutoConfigState((currentConfig) => {
        evaluateTheme(currentConfig);
        return currentConfig;
      });
    };

    const intervalId = window.setInterval(checkSolar, 30000);

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        checkSolar();
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", handleVisibility);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", handleVisibility);
    };
  }, [evaluateTheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      themeMode: autoConfig.mode,
      autoConfig,
      solarInfo,
      isLocating,
      locationError,
      setTheme,
      setThemeMode,
      setAutoConfig,
      requestBrowserLocation,
      setCustomLocation,
    }),
    [
      theme,
      autoConfig,
      solarInfo,
      isLocating,
      locationError,
      setTheme,
      setThemeMode,
      setAutoConfig,
      requestBrowserLocation,
      setCustomLocation,
    ],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider.");
  return value;
}
