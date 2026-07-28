/**
 * Theme Configuration
 *
 * Defines preset theme colors, mode options, and default settings
 * for the EuoraCraft Launcher theme system.
 */

// ---------------------------------------------------------------------------
// Theme Color Presets
// ---------------------------------------------------------------------------
export const THEME_COLORS = {
  blue: {
    name: "海洋蓝",
    primary: "217 91% 60%",
    primaryHover: "217 91% 65%",
    accent: "199 89% 48%",
  },
  purple: {
    name: "星云紫",
    primary: "262 83% 58%",
    primaryHover: "262 83% 63%",
    accent: "292 84% 60%",
  },
  green: {
    name: "翡翠绿",
    primary: "142 71% 45%",
    primaryHover: "142 71% 50%",
    accent: "160 84% 39%",
  },
  orange: {
    name: "日落橙",
    primary: "25 95% 53%",
    primaryHover: "25 95% 58%",
    accent: "35 92% 50%",
  },
  pink: {
    name: "樱花粉",
    primary: "330 81% 60%",
    primaryHover: "330 81% 65%",
    accent: "340 82% 52%",
  },
  teal: {
    name: "青碧色",
    primary: "173 80% 40%",
    primaryHover: "173 80% 45%",
    accent: "188 86% 53%",
  },
} as const;

// ---------------------------------------------------------------------------
// Theme Modes
// ---------------------------------------------------------------------------
export const THEME_MODES = ["system", "dark", "light"] as const;
export type ThemeMode = (typeof THEME_MODES)[number];
export type ThemeColor = keyof typeof THEME_COLORS;

// ---------------------------------------------------------------------------
// Default Theme Settings
// ---------------------------------------------------------------------------
export const DEFAULT_THEME_MODE: ThemeMode = "dark";
export const DEFAULT_THEME_COLOR: ThemeColor = "blue";

export interface ThemeSettings {
  mode: ThemeMode;
  color: ThemeColor;
}

export const DEFAULT_THEME_SETTINGS: ThemeSettings = {
  mode: DEFAULT_THEME_MODE,
  color: DEFAULT_THEME_COLOR,
};

// ---------------------------------------------------------------------------
// Theme Color HSL Value Helper
// ---------------------------------------------------------------------------
/**
 * Returns the HSL values for a given theme color key.
 * Returns the default (blue) values if the key is not found.
 */
export function getThemeColorHSL(key: ThemeColor): {
  primary: string;
  primaryHover: string;
  accent: string;
} {
  return THEME_COLORS[key] ?? THEME_COLORS.blue;
}

// ---------------------------------------------------------------------------
// Storage Keys
// ---------------------------------------------------------------------------
export const THEME_STORAGE_KEY = "euoracraft-theme-settings";