/**
 * Showcase / Demo Transport Implementation
 *
 * Fully mocked transport implementation for running the launcher
 * in a browser without Tauri (demo / development mode). Returns
 * realistic mock data for all API calls with simulated network
 * delays (200-500ms).
 *
 * Used when `window.__TAURI_INTERNALS__` is not available.
 */

import type { ApiResponse } from "@/types/api";
import type {
  LauncherConfig,
  MinecraftVersion,
  ScannedVersion,
  GameInstance,
  MinecraftAccount,
  PluginInfo,
} from "@/types/api";
import type { Transport } from "./types";

// ===========================================================================
// Constants
// ===========================================================================

/** Log prefix for showcase operations */
const LOG_PREFIX = "[ShowcaseTransport]";

/**
 * Simulate a random network delay between min and max milliseconds.
 */
function delay(min = 200, max = 500): Promise<void> {
  const ms = Math.floor(Math.random() * (max - min + 1)) + min;
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ===========================================================================
// Mock Data
// ===========================================================================

/** Mock launcher configuration */
const mockConfig: LauncherConfig = {
  version: 1,
  game: {
    javaPath: "C:\\Program Files\\Java\\jdk-17\\bin\\javaw.exe",
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
  },
  theme: {
    mode: "dark",
    color: "blue",
    glassEffect: true,
    reducedMotion: false,
    uiScale: 1.0,
  },
  download: {
    maxConcurrent: 5,
    retryCount: 3,
    speedLimit: 0,
    source: "bmclapi",
    verifyHash: true,
  },
  ui: {
    language: "zh-CN",
    sidebarCollapsed: false,
    showTitleBar: true,
    useTopNav: false,
    enableBlur: true,
  },
};

/** Mock Minecraft versions from the manifest */
const mockVersions: MinecraftVersion[] = [
  {
    id: "1.21.4",
    type: "release",
    releaseTime: "2024-12-03T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.21.4.json",
    sha1: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    compliance: true,
  },
  {
    id: "1.21.3",
    type: "release",
    releaseTime: "2024-10-23T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.21.3.json",
    sha1: "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
    compliance: true,
  },
  {
    id: "1.21.1",
    type: "release",
    releaseTime: "2024-08-08T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.21.1.json",
    sha1: "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    compliance: true,
  },
  {
    id: "1.20.6",
    type: "release",
    releaseTime: "2024-04-29T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.20.6.json",
    sha1: "d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
    compliance: true,
  },
  {
    id: "1.20.4",
    type: "release",
    releaseTime: "2023-12-07T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.20.4.json",
    sha1: "e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
    compliance: true,
  },
  {
    id: "1.20.1",
    type: "release",
    releaseTime: "2023-06-12T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.20.1.json",
    sha1: "f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1",
    compliance: true,
  },
  {
    id: "24w44a",
    type: "snapshot",
    releaseTime: "2024-10-30T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/24w44a.json",
    sha1: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c300000000",
    compliance: true,
  },
  {
    id: "1.19.4",
    type: "release",
    releaseTime: "2023-03-14T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.19.4.json",
    sha1: "b2c3d4e5f6a1b2c3d4e5f6a1b2c30000000001",
    compliance: true,
  },
  {
    id: "1.18.2",
    type: "release",
    releaseTime: "2022-02-28T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.18.2.json",
    sha1: "c3d4e5f6a1b2c3d4e5f6a1b2c3000000000002",
    compliance: true,
  },
  {
    id: "1.16.5",
    type: "release",
    releaseTime: "2021-01-15T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.16.5.json",
    sha1: "d4e5f6a1b2c3d4e5f6a1b2c30000000000003",
    compliance: true,
  },
];

/** Mock scanned (installed) versions */
const mockInstalledVersions: ScannedVersion[] = [
  {
    id: "1.21.4",
    type: "release",
    path: ".minecraft/versions/1.21.4",
    loaders: ["Fabric", "OptiFine"],
    isModified: true,
    lastPlayed: Date.now() - 3600000,
    playTime: 3600,
  },
  {
    id: "1.20.4",
    type: "release",
    path: ".minecraft/versions/1.20.4",
    loaders: ["Forge"],
    isModified: false,
    lastPlayed: Date.now() - 86400000,
    playTime: 7200,
  },
  {
    id: "1.16.5",
    type: "release",
    path: ".minecraft/versions/1.16.5",
    loaders: ["Vanilla"],
    isModified: false,
    lastPlayed: Date.now() - 604800000,
    playTime: 18000,
  },
];

/** Mock game instances */
const mockGameInstances: GameInstance[] = [
  {
    id: "instance-1",
    name: "EuoraCraft Survival",
    version: mockVersions[0],
    loader: "Fabric",
    loaderVersion: "0.16.10",
    gameDir: ".minecraft/instances/survival",
    jvmArgs: [],
    minMemory: 2048,
    maxMemory: 4096,
    windowWidth: 1280,
    windowHeight: 720,
    fullscreen: false,
    createdAt: Date.now() - 2592000000,
    lastPlayed: Date.now() - 3600000,
    totalPlayTime: 3600,
    isHidden: false,
    notes: "Main survival world with friends",
  },
  {
    id: "instance-2",
    name: "Creative Build",
    version: mockVersions[2],
    loader: "Forge",
    loaderVersion: "49.0.38",
    gameDir: ".minecraft/instances/creative",
    jvmArgs: [],
    minMemory: 4096,
    maxMemory: 8192,
    windowWidth: 1920,
    windowHeight: 1080,
    fullscreen: false,
    createdAt: Date.now() - 864000000,
    lastPlayed: Date.now() - 86400000,
    totalPlayTime: 7200,
    isHidden: false,
    notes: "Creative world with shaders",
  },
];

/** Mock Minecraft accounts */
const mockAccounts: MinecraftAccount[] = [
  {
    uuid: "account-1",
    type: "microsoft",
    username: "EuoraPlayer",
    playerUuid: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    accessToken: "eyJhbGciOiJIUzI1NiJ9.mock_token_1",
    refreshToken: "mock_refresh_token_1",
    expiresAt: Date.now() + 86400000,
    isSelected: true,
    avatarUrl: "https://crafatar.com/avatars/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4?size=64&overlay",
    lastLogin: Date.now() - 3600000,
    isLoggedIn: true,
  },
  {
    uuid: "account-2",
    type: "offline",
    username: "Steve",
    playerUuid: "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f",
    accessToken: "",
    refreshToken: "",
    expiresAt: 0,
    isSelected: false,
    avatarUrl: "",
    lastLogin: Date.now() - 86400000,
    isLoggedIn: true,
  },
];

/** Mock plugin information */
const mockPlugins: PluginInfo[] = [
  {
    id: "plugin-optimizer",
    name: "性能优化器",
    description: "自动优化 Minecraft 游戏性能，智能调整 JVM 参数",
    author: "EuoraCraft Team",
    version: "1.2.0",
    iconUrl: "",
    category: "tool",
    isInstalled: true,
    hasUpdate: false,
    downloads: 15234,
    rating: 4.5,
    tags: ["性能", "优化", "JVM"],
    updatedAt: Date.now() - 86400000,
    size: 245760,
  },
  {
    id: "plugin-world-backup",
    name: "世界备份",
    description: "定时自动备份 Minecraft 存档，支持增量备份和云同步",
    author: "EuoraCraft Team",
    version: "2.0.1",
    iconUrl: "",
    category: "utility",
    isInstalled: true,
    hasUpdate: true,
    downloads: 8921,
    rating: 4.8,
    tags: ["备份", "存档", "云同步"],
    updatedAt: Date.now() - 172800000,
    size: 524288,
  },
  {
    id: "plugin-resource-exporter",
    name: "资源包导出",
    description: "一键导出 Minecraft 资源包，支持自定义纹理和音效",
    author: "Community",
    version: "0.9.5",
    iconUrl: "",
    category: "tool",
    isInstalled: false,
    hasUpdate: false,
    downloads: 3456,
    rating: 4.2,
    tags: ["资源包", "导出", "纹理"],
    updatedAt: Date.now() - 604800000,
    size: 1048576,
  },
  {
    id: "plugin-skin-manager",
    name: "皮肤管理器",
    description: "管理和切换 Minecraft 皮肤，支持本地和在线皮肤",
    author: "Community",
    version: "3.1.0",
    iconUrl: "",
    category: "cosmetic",
    isInstalled: true,
    hasUpdate: false,
    downloads: 21567,
    rating: 4.6,
    tags: ["皮肤", "外观", "管理器"],
    updatedAt: Date.now() - 432000000,
    size: 196608,
  },
  {
    id: "plugin-shader-pack",
    name: "光影包管理",
    description: "一键安装和管理光影包，支持 OptiFine 和 Iris",
    author: "EuoraCraft Team",
    version: "1.5.2",
    iconUrl: "",
    category: "graphics",
    isInstalled: false,
    hasUpdate: false,
    downloads: 12543,
    rating: 4.7,
    tags: ["光影", "OptiFine", "Iris"],
    updatedAt: Date.now() - 259200000,
    size: 3145728,
  },
  {
    id: "plugin-modpack-creator",
    name: "整合包创建器",
    description: "可视化创建和管理 Minecraft 整合包，自动解决依赖冲突",
    author: "EuoraCraft Team",
    version: "2.3.0",
    iconUrl: "",
    category: "tool",
    isInstalled: false,
    hasUpdate: false,
    downloads: 6789,
    rating: 4.4,
    tags: ["整合包", "模组", "依赖"],
    updatedAt: Date.now() - 1296000000,
    size: 2097152,
  },
];

/** Mock file system structure */
const mockFileSystem: Record<string, { isDirectory: boolean; content?: string }> = {
  ".minecraft": { isDirectory: true },
  ".minecraft/versions": { isDirectory: true },
  ".minecraft/versions/1.21.4": { isDirectory: true },
  ".minecraft/versions/1.20.4": { isDirectory: true },
  ".minecraft/versions/1.16.5": { isDirectory: true },
  ".minecraft/mods": { isDirectory: true },
  ".minecraft/resourcepacks": { isDirectory: true },
  ".minecraft/shaderpacks": { isDirectory: true },
  ".minecraft/saves": { isDirectory: true },
  ".minecraft/options.txt": { isDirectory: false, content: "fov:0.5\ngamma:1.0\n" },
  ".minecraft/servers.dat": { isDirectory: false, content: "" },
  ".minecraft/launcher_profiles.json": {
    isDirectory: false,
    content: JSON.stringify({ profiles: {}, settings: {} }),
  },
};

// ===========================================================================
// Event Listener Registry
// ===========================================================================

interface ListenerEntry {
  event: string;
  handler: (payload: unknown) => void;
  unlisten: () => void;
}

const listeners: ListenerEntry[] = [];

/**
 * Simulate a backend event emission (for testing).
 * This is exposed for manual testing in the browser console.
 */
function simulateEvent(event: string, payload: unknown): void {
  listeners
    .filter((l) => l.event === event)
    .forEach((l) => l.handler(payload));
}

// Expose simulateEvent on window for debugging
if (typeof window !== "undefined") {
  (window as unknown as Record<string, unknown>).__showcaseEmit = simulateEvent;
}

// ===========================================================================
// ShowcaseTransport Implementation
// ===========================================================================

/**
 * Demo/mock transport implementation for browser-based development.
 *
 * Returns realistic mock data with simulated network delays.
 * Does not communicate with any real backend.
 */
export const showcaseTransport: Transport = {
  async invoke<T>(
    cmd: string,
    args?: Record<string, unknown>,
  ): Promise<ApiResponse<T>> {
    await delay();

    if (import.meta.env.DEV) {
      console.debug(`${LOG_PREFIX} invoke "${cmd}"`, { args });
    }

    try {
      let data: unknown;

      switch (cmd) {
        // ---- Config Commands ----
        case "get_config":
          data = mockConfig;
          break;
        case "get_game_config":
          data = mockConfig.game;
          break;
        case "get_theme_config":
          data = mockConfig.theme;
          break;
        case "get_download_config":
          data = mockConfig.download;
          break;
        case "get_ui_config":
          data = mockConfig.ui;
          break;
        case "set_config":
        case "save_config":
          data = { ok: true };
          break;

        // ---- Version Commands ----
        case "get_versions":
          data = mockVersions;
          break;
        case "get_installed_versions":
          data = mockInstalledVersions;
          break;
        case "get_instances":
          data = mockGameInstances;
          break;
        case "install_version":
          data = { taskId: "task-" + Date.now() };
          break;
        case "delete_version":
          data = { ok: true };
          break;

        // ---- Account Commands ----
        case "get_accounts":
          data = mockAccounts;
          break;
        case "add_account":
          data = { ...mockAccounts[0], uuid: "account-" + Date.now() };
          break;
        case "remove_account":
          data = { ok: true };
          break;
        case "select_account":
          data = { ok: true };
          break;
        case "microsoft_login":
          data = {
            deviceCode: "ABC123",
            userCode: "USER-CODE",
            verificationUri: "https://microsoft.com/link",
            expiresIn: 900,
            interval: 5,
          };
          break;
        case "microsoft_poll":
          data = {
            status: "authorization_pending",
          };
          break;
        case "offline_login":
          data = {
            uuid: "offline-" + Date.now(),
            type: "offline",
            username: (args?.username as string) ?? "Player",
            playerUuid: "offline-" + Date.now(),
            accessToken: "",
            refreshToken: "",
            expiresAt: 0,
            isSelected: true,
            isLoggedIn: true,
          };
          break;

        // ---- Plugin Commands ----
        case "get_plugins":
          data = mockPlugins;
          break;
        case "enable_plugin":
        case "disable_plugin":
        case "reload_plugin":
        case "uninstall_plugin":
          data = { ok: true, id: args?.id };
          break;
        case "install_plugin":
          data = { taskId: "task-plugin-" + Date.now() };
          break;

        // ---- Launch Commands ----
        case "launch_game":
          data = { pid: 12345, taskId: "task-launch-" + Date.now() };
          break;
        case "kill_game":
          data = { ok: true };
          break;

        // ---- Default ----
        default:
          if (import.meta.env.DEV) {
            console.warn(`${LOG_PREFIX} unknown command "${cmd}", returning empty`);
          }
          data = {};
          break;
      }

      return {
        success: true,
        data: data as T,
        timestamp: Date.now(),
      };
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        error: message,
        timestamp: Date.now(),
      };
    }
  },

  async listen<T>(
    event: string,
    handler: (payload: T) => void,
  ): Promise<() => void> {
    await delay(50, 100);

    if (import.meta.env.DEV) {
      console.debug(`${LOG_PREFIX} listen registering for "${event}"`);
    }

    const unlisten = () => {
      const index = listeners.findIndex(
        (l) => l.event === event && l.handler === handler,
      );
      if (index !== -1) {
        listeners.splice(index, 1);
      }
      if (import.meta.env.DEV) {
        console.debug(`${LOG_PREFIX} listen unregistered for "${event}"`);
      }
    };

    listeners.push({
      event,
      handler: handler as (payload: unknown) => void,
      unlisten,
    });

    return unlisten;
  },

  async readFile(path: string): Promise<Uint8Array> {
    await delay(100, 200);

    const entry = mockFileSystem[path];
    if (!entry || entry.isDirectory) {
      throw new Error(`File not found: ${path}`);
    }

    const encoder = new TextEncoder();
    return encoder.encode(entry.content ?? "");
  },

  async exists(path: string): Promise<boolean> {
    await delay(50, 100);
    return path in mockFileSystem;
  },

  async readDir(path: string): Promise<string[]> {
    await delay(100, 200);

    const normalizedPath = path.endsWith("/") ? path.slice(0, -1) : path;
    const prefix = normalizedPath ? normalizedPath + "/" : "";

    const entries = Object.keys(mockFileSystem)
      .filter((key) => key.startsWith(prefix) && key !== normalizedPath)
      .map((key) => key.slice(prefix.length))
      .filter((name) => !name.includes("/"))
      .filter((name, index, arr) => arr.indexOf(name) === index);

    if (entries.length === 0) {
      throw new Error(`Directory not found: ${path}`);
    }

    return entries;
  },

  async resolvePath(path: string): Promise<string> {
    await delay(50, 100);
    // In showcase mode, just prepend a mock base path
    return `/mock-app-data/${path.replace(/^\.\//, "").replace(/^\./, "")}`;
  },

  convertFileSrc(path: string): string {
    // In showcase mode, return the path as-is (or a data URL placeholder)
    if (path.endsWith(".png") || path.endsWith(".jpg") || path.endsWith(".webp")) {
      return `https://placehold.co/128x128/3b82f6/ffffff?text=${encodeURIComponent(path.split("/").pop() ?? "img")}`;
    }
    return path;
  },
};

export default showcaseTransport;