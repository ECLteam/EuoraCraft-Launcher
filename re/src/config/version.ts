/**
 * Version Configuration
 *
 * Version-related constants for the Minecraft Launcher:
 * version type metadata, loader metadata, download sources, and icon mappings.
 */

// ---------------------------------------------------------------------------
// Version Type Metadata
// ---------------------------------------------------------------------------
export const VERSION_TYPES = {
  release: {
    label: "正式版",
    color: "text-success",
    bgColor: "bg-success/10",
    borderColor: "border-success/30",
    sortOrder: 0,
  },
  snapshot: {
    label: "快照版",
    color: "text-warning",
    bgColor: "bg-warning/10",
    borderColor: "border-warning/30",
    sortOrder: 1,
  },
  old_beta: {
    label: "旧版 Beta",
    color: "text-info",
    bgColor: "bg-info/10",
    borderColor: "border-info/30",
    sortOrder: 2,
  },
  old_alpha: {
    label: "旧版 Alpha",
    color: "text-text-tertiary",
    bgColor: "bg-text-tertiary/10",
    borderColor: "border-text-tertiary/30",
    sortOrder: 3,
  },
} as const;

export type VersionType = keyof typeof VERSION_TYPES;

// ---------------------------------------------------------------------------
// Loader Metadata
// ---------------------------------------------------------------------------
export const LOADER_TYPES = {
  Vanilla: {
    label: "Vanilla",
    description: "原版 Minecraft，无任何修改",
    icon: "Box",
    color: "#8b8fa6",
    compatibleWith: [],
  },
  Forge: {
    label: "Forge",
    description: "最经典的模组加载器",
    icon: "Hammer",
    color: "#e04d2e",
    compatibleWith: ["OptiFine"],
  },
  NeoForge: {
    label: "NeoForge",
    description: "Forge 的现代化分支",
    icon: "Wrench",
    color: "#f16436",
    compatibleWith: [],
  },
  Fabric: {
    label: "Fabric",
    description: "轻量级模组加载器",
    icon: "Scissors",
    color: "#e8eaf0",
    compatibleWith: ["OptiFine"],
  },
  Quilt: {
    label: "Quilt",
    description: "Fabric 的社区分支",
    icon: "Feather",
    color: "#a040ff",
    compatibleWith: [],
  },
  OptiFine: {
    label: "OptiFine",
    description: "性能优化与光影支持",
    icon: "Sparkles",
    color: "#c7902a",
    compatibleWith: ["Forge", "Fabric"],
  },
  LiteLoader: {
    label: "LiteLoader",
    description: "轻量级模组加载器",
    icon: "Zap",
    color: "#22c55e",
    compatibleWith: [],
  },
} as const;

export type LoaderType = keyof typeof LOADER_TYPES;

// ---------------------------------------------------------------------------
// Download Source Options
// ---------------------------------------------------------------------------
export const DOWNLOAD_SOURCES = {
  mojang: {
    label: "Mojang 官方",
    baseUrl: "https://launchermeta.mojang.com",
    resourcesUrl: "https://resources.download.minecraft.net",
    librariesUrl: "https://libraries.minecraft.net",
    priority: 0,
  },
  bmclapi: {
    label: "BMCLAPI (国内镜像)",
    baseUrl: "https://bmclapi2.bangbang93.com",
    resourcesUrl: "https://bmclapi2.bangbang93.com/assets",
    librariesUrl: "https://bmclapi2.bangbang93.com/maven",
    priority: 1,
  },
  mcbbs: {
    label: "MCBBS 镜像",
    baseUrl: "https://download.mcbbs.net",
    resourcesUrl: "https://download.mcbbs.net/assets",
    librariesUrl: "https://download.mcbbs.net/maven",
    priority: 2,
  },
} as const;

export type DownloadSource = keyof typeof DOWNLOAD_SOURCES;

// ---------------------------------------------------------------------------
// Icon Mappings
// ---------------------------------------------------------------------------
export const VERSION_TYPE_ICONS: Record<VersionType, string> = {
  release: "CheckCircle",
  snapshot: "FlaskConical",
  old_beta: "History",
  old_alpha: "Archive",
};

export const LOADER_ICONS: Record<LoaderType, string> = {
  Vanilla: "Box",
  Forge: "Hammer",
  NeoForge: "Wrench",
  Fabric: "Scissors",
  Quilt: "Feather",
  OptiFine: "Sparkles",
  LiteLoader: "Zap",
};

// ---------------------------------------------------------------------------
// Version Sorting
// ---------------------------------------------------------------------------
export const VERSION_SORT_ORDERS = {
  /** Sort by version number (semantic) */
  SEMANTIC: "semantic",
  /** Sort by release date */
  DATE: "date",
  /** Sort alphabetically */
  ALPHABETICAL: "alpha",
} as const;

export type VersionSortOrder =
  (typeof VERSION_SORT_ORDERS)[keyof typeof VERSION_SORT_ORDERS];