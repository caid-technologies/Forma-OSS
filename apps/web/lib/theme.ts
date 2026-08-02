export const THEME_STORAGE_KEY = "forma-theme";

export type FormaTheme = "dark" | "light";

/**
 * Solarized Light tones by Ethan Schoonover (https://ethanschoonover.com/solarized/).
 * The light theme is built entirely from these values; the
 * `:root[data-theme="light"]` block in app/globals.css must stay in sync,
 * which test/theme.test.ts enforces.
 */
export const solarizedLight = {
  /** Primary background. */
  base3: "#fdf6e3",
  /** Background highlights. */
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
 * The accents Solarized publishes. Forma renders status text at 10px, and the
 * published accents only reach about 2.9:1 on base3, so the shipped accents
 * above are these hues scaled down in linear RGB until they clear 4.5:1. The
 * scaling is uniform across channels, so hue is preserved to within one degree,
 * which test/theme.test.ts asserts.
 */
export const solarizedPublishedAccents = {
  cyan: "#2aa198",
  green: "#859900",
  yellow: "#b58900",
  red: "#dc322f",
  violet: "#6c71c4",
} as const;

export function normalizeTheme(value: unknown): FormaTheme {
  return value === "light" ? "light" : "dark";
}

export const themeBootstrapScript = `
  try {
    var savedTheme = window.localStorage.getItem("${THEME_STORAGE_KEY}");
    var theme = savedTheme === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  } catch (error) {
    document.documentElement.dataset.theme = "dark";
    document.documentElement.style.colorScheme = "dark";
  }
`;
