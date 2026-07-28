/**
 * Game Configuration
 *
 * Game-related constants for the Minecraft Launcher:
 * launch stages, memory settings, JVM arguments, window sizes,
 * and timeout/delay values.
 */

// ---------------------------------------------------------------------------
// Launch Stage Names & Progress Percentages
// ---------------------------------------------------------------------------
export const LAUNCH_STAGES = [
  { stage: "checking_java", label: "检测 Java 环境", progress: 5 },
  { stage: "downloading_assets", label: "下载资源文件", progress: 15 },
  { stage: "downloading_libraries", label: "下载依赖库", progress: 30 },
  { stage: "extracting_natives", label: "解压原生库", progress: 45 },
  { stage: "verifying_files", label: "校验文件完整性", progress: 55 },
  { stage: "injecting_plugins", label: "注入插件", progress: 65 },
  { stage: "generating_launch_script", label: "生成启动参数", progress: 75 },
  { stage: "launching", label: "正在启动游戏", progress: 85 },
  { stage: "waiting_window", label: "等待游戏窗口", progress: 95 },
  { stage: "running", label: "游戏运行中", progress: 100 },
] as const;

export type LaunchStage = (typeof LAUNCH_STAGES)[number]["stage"];

// ---------------------------------------------------------------------------
// Default Memory Values (in MB)
// ---------------------------------------------------------------------------
export const MEMORY_CONFIG = {
  /** Minimum allowed memory (MB) */
  MIN: 512,
  /** Maximum allowed memory (MB) */
  MAX: 32768, // 32 GB
  /** Default minimum memory (MB) */
  DEFAULT_MIN: 2048,
  /** Default maximum memory (MB) */
  DEFAULT_MAX: 4096,
  /** Auto-detected memory - 50% of system RAM */
  AUTO_RATIO: 0.5,
  /** Step size for the memory slider (MB) */
  STEP: 256,
} as const;

// ---------------------------------------------------------------------------
// Default JVM Arguments
// ---------------------------------------------------------------------------
export const DEFAULT_JVM_ARGS = [
  "-XX:+UseG1GC",
  "-XX:+ParallelRefProcEnabled",
  "-XX:MaxGCPauseMillis=200",
  "-XX:+UnlockExperimentalVMOptions",
  "-XX:+DisableExplicitGC",
  "-XX:+AlwaysPreTouch",
  "-XX:G1NewSizePercent=30",
  "-XX:G1MaxNewSizePercent=40",
  "-XX:G1HeapRegionSize=8M",
  "-XX:G1ReservePercent=20",
  "-XX:G1HeapWastePercent=5",
  "-XX:G1MixedGCCountTarget=4",
  "-XX:InitiatingHeapOccupancyPercent=15",
  "-XX:G1MixedGCLiveThresholdPercent=90",
  "-XX:G1RSetUpdatingPauseTimePercent=5",
  "-XX:SurvivorRatio=32",
  "-XX:+PerfDisableSharedMem",
  "-XX:MaxTenuringThreshold=1",
  "-Dusing.aikars.flags=https://mcflags.emc.gs",
  "-Daikars.new.flags=true",
] as const;

// ---------------------------------------------------------------------------
// Default Window Size Options
// ---------------------------------------------------------------------------
export const WINDOW_SIZE_OPTIONS = [
  { label: "854x480", width: 854, height: 480 },
  { label: "1024x768", width: 1024, height: 768 },
  { label: "1280x720", width: 1280, height: 720 },
  { label: "1366x768", width: 1366, height: 768 },
  { label: "1600x900", width: 1600, height: 900 },
  { label: "1920x1080", width: 1920, height: 1080 },
  { label: "2560x1440", width: 2560, height: 1440 },
  { label: "全屏", width: 0, height: 0 },
] as const;

export const DEFAULT_WINDOW_SIZE = { width: 1280, height: 720 };

// ---------------------------------------------------------------------------
// Timeout / Delay Values (in milliseconds)
// ---------------------------------------------------------------------------
export const TIMEOUTS = {
  /** Max time to wait for Minecraft process to start */
  GAME_LAUNCH: 120_000,
  /** Max time to wait for a single download task */
  DOWNLOAD_TASK: 300_000,
  /** Max time to wait for version manifest fetch */
  VERSION_MANIFEST: 30_000,
  /** Max time to wait for asset download */
  ASSET_DOWNLOAD: 60_000,
  /** Debounce delay for search inputs */
  SEARCH_DEBOUNCE: 300,
  /** Toast auto-dismiss duration */
  TOAST_DURATION: 4_000,
  /** Tooltip show delay */
  TOOLTIP_DELAY: 400,
} as const;

// ---------------------------------------------------------------------------
// Game Output
// ---------------------------------------------------------------------------
export const GAME_OUTPUT = {
  /** Maximum number of lines to keep in the game output buffer */
  MAX_LINES: 1000,
  /** Interval for checking game process status (ms) */
  PROCESS_CHECK_INTERVAL: 2000,
} as const;