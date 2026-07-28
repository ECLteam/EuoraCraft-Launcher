/**
 * API Type Definitions
 *
 * Comprehensive TypeScript type definitions for the EuoraCraft Launcher
 * API layer. Covers configuration, game, account, event, plugin, and
 * task queue types.
 */

import type { ThemeColor, ThemeMode } from "@/config/theme";
import type { LoaderType, VersionType, DownloadSource } from "@/config/version";
import type { LaunchStage } from "@/config/game";

// ===========================================================================
// Generic API Response
// ===========================================================================

/** Standard API response wrapper */
export interface ApiResponse<T = unknown> {
  /** Whether the request was successful */
  success: boolean;
  /** Response data (present on success) */
  data?: T;
  /** Error message (present on failure) */
  error?: string;
  /** Error code for programmatic handling */
  code?: string;
  /** Unix timestamp of the response */
  timestamp: number;
}

// ===========================================================================
// Transport Interface
// ===========================================================================

/** Generic transport layer for backend communication */
export interface Transport {
  /** Send a command and receive a typed response */
  invoke<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T>;
  /** Listen for events from the backend */
  listen<T = unknown>(event: string, handler: (payload: T) => void): Promise<() => void>;
  /** Emit an event to the backend */
  emit(event: string, payload?: unknown): Promise<void>;
}

// ===========================================================================
// Configuration Types
// ===========================================================================

/** Top-level launcher configuration */
export interface LauncherConfig {
  game: GameConfig;
  theme: ThemeConfig;
  download: DownloadConfig;
  ui: UiConfig;
  /** Config version for migration support */
  version: number;
}

/** Game-related configuration */
export interface GameConfig {
  /** Path to the Java runtime */
  javaPath: string;
  /** Minimum memory allocation (MB) */
  minMemory: number;
  /** Maximum memory allocation (MB) */
  maxMemory: number;
  /** Custom JVM arguments */
  jvmArgs: string[];
  /** Game window width */
  windowWidth: number;
  /** Game window height */
  windowHeight: number;
  /** Whether to launch in fullscreen */
  fullscreen: boolean;
  /** Game directory path */
  gameDir: string;
  /** Whether to keep the launcher open after game starts */
  keepLauncherOpen: boolean;
  /** Whether to show the game output console */
  showGameOutput: boolean;
  /** Preferred download source */
  downloadSource: DownloadSource;
  /** Whether to use isolated game instances */
  useIsolation: boolean;
}

/** Theme-related configuration */
export interface ThemeConfig {
  mode: ThemeMode;
  color: ThemeColor;
  /** Whether to use glass morphism effects */
  glassEffect: boolean;
  /** Whether to reduce animations */
  reducedMotion: boolean;
  /** UI scale factor (0.8 - 1.5) */
  uiScale: number;
}

/** Download-related configuration */
export interface DownloadConfig {
  /** Maximum concurrent downloads */
  maxConcurrent: number;
  /** Number of download retries on failure */
  retryCount: number;
  /** Download speed limit in bytes per second (0 = unlimited) */
  speedLimit: number;
  /** Preferred download source */
  source: DownloadSource;
  /** Whether to verify file hashes after download */
  verifyHash: boolean;
}

/** UI-related configuration */
export interface UiConfig {
  /** App language code */
  language: string;
  /** Whether the sidebar starts collapsed */
  sidebarCollapsed: boolean;
  /** Whether to show the title bar */
  showTitleBar: boolean;
  /** Whether to use the top navigation bar (instead of sidebar) */
  useTopNav: boolean;
  /** Whether to enable background blur effects */
  enableBlur: boolean;
}

// ===========================================================================
// Game Types
// ===========================================================================

/** A Minecraft version from the manifest */
export interface MinecraftVersion {
  /** Version ID (e.g. "1.20.4") */
  id: string;
  /** Version type */
  type: VersionType;
  /** Release date (ISO 8601) */
  releaseTime: string;
  /** URL to the version JSON manifest */
  url: string;
  /** SHA1 hash of the version JSON */
  sha1: string;
  /** Whether this version is compliant */
  compliance: boolean;
}

/** A locally scanned Minecraft version */
export interface ScannedVersion {
  /** Version ID */
  id: string;
  /** Version type */
  type: VersionType;
  /** Path to the version directory */
  path: string;
  /** Installed loaders */
  loaders: LoaderType[];
  /** Whether this version has been modified */
  isModified: boolean;
  /** Last played timestamp */
  lastPlayed?: number;
  /** Total play time in seconds */
  playTime?: number;
  /** Version icon path (relative to game dir) */
  iconPath?: string;
}

/** A fully configured game instance */
export interface GameInstance {
  /** Unique instance ID */
  id: string;
  /** Display name */
  name: string;
  /** Minecraft version */
  version: MinecraftVersion;
  /** Installed loader */
  loader: LoaderType;
  /** Loader version string */
  loaderVersion: string;
  /** Game directory path */
  gameDir: string;
  /** Instance icon path */
  iconPath?: string;
  /** Instance-specific JVM args */
  jvmArgs: string[];
  /** Min memory (MB) */
  minMemory: number;
  /** Max memory (MB) */
  maxMemory: number;
  /** Window width */
  windowWidth: number;
  /** Window height */
  windowHeight: number;
  /** Whether to launch fullscreen */
  fullscreen: boolean;
  /** Creation timestamp */
  createdAt: number;
  /** Last played timestamp */
  lastPlayed?: number;
  /** Total play time in seconds */
  totalPlayTime: number;
  /** Whether this instance is hidden */
  isHidden: boolean;
  /** Custom notes / description */
  notes?: string;
}

// ===========================================================================
// Account Types
// ===========================================================================

/** Supported account types */
export type AccountType = "microsoft" | "offline";

/** A Minecraft account stored in the launcher */
export interface MinecraftAccount {
  /** Unique account UUID */
  uuid: string;
  /** Account type */
  type: AccountType;
  /** Display name / in-game name */
  username: string;
  /** Player UUID (from Mojang/Microsoft) */
  playerUuid: string;
  /** Microsoft access token */
  accessToken: string;
  /** Microsoft refresh token */
  refreshToken: string;
  /** Token expiry timestamp (Unix ms) */
  expiresAt: number;
  /** Whether this is the currently selected account */
  isSelected: boolean;
  /** Avatar URL */
  avatarUrl?: string;
  /** Last login timestamp */
  lastLogin?: number;
  /** Whether the account is currently logged in */
  isLoggedIn: boolean;
}

/** Microsoft OAuth login data */
export interface MicrosoftLoginData {
  /** Authorization code from Microsoft */
  code: string;
  /** Redirect URI used for the OAuth flow */
  redirectUri: string;
  /** PKCE code verifier */
  codeVerifier: string;
}

// ===========================================================================
// Event Types
// ===========================================================================

/** Backend-to-frontend event names */
export const BACKEND_EVENTS = {
  /** Game launch progress update */
  LAUNCH_PROGRESS: "launch:progress",
  /** Game output log line */
  GAME_OUTPUT: "game:output",
  /** Game process exited */
  GAME_EXIT: "game:exit",
  /** Download progress update */
  DOWNLOAD_PROGRESS: "download:progress",
  /** Download completed */
  DOWNLOAD_COMPLETE: "download:complete",
  /** Download error */
  DOWNLOAD_ERROR: "download:error",
  /** Version list updated */
  VERSION_UPDATE: "version:update",
  /** Account login status changed */
  ACCOUNT_CHANGE: "account:change",
  /** Plugin installed / updated */
  PLUGIN_CHANGE: "plugin:change",
  /** Launcher update available */
  UPDATE_AVAILABLE: "update:available",
  /** Task queue updated */
  TASK_UPDATE: "task:update",
  /** Java runtime detection complete */
  JAVA_DETECTED: "java:detected",
  /** Error notification */
  ERROR: "error",
  /** Warning notification */
  WARNING: "warning",
} as const;

export type BackendEvent = (typeof BACKEND_EVENTS)[keyof typeof BACKEND_EVENTS];

/** Payload for the launch progress event */
export interface LaunchProgressPayload {
  stage: LaunchStage;
  progress: number;
  message: string;
}

/** Payload for the game output event */
export interface GameOutputPayload {
  line: string;
  level: "info" | "warn" | "error" | "debug";
  timestamp: number;
}

/** Payload for the download progress event */
export interface DownloadProgressPayload {
  taskId: string;
  fileName: string;
  downloaded: number;
  total: number;
  speed: number; // bytes per second
}

/** Payload for the error event */
export interface ErrorPayload {
  message: string;
  code?: string;
  stack?: string;
  recoverable: boolean;
}

// ===========================================================================
// Plugin Types
// ===========================================================================

/** Plugin information from the repository or local scan */
export interface PluginInfo {
  /** Unique plugin ID */
  id: string;
  /** Display name */
  name: string;
  /** Short description */
  description: string;
  /** Plugin author */
  author: string;
  /** Current version string */
  version: string;
  /** Plugin icon URL */
  iconUrl?: string;
  /** Plugin category */
  category: string;
  /** Required launcher version */
  minLauncherVersion?: string;
  /** Whether this plugin is installed */
  isInstalled: boolean;
  /** Whether an update is available */
  hasUpdate: boolean;
  /** Download count */
  downloads: number;
  /** Rating (0-5) */
  rating: number;
  /** Plugin tags */
  tags: string[];
  /** Last updated timestamp */
  updatedAt: number;
  /** Installation size in bytes */
  size?: number;
}

/** Plugin manifest file structure */
export interface PluginManifest {
  /** Plugin ID */
  id: string;
  /** Display name */
  name: string;
  /** Version */
  version: string;
  /** Author */
  author: string;
  /** Description */
  description: string;
  /** Entry point script */
  main: string;
  /** Minimum launcher version */
  minLauncherVersion?: string;
  /** Plugin dependencies */
  dependencies?: Record<string, string>;
  /** Plugin permissions */
  permissions?: string[];
  /** Plugin icon path */
  icon?: string;
}

// ===========================================================================
// Task Queue Types
// ===========================================================================

/** Task status */
export type TaskStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

/** Task type */
export type TaskType =
  | "download"
  | "install"
  | "extract"
  | "verify"
  | "launch"
  | "plugin_install"
  | "plugin_update"
  | "plugin_remove"
  | "version_install"
  | "version_delete";

/** A single task in the queue */
export interface TaskInfo {
  /** Unique task ID */
  id: string;
  /** Task type */
  type: TaskType;
  /** Display name */
  name: string;
  /** Current status */
  status: TaskStatus;
  /** Progress percentage (0-100) */
  progress: number;
  /** Status message */
  message?: string;
  /** Error message (if failed) */
  error?: string;
  /** Creation timestamp */
  createdAt: number;
  /** Started timestamp */
  startedAt?: number;
  /** Completed timestamp */
  completedAt?: number;
  /** Whether this task can be cancelled */
  cancellable: boolean;
  /** Parent task ID (for subtasks) */
  parentId?: string;
  /** Subtask IDs */
  subtaskIds?: string[];
}

// ===========================================================================
// Utility types
// ===========================================================================

/** Recursively make all properties partial */
export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

/** Extract the payload type for a given event */
export type EventPayload<T extends BackendEvent> = T extends "launch:progress"
  ? LaunchProgressPayload
  : T extends "game:output"
    ? GameOutputPayload
    : T extends "download:progress"
      ? DownloadProgressPayload
      : T extends "error"
        ? ErrorPayload
        : unknown;