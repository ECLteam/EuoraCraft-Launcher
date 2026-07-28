/**
 * i18n Initialization
 *
 * Initializes i18next with react-i18next for the EuoraCraft Launcher.
 * Supports zh-CN (default) and en-US (fallback) languages.
 *
 * Synchronizes language changes with the settings store to persist
 * the user's language preference across sessions.
 *
 * Usage:
 *   import { t } from "@/i18n";
 *   // or use the useTranslation hook from react-i18next
 *   import { useTranslation } from "react-i18next";
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import zhCN from "./locales/zh-CN.json";
import enUS from "./locales/en-US.json";

// ===========================================================================
// Resources
// ===========================================================================

const resources = {
  "zh-CN": { translation: zhCN },
  "en-US": { translation: enUS },
} as const;

/** Supported language codes */
export const SUPPORTED_LANGUAGES = ["zh-CN", "en-US"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

/** Language display names */
export const LANGUAGE_NAMES: Record<SupportedLanguage, string> = {
  "zh-CN": "简体中文",
  "en-US": "English",
};

// ===========================================================================
// Initialization
// ===========================================================================

/**
 * Get the initial language preference.
 * Priority: localStorage > settings store > navigator > default
 */
function getInitialLanguage(): SupportedLanguage {
  // Check localStorage first (from zustand persist)
  try {
    const stored = localStorage.getItem("euoracraft-settings");
    if (stored) {
      const parsed = JSON.parse(stored);
      const lang = parsed?.state?.ui?.language;
      if (lang && SUPPORTED_LANGUAGES.includes(lang as SupportedLanguage)) {
        return lang as SupportedLanguage;
      }
    }
  } catch {
    // Ignore parse errors
  }

  // Check browser language
  if (typeof navigator !== "undefined") {
    const browserLang = navigator.language;
    if (browserLang.startsWith("zh")) {
      return "zh-CN";
    }
    if (browserLang.startsWith("en")) {
      return "en-US";
    }
  }

  // Default
  return "zh-CN";
}

const initialLanguage = getInitialLanguage();

i18n.use(initReactI18next).init({
  resources,
  lng: initialLanguage,
  fallbackLng: "en-US",
  interpolation: {
    escapeValue: false, // React already escapes values
  },
  returnNull: false,
  returnEmptyString: false,
  // Debug mode in development
  debug: import.meta.env.DEV ? false : false,
});

// ===========================================================================
// Settings Store Synchronization
// ===========================================================================

/**
 * Subscribe to language changes from the settings store.
 * When the user changes the language in settings, i18n updates automatically.
 *
 * This function should be called once at app startup.
 * It uses a dynamic import to avoid circular dependencies.
 */
let _languageSyncInitialized = false;

export function initLanguageSync(): void {
  if (_languageSyncInitialized) {
    return;
  }
  _languageSyncInitialized = true;

  // Use dynamic import to avoid circular dependency at module init time
  import("@/stores/settingsStore").then(({ useSettingsStore }) => {
    // Sync initial state
    const currentLang = useSettingsStore.getState().ui.language;
    if (currentLang && currentLang !== i18n.language) {
      i18n.changeLanguage(currentLang).catch(() => {
        // Silently ignore change language errors
      });
    }

    // Subscribe to future changes
    useSettingsStore.subscribe((state, prevState) => {
      const newLang = state.ui.language;
      const prevLang = prevState.ui.language;
      if (newLang && newLang !== prevLang && newLang !== i18n.language) {
        i18n.changeLanguage(newLang).catch(() => {
          // Silently ignore change language errors
        });
      }
    });
  }).catch(() => {
    // Settings store may not be available yet
    if (import.meta.env.DEV) {
      console.warn("[i18n] Failed to sync with settings store");
    }
  });
}

// ===========================================================================
// Helpers
// ===========================================================================

/**
 * Change the application language.
 * Also updates the settings store if available.
 *
 * @param language - The language code to switch to
 */
export async function changeLanguage(language: SupportedLanguage): Promise<void> {
  await i18n.changeLanguage(language);

  // Update the settings store
  try {
    const { useSettingsStore } = await import("@/stores/settingsStore");
    useSettingsStore.getState().setLanguage(language);
  } catch {
    // Settings store may not be available
  }
}

/**
 * Get the current language.
 */
export function getCurrentLanguage(): SupportedLanguage {
  return i18n.language as SupportedLanguage;
}

/**
 * Check if a language code is supported.
 */
export function isSupportedLanguage(lang: string): lang is SupportedLanguage {
  return SUPPORTED_LANGUAGES.includes(lang as SupportedLanguage);
}

// ===========================================================================
// Default Export
// ===========================================================================

export default i18n;