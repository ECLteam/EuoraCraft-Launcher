/**
 * API Client Facade
 *
 * Provides a clean, type-safe API interface for the application
 * by wrapping the transport layer. The client exposes organized
 * method groups for config, commands, events, and file system
 * operations.
 *
 * Usage:
 *   import { api } from "@/api/client";
 *   const config = await api.config.get();
 *   await api.command("launch_game", { version: "1.21.4" });
 *   api.on("launch:progress", (payload) => { ... });
 */

import { transport } from "@/api/transport";
import type { Transport } from "@/api/transport";
import type { ApiResponse, LauncherConfig, GameConfig, ThemeConfig, DownloadConfig, UiConfig } from "@/types/api";

// ===========================================================================
// Constants
// ===========================================================================

const LOG_PREFIX = "[ApiClient]";

/** Whether debug logging is enabled (development mode only) */
const DEBUG = import.meta.env.DEV;

// ===========================================================================
// Utility Types
// ===========================================================================

/** Event handler callback type */
type EventHandler<T = unknown> = (payload: T) => void;

/** Registered event listener */
interface EventListenerEntry {
  event: string;
  handler: EventHandler;
  unlisten: () => void;
}

// ===========================================================================
// Config API
// ===========================================================================

/**
 * Configuration API methods for reading and writing launcher config.
 */
const configApi = {
  /**
   * Get the full launcher configuration.
   */
  async get(): Promise<ApiResponse<LauncherConfig>> {
    if (DEBUG) console.debug(`${LOG_PREFIX} config.get()`);
    return transport.invoke<LauncherConfig>("get_config");
  },

  /**
   * Get a specific config section by key.
   */
  async getSection<K extends keyof LauncherConfig>(
    key: K,
  ): Promise<ApiResponse<LauncherConfig[K]>> {
    const cmdMap: Record<string, string> = {
      game: "get_game_config",
      theme: "get_theme_config",
      download: "get_download_config",
      ui: "get_ui_config",
    };
    const cmd = cmdMap[key] ?? "get_config";
    if (DEBUG) console.debug(`${LOG_PREFIX} config.getSection("${key}")`);

    const response = await transport.invoke<LauncherConfig>(cmd);
    if (response.success && response.data) {
      return {
        ...response,
        data: response.data[key],
      };
    }
    return response as unknown as ApiResponse<LauncherConfig[K]>;
  },

  /**
   * Get the game configuration section.
   */
  async getGame(): Promise<ApiResponse<GameConfig>> {
    return configApi.getSection("game") as Promise<ApiResponse<GameConfig>>;
  },

  /**
   * Get the theme configuration section.
   */
  async getTheme(): Promise<ApiResponse<ThemeConfig>> {
    return configApi.getSection("theme") as Promise<ApiResponse<ThemeConfig>>;
  },

  /**
   * Get the download configuration section.
   */
  async getDownload(): Promise<ApiResponse<DownloadConfig>> {
    return configApi.getSection("download") as Promise<ApiResponse<DownloadConfig>>;
  },

  /**
   * Get the UI configuration section.
   */
  async getUi(): Promise<ApiResponse<UiConfig>> {
    return configApi.getSection("ui") as Promise<ApiResponse<UiConfig>>;
  },

  /**
   * Set a single configuration value. The backend merges it into the
   * existing config and persists it.
   *
   * @param key - Dot-notation config key (e.g. "game.maxMemory")
   * @param value - The new value to set
   */
  async set(
    key: string,
    value: unknown,
  ): Promise<ApiResponse<{ ok: boolean }>> {
    if (DEBUG) console.debug(`${LOG_PREFIX} config.set("${key}")`, value);
    return transport.invoke("set_config", { key, value });
  },

  /**
   * Set multiple configuration values at once.
   *
   * @param values - Record of key-value pairs to set
   */
  async setMany(
    values: Record<string, unknown>,
  ): Promise<ApiResponse<{ ok: boolean }>> {
    if (DEBUG) console.debug(`${LOG_PREFIX} config.setMany()`, values);
    return transport.invoke("set_config", { values });
  },

  /**
   * Save the current configuration to disk.
   */
  async save(): Promise<ApiResponse<{ ok: boolean }>> {
    if (DEBUG) console.debug(`${LOG_PREFIX} config.save()`);
    return transport.invoke("save_config");
  },

  /**
   * Get multiple configuration values by their keys.
   *
   * @param keys - Array of dot-notation config keys
   */
  async getMany(
    keys: string[],
  ): Promise<ApiResponse<Record<string, unknown>>> {
    if (DEBUG) console.debug(`${LOG_PREFIX} config.getMany()`, keys);
    return transport.invoke("get_config_values", { keys });
  },
};

// ===========================================================================
// Event API
// ===========================================================================

const eventListeners: EventListenerEntry[] = [];

/**
 * Event API methods for subscribing to backend events.
 */
const eventApi = {
  /**
   * Subscribe to a backend event.
   *
   * @param event - The event name to listen for
   * @param handler - Callback invoked with the event payload
   * @returns An unsubscribe function
   */
  async on<T = unknown>(
    event: string,
    handler: EventHandler<T>,
  ): Promise<() => void> {
    if (DEBUG) console.debug(`${LOG_PREFIX} event.on("${event}")`);

    const unlisten = await transport.listen<T>(event, handler);

    const entry: EventListenerEntry = {
      event,
      handler: handler as EventHandler,
      unlisten,
    };
    eventListeners.push(entry);

    return () => {
      unlisten();
      const index = eventListeners.indexOf(entry);
      if (index !== -1) {
        eventListeners.splice(index, 1);
      }
    };
  },

  /**
   * Unsubscribe from a backend event.
   *
   * @param event - The event name
   * @param handler - The handler to remove (if omitted, removes all handlers for this event)
   */
  off(event: string, handler?: EventHandler): void {
    if (DEBUG) console.debug(`${LOG_PREFIX} event.off("${event}")`);

    const toRemove = eventListeners.filter(
      (l) => l.event === event && (!handler || l.handler === handler),
    );

    for (const entry of toRemove) {
      entry.unlisten();
      const index = eventListeners.indexOf(entry);
      if (index !== -1) {
        eventListeners.splice(index, 1);
      }
    }
  },

  /**
   * Remove all event listeners.
   */
  offAll(): void {
    if (DEBUG) console.debug(`${LOG_PREFIX} event.offAll()`);

    for (const entry of [...eventListeners]) {
      entry.unlisten();
    }
    eventListeners.length = 0;
  },
};

// ===========================================================================
// File System API
// ===========================================================================

/**
 * File system API methods for reading files and directories.
 */
const fsApi = {
  /**
   * Read a file's contents as raw bytes.
   *
   * @param path - Absolute path to the file
   */
  async readFile(path: string): Promise<Uint8Array> {
    if (DEBUG) console.debug(`${LOG_PREFIX} fs.readFile("${path}")`);
    return transport.readFile(path);
  },

  /**
   * Read a text file's contents as a string.
   *
   * @param path - Absolute path to the file
   * @param encoding - Text encoding (default: "utf-8")
   */
  async readTextFile(path: string, encoding = "utf-8"): Promise<string> {
    if (DEBUG) console.debug(`${LOG_PREFIX} fs.readTextFile("${path}")`);
    const bytes = await transport.readFile(path);
    return new TextDecoder(encoding).decode(bytes);
  },

  /**
   * Read a JSON file and parse its contents.
   *
   * @param path - Absolute path to the JSON file
   */
  async readJsonFile<T = unknown>(path: string): Promise<T> {
    if (DEBUG) console.debug(`${LOG_PREFIX} fs.readJsonFile("${path}")`);
    const text = await fsApi.readTextFile(path);
    return JSON.parse(text) as T;
  },

  /**
   * List the contents of a directory.
   *
   * @param path - Absolute path to the directory
   */
  async readDir(path: string): Promise<string[]> {
    if (DEBUG) console.debug(`${LOG_PREFIX} fs.readDir("${path}")`);
    return transport.readDir(path);
  },

  /**
   * Check if a file or directory exists at the given path.
   *
   * @param path - Absolute path to check
   */
  async exists(path: string): Promise<boolean> {
    if (DEBUG) console.debug(`${LOG_PREFIX} fs.exists("${path}")`);
    return transport.exists(path);
  },
};

// ===========================================================================
// File Path API
// ===========================================================================

/**
 * File path utility methods.
 */
const fileApi = {
  /**
   * Resolve a relative path to an absolute path.
   *
   * @param path - Relative path to resolve
   */
  async resolve(path: string): Promise<string> {
    if (DEBUG) console.debug(`${LOG_PREFIX} file.resolve("${path}")`);
    return transport.resolvePath(path);
  },

  /**
   * Convert a local file path to an asset URL for use in the webview.
   *
   * @param path - Absolute file path
   */
  toUrl(path: string): string {
    if (DEBUG) console.debug(`${LOG_PREFIX} file.toUrl("${path}")`);
    return transport.convertFileSrc(path);
  },
};

// ===========================================================================
// API Client
// ===========================================================================

/**
 * The main API client that provides a clean facade over the transport layer.
 *
 * Usage:
 * ```typescript
 * import { api } from "@/api/client";
 *
 * // Read config
 * const config = await api.config.get();
 *
 * // Send a command
 * const result = await api.command("launch_game", { versionId: "1.21.4" });
 *
 * // Listen to events
 * const unlisten = await api.on("launch:progress", (payload) => {
 *   console.log(payload.progress);
 * });
 *
 * // File system
 * const exists = await api.fs.exists(".minecraft/options.txt");
 * const dirs = await api.fs.readDir(".minecraft");
 *
 * // File paths
 * const fullPath = await api.file.resolve(".minecraft");
 * const imgUrl = api.file.toUrl("/path/to/icon.png");
 * ```
 */
export interface ApiClient {
  /** Configuration operations */
  config: typeof configApi;
  /** Send a raw command to the backend */
  command: <T = unknown>(cmd: string, params?: Record<string, unknown>) => Promise<ApiResponse<T>>;
  /** Subscribe to a backend event */
  on: typeof eventApi.on;
  /** Unsubscribe from a backend event */
  off: typeof eventApi.off;
  /** Remove all event listeners */
  offAll: typeof eventApi.offAll;
  /** File system operations */
  fs: typeof fsApi;
  /** File path utilities */
  file: typeof fileApi;
  /** Raw transport access (for advanced use) */
  transport: Transport;
}

/**
 * Singleton API client instance.
 */
export const api: ApiClient = {
  config: configApi,

  async command<T = unknown>(
    cmd: string,
    params?: Record<string, unknown>,
  ): Promise<ApiResponse<T>> {
    if (DEBUG) console.debug(`${LOG_PREFIX} command("${cmd}")`, params);
    return transport.invoke<T>(cmd, params);
  },

  on: eventApi.on,
  off: eventApi.off,
  offAll: eventApi.offAll,
  fs: fsApi,
  file: fileApi,
  transport,
};

// ===========================================================================
// Convenience Re-exports
// ===========================================================================

export { transport } from "@/api/transport";
export type { Transport } from "@/api/transport";
export type { ApiResponse } from "@/types/api";

export default api;