import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { normalizeTheme, solarizedLight, solarizedPublishedAccents, THEME_STORAGE_KEY } from "../lib/theme";

const globalsCss = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
// Only the rules scoped to the light theme; the dark theme keeps its own colours.
const lightThemeCss = globalsCss
  .split("}")
  .filter((rule) => rule.includes('[data-theme="light"]'))
  .join("}\n");

function relativeLuminance(hex: string) {
  const [red, green, blue] = [1, 3, 5].map((offset) => {
    const channel = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrastRatio(foreground: string, background: string) {
  const [lighter, darker] = [relativeLuminance(foreground), relativeLuminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

function hueDegrees(hex: string) {
  const [red, green, blue] = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const max = Math.max(red, green, blue);
  const span = max - Math.min(red, green, blue);
  if (span === 0) return 0;
  const sector = max === red ? ((green - blue) / span) % 6 : max === green ? (blue - red) / span + 2 : (red - green) / span + 4;
  return (sector * 60 + 360) % 360;
}

test("theme preferences use a stable local storage key", () => {
  assert.equal(THEME_STORAGE_KEY, "forma-theme");
});

test("theme preferences accept light and default every other value to dark", () => {
  assert.equal(normalizeTheme("light"), "light");
  assert.equal(normalizeTheme("dark"), "dark");
  assert.equal(normalizeTheme(null), "dark");
  assert.equal(normalizeTheme("system"), "dark");
});

test("the base tones are the published Solarized Light values", () => {
  assert.equal(solarizedLight.base3, "#fdf6e3");
  assert.equal(solarizedLight.base2, "#eee8d5");
  assert.equal(solarizedLight.base1, "#93a1a1");
  assert.equal(solarizedLight.base00, "#657b83");
  assert.equal(solarizedLight.base01, "#586e75");
  assert.equal(solarizedLight.base02, "#073642");
});

test("the shipped accents keep the published Solarized hues", () => {
  for (const [name, published] of Object.entries(solarizedPublishedAccents)) {
    const shipped = solarizedLight[name as keyof typeof solarizedPublishedAccents];
    const drift = Math.abs(hueDegrees(shipped) - hueDegrees(published));
    assert.ok(Math.min(drift, 360 - drift) <= 1, `${name} drifted ${drift.toFixed(2)} degrees from ${published}`);
  }
});

test("the light theme variables are built from the exported palette", () => {
  assert.match(lightThemeCss, new RegExp(`--forma-page: ${solarizedLight.base2};`));
  assert.match(lightThemeCss, new RegExp(`--forma-surface: ${solarizedLight.base3};`));
  assert.match(lightThemeCss, new RegExp(`--forma-text: ${solarizedLight.base01};`));
  // Rules and wells are base1 at low alpha so they track whatever sits behind them.
  assert.match(lightThemeCss, /--forma-surface-muted: rgb\(147 161 161 \/ 0\.18\);/);
  assert.match(lightThemeCss, /--forma-border: rgb\(147 161 161 \/ 0\.45\);/);
});

test("no colour from the retired slate light theme survives", () => {
  for (const retired of ["#eef2f7", "#ffffff", "#f8fafc", "#cbd5e1", "#0f172a", "#334155", "#475569", "#64748b", "#94a3b8", "#0e7490", "#047857", "#a16207", "#be123c", "#7e22ce"]) {
    assert.doesNotMatch(lightThemeCss, new RegExp(retired, "i"), `${retired} is still referenced`);
  }
});

test("every light theme text tier stays legible on the panel background", () => {
  // base01 and base02 clear WCAG AA for normal text. base00 is Solarized's own
  // primary content tone and lands just under it by design, so it is pinned to
  // its published value rather than silently darkened.
  assert.ok(contrastRatio(solarizedLight.base02, solarizedLight.base3) >= 4.5);
  assert.ok(contrastRatio(solarizedLight.base01, solarizedLight.base3) >= 4.5);
  assert.ok(contrastRatio(solarizedLight.base00, solarizedLight.base3) >= 4.0);
});

test("every accent clears WCAG AA for normal text on the panel background", () => {
  // Forma renders status labels at 10px, which is why the published accents are
  // darkened: each of them measures about 2.9:1 here.
  for (const [name, published] of Object.entries(solarizedPublishedAccents)) {
    const shipped = solarizedLight[name as keyof typeof solarizedPublishedAccents];
    const ratio = contrastRatio(shipped, solarizedLight.base3);
    assert.ok(ratio >= 4.5, `${name} ${shipped} is ${ratio.toFixed(2)}:1 on base3`);
    assert.ok(
      contrastRatio(published, solarizedLight.base3) < 4.5,
      `${name} no longer needs darkening; ship the published ${published} instead`,
    );
  }
});

test("the light theme stylesheet uses the shipped accents", () => {
  for (const accent of [solarizedLight.cyan, solarizedLight.green, solarizedLight.yellow, solarizedLight.red, solarizedLight.violet]) {
    assert.match(lightThemeCss, new RegExp(`color: ${accent};`), `${accent} is missing from the light overrides`);
  }
});
