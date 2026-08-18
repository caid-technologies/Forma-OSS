import { calculateSolarTimes, getDefaultLocationFromTimezone, getNextSolarTransition, type SolarTimes, type SolarTransition } from "./solar";

export const THEME_STORAGE_KEY = "forma-theme";
export const THEME_CONFIG_STORAGE_KEY = "forma-theme-auto-config";

export const FORMA_THEMES = ["solarized-dark", "light", "arctic"] as const;

export type FormaTheme = (typeof FORMA_THEMES)[number];

export interface AutoThemeConfig {
  mode: "manual" | "auto";
  dayTheme: FormaTheme;
  nightTheme: FormaTheme;
  locationMode: "auto" | "custom";
  latitude: number;
  longitude: number;
  locationLabel: string;
}

export const DEFAULT_AUTO_THEME_CONFIG: AutoThemeConfig = {
  mode: "manual",
  dayTheme: "light",
  nightTheme: "solarized-dark",
  locationMode: "auto",
  latitude: 37.7749,
  longitude: -122.4194,
  locationLabel: "San Francisco, CA, USA",
};

/** `color-scheme` only understands native schemes, not individual theme IDs. */
export function themeColorScheme(theme: FormaTheme | "dark"): "dark" | "light" {
  return theme === "dark" || theme === "solarized-dark" ? "dark" : "light";
}

/**
 * Solarized Light+ tones based on Ethan Schoonover and Ryan Olson's VS Code Solarized theme
 * (https://marketplace.visualstudio.com/items?itemName=ryanolsonx.solarized).
 * Mirrors `:root[data-theme="light"]` in app/globals.css.
 */
export const solarizedLight = {
  /** Primary background. */
  base3: "#fdf6e3",
  /** Background highlights and surfaces. */
  base2: "#eee8d5",
  /** Secondary content, and the source tone for rules and recessed wells. */
  base1: "#93a1a1",
  /** Primary content. */
  base00: "#657b83",
  /** Emphasized content. */
  base01: "#586e75",
  /** Darkest tone, used here for headings and inverted button fills. */
  base02: "#073642",
  cyan: "#1f7e77",
  green: "#687900",
  yellow: "#8f6c00",
  red: "#d6302e",
  violet: "#656ab9",
} as const;

/**
 * Solarized Dark+ tones based on Ryan Olson's VS Code Solarized theme
 * (https://marketplace.visualstudio.com/items?itemName=ryanolsonx.solarized).
 * Mirrors `:root[data-theme="solarized-dark"]` in app/globals.css.
 */
export const solarizedDark = {
  /** Primary background (editor/page base03). */
  base03: "#002b36",
  /** Dark teal surface tone (sidebar, panels, chrome). */
  base04: "#001f26",
  /** Recessed surface and input background. */
  base02: "#073642",
  /** Subtle border and secondary tone. */
  base01: "#586e75",
  /** Muted text and structural borders. */
  base00: "#657b83",
  /** Primary body text tone. */
  base0: "#839496",
  /** Secondary content tone. */
  base1: "#93a1a1",
  /** Brightest emphasis tone. */
  base3: "#fdf6e3",
  cyan: "#2aa198",
  green: "#859900",
  yellow: "#b58900",
  red: "#dc322f",
  violet: "#6c71c4",
  blue: "#268bd2",
  orange: "#cb4b16",
} as const;

/**
 * The accents Solarized publishes. Forma renders status text at 10px, and the
 * published accents only reach about 2.9:1 on base3, so the shipped accents
 * in Solarized Light are scaled down in linear RGB until they clear 4.5:1.
 */
export const solarizedPublishedAccents = {
  cyan: "#2aa198",
  green: "#859900",
  yellow: "#b58900",
  red: "#dc322f",
  violet: "#6c71c4",
} as const;

/**
 * The cool slate light theme Forma shipped before Solarized, kept as a separate
 * choice. Mirrors the `:root[data-theme="arctic"]` block in app/globals.css.
 */
export const arcticLight = {
  page: "#eef2f7",
  surface: "#ffffff",
  surfaceMuted: "#f8fafc",
  border: "#cbd5e1",
  textStrong: "#0f172a",
  textBody: "#334155",
  textSecondary: "#475569",
  textMuted: "#64748b",
  cyan: "#0e7490",
  green: "#047857",
  yellow: "#a16207",
  red: "#be123c",
  violet: "#7e22ce",
} as const;

/** Lighting and clear-color for the 3D canvas so it matches each appearance. */
export type MechanicalSceneAppearance = {
  background: string;
  fog: string;
  ambientIntensity: number;
  hemisphereSky: string;
  hemisphereGround: string;
  hemisphereIntensity: number;
  keyLight: string;
  keyLightIntensity: number;
  selectedEdge: string;
  fillOpacity: number;
  selectedFillOpacity: number;
};

export const mechanicalSceneAppearance: Record<FormaTheme, MechanicalSceneAppearance> = {
  "solarized-dark": {
    background: solarizedDark.base03,
    fog: solarizedDark.base03,
    ambientIntensity: 0.72,
    hemisphereSky: solarizedDark.base02,
    hemisphereGround: solarizedDark.base04,
    hemisphereIntensity: 0.55,
    keyLight: solarizedDark.base1,
    keyLightIntensity: 0.62,
    selectedEdge: solarizedDark.base3,
    fillOpacity: 0.06,
    selectedFillOpacity: 0.16,
  },
  light: {
    background: solarizedLight.base2,
    fog: solarizedLight.base2,
    ambientIntensity: 1.05,
    hemisphereSky: solarizedLight.base3,
    hemisphereGround: solarizedLight.base2,
    hemisphereIntensity: 0.7,
    keyLight: solarizedLight.base3,
    keyLightIntensity: 0.85,
    selectedEdge: solarizedLight.base02,
    fillOpacity: 0.12,
    selectedFillOpacity: 0.22,
  },
  arctic: {
    background: arcticLight.page,
    fog: arcticLight.page,
    ambientIntensity: 1.12,
    hemisphereSky: arcticLight.surface,
    hemisphereGround: arcticLight.page,
    hemisphereIntensity: 0.78,
    keyLight: arcticLight.surface,
    keyLightIntensity: 0.9,
    selectedEdge: arcticLight.textStrong,
    fillOpacity: 0.1,
    selectedFillOpacity: 0.2,
  },
};

export function sceneAppearanceForTheme(theme: FormaTheme): MechanicalSceneAppearance {
  return mechanicalSceneAppearance[theme] || mechanicalSceneAppearance["solarized-dark"];
}

export function normalizeTheme(value: unknown): FormaTheme {
  if (value === "solarized-light" || value === "light") return "light";
  if (value === "arctic") return "arctic";
  if (value === "solarized-dark" || value === "dark") return "solarized-dark";
  return FORMA_THEMES.includes(value as FormaTheme) ? (value as FormaTheme) : "solarized-dark";
}

export function parseAutoThemeConfig(raw: unknown): AutoThemeConfig {
  const fallback = {
    ...DEFAULT_AUTO_THEME_CONFIG,
    ...getDefaultLocationFromTimezone(),
  };

  if (!raw || typeof raw !== "object") return fallback;
  const obj = raw as Record<string, unknown>;

  const mode = obj.mode === "auto" ? "auto" : "manual";
  const dayTheme = normalizeTheme(obj.dayTheme || "light");
  const nightTheme = normalizeTheme(obj.nightTheme || "solarized-dark");
  const locationMode = obj.locationMode === "custom" ? "custom" : "auto";
  const latitude = typeof obj.latitude === "number" && !isNaN(obj.latitude) ? obj.latitude : fallback.latitude;
  const longitude = typeof obj.longitude === "number" && !isNaN(obj.longitude) ? obj.longitude : fallback.longitude;
  const locationLabel = typeof obj.locationLabel === "string" && obj.locationLabel ? obj.locationLabel : fallback.locationLabel;

  return {
    mode,
    dayTheme,
    nightTheme,
    locationMode,
    latitude,
    longitude,
    locationLabel,
  };
}

export function resolveAutoTheme(
  config: AutoThemeConfig,
  date: Date = new Date(),
): {
  theme: FormaTheme;
  isDaylight: boolean;
  solarTimes: SolarTimes;
  transition: SolarTransition;
} {
  const solarTimes = calculateSolarTimes(config.latitude, config.longitude, date);
  const transition = getNextSolarTransition(config.latitude, config.longitude, date);
  const theme = solarTimes.isDaylight ? config.dayTheme : config.nightTheme;

  return {
    theme,
    isDaylight: solarTimes.isDaylight,
    solarTimes,
    transition,
  };
}

export const themeBootstrapScript = `
  try {
    var rawConfig = window.localStorage.getItem("${THEME_CONFIG_STORAGE_KEY}");
    var config = null;
    if (rawConfig) {
      try { config = JSON.parse(rawConfig); } catch (e) {}
    }
    var theme = "solarized-dark";
    if (config && config.mode === "auto" && typeof config.latitude === "number" && typeof config.longitude === "number") {
      var now = new Date();
      var lat = config.latitude;
      var lng = config.longitude;
      var d = (now.getTime() / 86400000 + 2440587.5) - 2451545.0 + 0.0008;
      var n = Math.round(d - lng / 360);
      var jStar = 2451545.0 + n + 0.0008 - lng / 360;
      var m = (357.5291 + 0.98560028 * (jStar - 2451545.0)) % 360;
      var mRad = (m < 0 ? m + 360 : m) * (Math.PI / 180);
      var c = 1.9148 * Math.sin(mRad) + 0.02 * Math.sin(2 * mRad) + 0.0003 * Math.sin(3 * mRad);
      var lam = (m + c + 180 + 102.9372) % 360;
      var lamRad = (lam < 0 ? lam + 360 : lam) * (Math.PI / 180);
      var jTransit = jStar + 0.0053 * Math.sin(mRad) - 0.0069 * Math.sin(2 * lamRad);
      var sinDelta = Math.sin(lamRad) * Math.sin(23.44 * (Math.PI / 180));
      var cosDelta = Math.sqrt(Math.max(0, 1 - sinDelta * sinDelta));
      var latRad = lat * (Math.PI / 180);
      var cosH0 = (Math.cos(90.833 * (Math.PI / 180)) - Math.sin(latRad) * sinDelta) / (Math.cos(latRad) * cosDelta);
      var isDay = false;
      if (cosH0 <= -1) {
        isDay = true;
      } else if (cosH0 >= 1) {
        isDay = false;
      } else {
        var h0 = Math.acos(cosH0) * (180 / Math.PI);
        var riseMs = (jTransit - h0 / 360 - 2440587.5) * 86400000;
        var setMs = (jTransit + h0 / 360 - 2440587.5) * 86400000;
        var curMs = now.getTime();
        isDay = curMs >= riseMs && curMs < setMs;
      }
      var validThemes = ["solarized-dark","light","arctic"];
      var dayTh = validThemes.indexOf(config.dayTheme) !== -1 ? config.dayTheme : "light";
      var nightTh = validThemes.indexOf(config.nightTheme) !== -1 ? config.nightTheme : "solarized-dark";
      theme = isDay ? dayTh : nightTh;
    } else {
      var savedTheme = window.localStorage.getItem("${THEME_STORAGE_KEY}");
      if (savedTheme === "dark" || savedTheme === "solarized-dark") {
        theme = "solarized-dark";
      } else if (savedTheme === "light" || savedTheme === "solarized-light") {
        theme = "light";
      } else if (savedTheme === "arctic") {
        theme = "arctic";
      } else {
        theme = "solarized-dark";
      }
    }
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = (theme === "solarized-dark" || theme === "dark") ? "dark" : "light";
  } catch (error) {
    document.documentElement.dataset.theme = "solarized-dark";
    document.documentElement.style.colorScheme = "dark";
  }
`;
