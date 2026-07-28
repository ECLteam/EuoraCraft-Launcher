/**
 * Theme Management Hook
 *
 * Uses zustand store for theme state and manages CSS custom properties
 * on the document root element. Persists settings to localStorage and
 * watches for system preference changes.
 */

import { useEffect, useCallback, useMemo } from "react";
import { useShallow } from "zustand/shallow";
import { useAppStore, selectTheme } from "@/stores/appStore";
import { getThemeColorHSL, THEME_STORAGE_KEY } from "@/config/theme";
import type { ThemeMode, ThemeColor } from "@/config/theme";

// ---------------------------------------------------------------------------
// System Preference Media Query
// ---------------------------------------------------------------------------

function getSystemPreference(): "dark" | "light" {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

// ---------------------------------------------------------------------------
// CSS Variable Application
// ---------------------------------------------------------------------------

/**
 * Apply theme CSS custom properties to the document root element.
 */
function applyThemeCSS(color: ThemeColor, mode: ThemeMode, glassEffect: boolean) {
  const root = document.documentElement;
  const { primary, primaryHover, accent } = getThemeColorHSL(color);

  // Resolve the actual mode (system preference or explicit)
  const resolvedMode = mode === "system" ? getSystemPreference() : mode;

  // Set color scheme
  root.style.colorScheme = resolvedMode;
  root.classList.toggle("dark", resolvedMode === "dark");
  root.classList.toggle("light", resolvedMode === "light");

  // Apply theme colors as CSS custom properties
  root.style.setProperty("--theme-primary", primary);
  root.style.setProperty("--theme-primary-hover", primaryHover);
  root.style.setProperty("--theme-accent", accent);
  root.style.setProperty("--theme-color-name", color);

  // Glass effect toggle
  root.classList.toggle("glass-enabled", glassEffect);

  // Data attributes for querying
  root.setAttribute("data-theme-mode", resolvedMode);
  root.setAttribute("data-theme-color", color);
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTheme() {
  const theme = useAppStore(useShallow(selectTheme));

  // Derive the resolved mode (considering system preference)
  const resolvedMode = useMemo<"dark" | "light">(() => {
    return theme.mode === "system" ? getSystemPreference() : theme.mode;
  }, [theme.mode]);

  // Apply theme whenever it changes
  useEffect(() => {
    applyThemeCSS(theme.color, theme.mode, theme.glassEffect);
  }, [theme.color, theme.mode, theme.glassEffect]);

  // Listen for system preference changes
  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

    const handleChange = () => {
      if (theme.mode === "system") {
        applyThemeCSS(theme.color, "system", theme.glassEffect);
      }
    };

    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [theme.mode, theme.color, theme.glassEffect]);

  // Cycle theme mode
  const cycleMode = useCallback(() => {
    theme.cycleMode();
  }, [theme.cycleMode]);

  // Set a specific theme color
  const setColor = useCallback(
    (color: ThemeColor) => {
      theme.setColor(color);
    },
    [theme.setColor]
  );

  // Toggle glass effect
  const toggleGlass = useCallback(() => {
    theme.toggleGlass();
  }, [theme.toggleGlass]);

  // Toggle reduced motion
  const toggleReducedMotion = useCallback(() => {
    theme.toggleReducedMotion();
  }, [theme.toggleReducedMotion]);

  // Get the next mode in the cycle (for display)
  const nextMode = useMemo<ThemeMode>(() => {
    const modes: ThemeMode[] = ["system", "dark", "light"];
    const idx = modes.indexOf(theme.mode);
    return modes[(idx + 1) % modes.length];
  }, [theme.mode]);

  return {
    /** Current theme mode setting */
    mode: theme.mode,
    /** Resolved mode (dark/light, considering system) */
    resolvedMode,
    /** Current theme color preset */
    color: theme.color,
    /** Whether glass morphism is enabled */
    glassEffect: theme.glassEffect,
    /** Whether reduced motion is active */
    reducedMotion: theme.reducedMotion,
    /** Set the theme mode */
    setMode: theme.setMode,
    /** Cycle to the next theme mode */
    cycleMode,
    /** Set the theme color preset */
    setColor,
    /** Toggle glass effect */
    toggleGlass,
    /** Toggle reduced motion */
    toggleReducedMotion,
    /** The next mode in the cycle (for UI hints) */
    nextMode,
    /** Whether the current mode is "system" */
    isSystem: theme.mode === "system",
    /** Whether the resolved mode is dark */
    isDark: resolvedMode === "dark",
  };
}

// ---------------------------------------------------------------------------
// Theme Initialization (called once at app startup)
// ---------------------------------------------------------------------------

/**
 * Initialize the theme on app startup. Reads persisted settings from
 * localStorage and applies them immediately to prevent flash.
 */
export function initializeTheme(): void {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw) {
      const settings = JSON.parse(raw);
      const state = settings?.state;
      if (state) {
        applyThemeCSS(
          state.themeColor ?? "blue",
          state.themeMode ?? "dark",
          state.glassEffect ?? true
        );
        return;
      }
    }
  } catch {
    // Ignore parse errors, fall through to defaults
  }

  // Apply defaults
  applyThemeCSS("blue", "dark", true);
}