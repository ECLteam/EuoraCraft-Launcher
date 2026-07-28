/**
 * Settings Store
 *
 * Zustand store managing launcher settings with persistence to
 * localStorage. Covers game, download, UI, and theme settings.
 *
 * Uses the transport layer for backend communication and
 * provides default values when running in showcase mode.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { transport } from "@/api/transport";
import { isShowcaseMode } from "@/api/transport";
import type {
  LauncherConfig,
  GameConfig,
  ThemeConfig,
  DownloadConfig,
  UiConfig,
} from "@/types/api";
import type { ThemeColor, ThemeMode } from "@/config/theme";
import type { DownloadSource } from "@/config/version";

// ===========================================================================
// Default Settings
// ===========================================================================

/** Default game configuration */
const DEFAULT_GAME: GameConfig = {
  javaPath: "",
  minMemory: 2048,
  maxMemory: 4096,
  jvmArgs: [
    "-XX:+UseG1GC",
    "-XX:+ParallelRefProcEnabled",
    "-XX:MaxGCPauseMillis=200",
    "-XX:+UnlockExperimentalVMOptions",
    "-XX:+DisableExplicitGC",
    "-XX:+AlwaysPreTouch",
  ],
  windowWidth: 1280,
  windowHeight: 720,
  fullscreen: false,
  gameDir: ".minecraft",
  keepLauncherOpen: false,
  showGameOutput: true,
  downloadSource: "bmclapi",
  useIsolation: true,
};

/** Default download configuration */
const DEFAULT_DOWNLOAD: DownloadConfig = {
  maxConcurrent: 5,
  retryCount: 3,
  speedLimit: 0,
  source: "bmclapi",
  verifyHash: true,
};

/** Default UI configuration */
const DEFAULT_UI: UiConfig = {
  language: "zh-CN",
  sidebarCollapsed: false,
  showTitleBar: true,
  useTopNav: false,
  enableBlur: true,
};

/** Default theme configuration */
const DEFAULT_THEME: ThemeConfig = {
  mode: "dark",
  color: "blue",
  glassEffect: true,
  reducedMotion: false,
  uiScale: 1.0,
};

// ===========================================================================
// State Interface
// ===========================================================================

export interface SettingsState {
  // ---- Game Settings ----
  game: GameConfig;

  // ---- Download Settings ----
  download: DownloadConfig;

  // ---- UI Settings ----
  ui: UiConfig;

  // ---- Theme Settings ----
  theme: ThemeConfig;

  // ---- Status ----
  /** Whether settings are being loaded */
  loading: boolean;
  /** Error message if loading/saving failed */
  error: string | null;
  /** Whether settings have been modified since last save */
  isDirty: boolean;
  /** Whether the initial load has completed */
  isLoaded: boolean;

  // ---- Actions ----
  /** Load all settings from the backend */
  loadSettings: () => Promise<void>;
  /** Save all settings to the backend */
  saveSettings: () => Promise<void>;
  /** Update a single setting value by dot-notation key */
  updateSetting: (key: string, value: unknown) => void;
  /** Update game settings */
  updateGameSettings: (updates: Partial<GameConfig>) => void;
  /** Update download settings */
  updateDownloadSettings: (updates: Partial<DownloadConfig>) => void;
  /** Update UI settings */
  updateUiSettings: (updates: Partial<UiConfig>) => void;
  /** Update theme settings */
  updateThemeSettings: (updates: Partial<ThemeConfig>) => void;
  /** Set the theme mode */
  setThemeMode: (mode: ThemeMode) => void;
  /** Set the theme color */
  setThemeColor: (color: ThemeColor) => void;
  /** Set the download source */
  setDownloadSource: (source: DownloadSource) => void;
  /** Set the language */
  setLanguage: (language: string) => void;
  /** Reset all settings to defaults */
  resetSettings: () => void;
  /** Clear any error state */
  clearError: () => void;
}

// ===========================================================================
// Helpers
// ===========================================================================

/**
 * Set a value at a dot-notation path in an object.
 * Returns a new object with the updated value.
 */
function setNestedValue<T>(
  obj: T,
  path: string,
  value: unknown,
): T {
  const keys = path.split(".");
  const result = { ...obj } as Record<string, unknown>;

  let current: Record<string, unknown> = result;
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i];
    if (!(key in current)) {
      current[key] = {};
    }
    current[key] = { ...(current[key] as Record<string, unknown>) };
    current = current[key] as Record<string, unknown>;
  }

  const lastKey = keys[keys.length - 1];
  current[lastKey] = value;

  return result as T;
}

// ===========================================================================
// Store
// ===========================================================================

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      // ---- Initial State ----
      game: { ...DEFAULT_GAME },
      download: { ...DEFAULT_DOWNLOAD },
      ui: { ...DEFAULT_UI },
      theme: { ...DEFAULT_THEME },
      loading: false,
      error: null,
      isDirty: false,
      isLoaded: false,

      // ---- Actions ----

      loadSettings: async () => {
        set({ loading: true, error: null });

        try {
          if (isShowcaseMode()) {
            await new Promise((r) => setTimeout(r, 300));
            set({
              game: { ...DEFAULT_GAME },
              download: { ...DEFAULT_DOWNLOAD },
              ui: { ...DEFAULT_UI },
              theme: { ...DEFAULT_THEME },
              loading: false,
              isLoaded: true,
              isDirty: false,
            });
            return;
          }

          const response = await transport.invoke<LauncherConfig>("get_config");

          if (response.success && response.data) {
            const config = response.data;
            set({
              game: { ...DEFAULT_GAME, ...config.game },
              download: { ...DEFAULT_DOWNLOAD, ...config.download },
              ui: { ...DEFAULT_UI, ...config.ui },
              theme: { ...DEFAULT_THEME, ...config.theme },
              loading: false,
              isLoaded: true,
              isDirty: false,
            });
          } else {
            // Load defaults on failure
            set({
              loading: false,
              isLoaded: true,
              error: response.error ?? "Failed to load settings",
            });
          }
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : String(error);
          set({
            loading: false,
            isLoaded: true,
            error: message,
          });
        }
      },

      saveSettings: async () => {
        set({ loading: true, error: null });

        const state = get();
        const config: LauncherConfig = {
          version: 1,
          game: state.game,
          download: state.download,
          ui: state.ui,
          theme: state.theme,
        };

        try {
          if (isShowcaseMode()) {
            await new Promise((r) => setTimeout(r, 300));
            set({ loading: false, isDirty: false });
            return;
          }

          const response = await transport.invoke<{ ok: boolean }>("save_config", {
            config,
          });

          if (response.success) {
            set({ loading: false, isDirty: false });
          } else {
            set({ error: response.error ?? "Failed to save settings", loading: false });
          }
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : String(error);
          set({ error: message, loading: false });
        }
      },

      updateSetting: (key: string, value: unknown) => {
        set((state) => {
          // Map top-level keys to their sections
          const parts = key.split(".");
          const section = parts[0] as keyof SettingsState;

          if (section === "game" && parts.length > 1) {
            const gamePath = parts.slice(1).join(".");
            return {
              game: setNestedValue(state.game, gamePath, value) as GameConfig,
              isDirty: true as const,
            };
          }
          if (section === "download" && parts.length > 1) {
            const downloadPath = parts.slice(1).join(".");
            return {
              download: setNestedValue(state.download, downloadPath, value) as DownloadConfig,
              isDirty: true as const,
            };
          }
          if (section === "ui" && parts.length > 1) {
            const uiPath = parts.slice(1).join(".");
            return {
              ui: setNestedValue(state.ui, uiPath, value) as UiConfig,
              isDirty: true as const,
            };
          }
          if (section === "theme" && parts.length > 1) {
            const themePath = parts.slice(1).join(".");
            return {
              theme: setNestedValue(state.theme, themePath, value) as ThemeConfig,
              isDirty: true as const,
            };
          }

          return state;
        });
      },

      updateGameSettings: (updates: Partial<GameConfig>) => {
        set((state) => ({
          game: { ...state.game, ...updates },
          isDirty: true,
        }));
      },

      updateDownloadSettings: (updates: Partial<DownloadConfig>) => {
        set((state) => ({
          download: { ...state.download, ...updates },
          isDirty: true,
        }));
      },

      updateUiSettings: (updates: Partial<UiConfig>) => {
        set((state) => ({
          ui: { ...state.ui, ...updates },
          isDirty: true,
        }));
      },

      updateThemeSettings: (updates: Partial<ThemeConfig>) => {
        set((state) => ({
          theme: { ...state.theme, ...updates },
          isDirty: true,
        }));
      },

      setThemeMode: (mode: ThemeMode) => {
        set((state) => ({
          theme: { ...state.theme, mode },
          isDirty: true,
        }));
      },

      setThemeColor: (color: ThemeColor) => {
        set((state) => ({
          theme: { ...state.theme, color },
          isDirty: true,
        }));
      },

      setDownloadSource: (source: DownloadSource) => {
        set((state) => ({
          download: { ...state.download, source },
          isDirty: true,
        }));
      },

      setLanguage: (language: string) => {
        set((state) => ({
          ui: { ...state.ui, language },
          isDirty: true,
        }));
      },

      resetSettings: () => {
        set({
          game: { ...DEFAULT_GAME },
          download: { ...DEFAULT_DOWNLOAD },
          ui: { ...DEFAULT_UI },
          theme: { ...DEFAULT_THEME },
          isDirty: true,
          error: null,
        });
      },

      clearError: () => {
        set({ error: null });
      },
    }),
    {
      name: "euoracraft-settings",
      partialize: (state) => ({
        game: state.game,
        download: state.download,
        ui: state.ui,
        theme: state.theme,
      }),
    },
  ),
);

// ===========================================================================
// Selectors
// ===========================================================================

/** Select only game settings */
export const selectGameSettings = (state: SettingsState) => state.game;

/** Select only download settings */
export const selectDownloadSettings = (state: SettingsState) => state.download;

/** Select only UI settings */
export const selectUiSettings = (state: SettingsState) => state.ui;

/** Select only theme settings */
export const selectThemeSettings = (state: SettingsState) => state.theme;

/** Select the current language */
export const selectLanguage = (state: SettingsState) => state.ui.language;

/** Select the current theme mode */
export const selectThemeMode = (state: SettingsState) => state.theme.mode;

/** Select the current theme color */
export const selectThemeColor = (state: SettingsState) => state.theme.color;

export default useSettingsStore;