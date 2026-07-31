export const THEME_STORAGE_KEY = "forma-theme";

export type FormaTheme = "dark" | "light";

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
