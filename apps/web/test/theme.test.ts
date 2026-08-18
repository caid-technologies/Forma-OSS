import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  arcticLight,
  DEFAULT_AUTO_THEME_CONFIG,
  FORMA_THEMES,
  mechanicalSceneAppearance,
  normalizeTheme,
  parseAutoThemeConfig,
  resolveAutoTheme,
  sceneAppearanceForTheme,
  solarizedDark,
  solarizedLight,
  solarizedPublishedAccents,
  themeBootstrapScript,
  themeColorScheme,
  THEME_STORAGE_KEY,
} from "../lib/theme";

const globalsCss = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

/** The declarations inside a single `:root[data-theme="..."]` block. */
function themeBlock(theme: string) {
  const start = globalsCss.indexOf(`:root[data-theme="${theme}"] {`);
  assert.notEqual(start, -1, `no :root block for the ${theme} theme`);
  return globalsCss.slice(start, globalsCss.indexOf("}", start));
}

/** Every rule that scopes itself to a theme, excluding the `:root` palette blocks. */
function scopedRules() {
  const rules: Array<{ selector: string; declarations: string }> = [];
  for (const chunk of globalsCss.split("}")) {
    const brace = chunk.indexOf("{");
    if (brace === -1) continue;
    const selector = chunk.slice(0, brace);
    if (!selector.includes("data-theme=") || selector.includes(":root[data-theme=")) continue;
    rules.push({ selector, declarations: chunk.slice(brace + 1) });
  }
  assert.ok(rules.length > 0, "no theme scoped rules were found");
  return rules;
}

function channels(hex: string) {
  return [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16));
}

function relativeLuminance(hex: string) {
  const [red, green, blue] = channels(hex).map((value) => {
    const channel = value / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrastRatio(foreground: string, background: string) {
  const [lighter, darker] = [relativeLuminance(foreground), relativeLuminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

function hueDegrees(hex: string) {
  const [red, green, blue] = channels(hex).map((value) => value / 255);
  const max = Math.max(red, green, blue);
  const span = max - Math.min(red, green, blue);
  if (span === 0) return 0;
  const sector = max === red ? ((green - blue) / span) % 6 : max === green ? (blue - red) / span + 2 : (red - green) / span + 4;
  return (sector * 60 + 360) % 360;
}

test("theme preferences use a stable local storage key", () => {
  assert.equal(THEME_STORAGE_KEY, "forma-theme");
});

test("theme preferences accept every known theme and default the rest to dark", () => {
  assert.equal(normalizeTheme("light"), "light");
  assert.equal(normalizeTheme("arctic"), "arctic");
  assert.equal(normalizeTheme("solarized-dark"), "solarized-dark");
  assert.equal(normalizeTheme("dark"), "solarized-dark");
  assert.equal(normalizeTheme(null), "solarized-dark");
  assert.equal(normalizeTheme("system"), "solarized-dark");
  assert.equal(normalizeTheme("solarized"), "solarized-dark");
});

test("every theme resolves to a native colour scheme", () => {
  // `color-scheme: arctic` is not a thing, so the theme id cannot be passed through.
  assert.equal(themeColorScheme("solarized-dark"), "dark");
  assert.equal(themeColorScheme("dark"), "dark");
  assert.equal(themeColorScheme("light"), "light");
  assert.equal(themeColorScheme("arctic"), "light");
});

test("the theme bootstrap script restores every known theme", () => {
  for (const theme of FORMA_THEMES) {
    assert.ok(themeBootstrapScript.includes(`"${theme}"`), `${theme} is missing from the bootstrap script`);
  }
  // It must not assign the theme id straight to colorScheme.
  assert.doesNotMatch(themeBootstrapScript, /colorScheme = theme;/);
});

test("the base tones are the published Solarized Light values", () => {
  assert.equal(solarizedLight.base3, "#fdf6e3");
  assert.equal(solarizedLight.base2, "#eee8d5");
  assert.equal(solarizedLight.base1, "#93a1a1");
  assert.equal(solarizedLight.base00, "#657b83");
  assert.equal(solarizedLight.base01, "#586e75");
  assert.equal(solarizedLight.base02, "#073642");
});

test("the shipped Solarized accents keep the published hues", () => {
  for (const [name, published] of Object.entries(solarizedPublishedAccents)) {
    const shipped = solarizedLight[name as keyof typeof solarizedPublishedAccents];
    const drift = Math.abs(hueDegrees(shipped) - hueDegrees(published));
    assert.ok(Math.min(drift, 360 - drift) <= 1, `${name} drifted ${drift.toFixed(2)} degrees from ${published}`);
  }
});

test("every Solarized accent clears WCAG AA for normal text on the panel background", () => {
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

test("every Solarized text tier stays legible on the panel background", () => {
  // base01 and base02 clear WCAG AA for normal text. base00 is Solarized's own
  // primary content tone and lands just under it by design, so it is pinned to
  // its published value rather than silently darkened.
  assert.ok(contrastRatio(solarizedLight.base02, solarizedLight.base3) >= 4.5);
  assert.ok(contrastRatio(solarizedLight.base01, solarizedLight.base3) >= 4.5);
  assert.ok(contrastRatio(solarizedLight.base00, solarizedLight.base3) >= 4.0);
});

test("the Solarized block declares the exported palette", () => {
  const block = themeBlock("light");
  assert.match(block, new RegExp(`--forma-page: ${solarizedLight.base2};`));
  assert.match(block, new RegExp(`--forma-surface: ${solarizedLight.base3};`));
  assert.match(block, new RegExp(`--forma-text: ${solarizedLight.base01};`));
  assert.match(block, new RegExp(`--forma-text-strong: ${solarizedLight.base02};`));
  assert.match(block, new RegExp(`--forma-text-muted: ${solarizedLight.base00};`));
  assert.match(block, /--forma-selected-wash-alpha: 0\.07;/);
  // Rules and wells are base1 at low alpha so they track whatever sits behind them.
  const [red, green, blue] = channels(solarizedLight.base1);
  assert.match(block, new RegExp(`--forma-surface-muted: rgb\\(${red} ${green} ${blue} / 0\\.18\\);`));
  assert.match(block, new RegExp(`--forma-border: rgb\\(${red} ${green} ${blue} / 0\\.45\\);`));
  for (const [name, hex] of Object.entries({
    cyan: solarizedLight.cyan,
    green: solarizedLight.green,
    yellow: solarizedLight.yellow,
    red: solarizedLight.red,
    violet: solarizedLight.violet,
  })) {
    assert.match(block, new RegExp(`--forma-${name}-rgb: ${channels(hex).join(" ")};`), `${name} is missing`);
  }
});

test("the Arctic block preserves the slate theme Forma shipped before Solarized", () => {
  const block = themeBlock("arctic");
  assert.match(block, new RegExp(`--forma-page: ${arcticLight.page};`));
  assert.match(block, new RegExp(`--forma-surface: ${arcticLight.surface};`));
  assert.match(block, new RegExp(`--forma-surface-muted: ${arcticLight.surfaceMuted};`));
  assert.match(block, new RegExp(`--forma-border: ${arcticLight.border};`));
  assert.match(block, new RegExp(`--forma-text: ${arcticLight.textStrong};`));
  assert.match(block, new RegExp(`--forma-text-body: ${arcticLight.textBody};`));
  assert.match(block, new RegExp(`--forma-text-secondary: ${arcticLight.textSecondary};`));
  assert.match(block, new RegExp(`--forma-text-muted: ${arcticLight.textMuted};`));
  assert.match(block, /--forma-selected-wash-alpha: 0\.18;/);
  for (const [name, hex] of Object.entries({
    cyan: arcticLight.cyan,
    green: arcticLight.green,
    yellow: arcticLight.yellow,
    red: arcticLight.red,
    violet: arcticLight.violet,
  })) {
    assert.match(block, new RegExp(`--forma-${name}-rgb: ${channels(hex).join(" ")};`), `${name} is missing`);
    // Arctic tinted the quiet 50 and 100 steps with the accent itself; Solarized does not.
    assert.match(block, new RegExp(`--forma-${name}-soft: ${hex};`), `${name} soft tone is missing`);
  }
});

test("every Arctic tone clears WCAG AA for normal text on its own page", () => {
  for (const [name, hex] of Object.entries(arcticLight)) {
    if (["page", "surface", "surfaceMuted", "border"].includes(name)) continue;
    const ratio = contrastRatio(hex, arcticLight.page);
    assert.ok(ratio >= 4.2, `${name} ${hex} is ${ratio.toFixed(2)}:1 on the Arctic page`);
  }
});

test("the Solarized Dark+ block declares the exported palette", () => {
  const block = themeBlock("solarized-dark");
  assert.match(block, new RegExp(`--forma-page: ${solarizedDark.base03};`));
  assert.match(block, new RegExp(`--forma-surface: ${solarizedDark.base04};`));
  assert.match(block, new RegExp(`--forma-surface-muted: ${solarizedDark.base02};`));
  assert.match(block, new RegExp(`--forma-text: ${solarizedDark.base0};`));
  assert.match(block, new RegExp(`--forma-text-strong: ${solarizedDark.base3};`));
  assert.match(block, new RegExp(`--forma-text-secondary: ${solarizedDark.base1};`));
  assert.match(block, new RegExp(`--forma-text-muted: ${solarizedDark.base00};`));
  assert.match(block, /--forma-selected-wash-alpha: 0\.15;/);
  for (const [name, hex] of Object.entries({
    cyan: solarizedDark.cyan,
    green: solarizedDark.green,
    yellow: solarizedDark.yellow,
    red: solarizedDark.red,
    violet: solarizedDark.violet,
  })) {
    assert.match(block, new RegExp(`--forma-${name}-rgb: ${channels(hex).join(" ")};`), `${name} is missing`);
    assert.match(block, new RegExp(`--forma-${name}-soft: ${hex};`), `${name} soft tone is missing`);
  }
});

test("no override rule is scoped to a single light theme", () => {
  // The two light themes share every rule and differ only in their variables.
  // A rule that names one and not the other is a drift bug.
  for (const { selector } of scopedRules()) {
    assert.equal(
      selector.includes('[data-theme="light"]'),
      selector.includes('[data-theme="arctic"]'),
      `this selector covers only one light theme:\n${selector.trim()}`,
    );
  }
});

test("shared rules resolve their colours through variables, not literals", () => {
  for (const { selector, declarations } of scopedRules()) {
    assert.doesNotMatch(
      declarations,
      /#[0-9a-f]{3,8}\b/i,
      `a literal colour leaked into a shared rule:\n${selector.trim()}\n{${declarations}}`,
    );
  }
});

test("light-theme interaction states use theme tokens instead of dark utilities", () => {
  const rules = scopedRules();
  const sidebarHover = rules.find(({ selector }) => selector.includes("hover:bg-[#17181d]"));
  assert.ok(sidebarHover, "the sidebar hover utility is not translated for light themes");
  assert.match(sidebarHover.declarations, /background-color: var\(--forma-surface-muted\)/);

  const selectedWash = rules.find(({ selector }) => selector.includes("bg-cyan-300/10"));
  assert.ok(selectedWash, "the selected-state wash rule is missing");
  assert.match(selectedWash.declarations, /var\(--forma-selected-wash-alpha\)/);

  const groupHoverText = rules.find(({ selector }) => selector.includes("group-hover:text-zinc-100"));
  assert.ok(groupHoverText, "group-hover light text is not translated for light themes");
  assert.match(groupHoverText.selector, /\.group:hover/);
  assert.doesNotMatch(groupHoverText.selector, /:where\(/);
  assert.match(groupHoverText.declarations, /color: var\(--forma-text-strong\)/);

  const whiteWash = rules.find(({ selector }) => selector.includes("hover:bg-white/5"));
  assert.ok(whiteWash, "the white hover wash is not translated for light themes");
  assert.match(whiteWash.declarations, /background-color: var\(--forma-surface-muted\)/);
});

test("the 3D canvas appearance is distinct for every settings theme", () => {
  const backgrounds = new Set(FORMA_THEMES.map((theme) => mechanicalSceneAppearance[theme].background));
  assert.equal(backgrounds.size, FORMA_THEMES.length);

  assert.equal(mechanicalSceneAppearance["solarized-dark"].background, solarizedDark.base03);
  assert.equal(mechanicalSceneAppearance.light.background, solarizedLight.base2);
  assert.equal(mechanicalSceneAppearance.arctic.background, arcticLight.page);

  assert.ok(mechanicalSceneAppearance["solarized-dark"].ambientIntensity < mechanicalSceneAppearance.light.ambientIntensity);
  assert.ok(mechanicalSceneAppearance.light.selectedEdge !== mechanicalSceneAppearance["solarized-dark"].selectedEdge);
  assert.equal(sceneAppearanceForTheme("arctic").background, arcticLight.page);
});
