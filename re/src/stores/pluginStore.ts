/**
 * Plugin Store
 *
 * Zustand store managing plugin state:
 * - Plugin listing, installation, and removal
 * - Enable/disable/reload operations
 * - Status change listeners
 *
 * Uses the transport layer for backend communication and
 * provides mock data when running in showcase mode.
 */

import { create } from "zustand";
import { transport } from "@/api/transport";
import { isShowcaseMode } from "@/api/transport";
import type { PluginInfo } from "@/types/api";

// ===========================================================================
// Types
// ===========================================================================

/** Plugin operation status */
export type PluginOperationStatus =
  | "idle"
  | "installing"
  | "uninstalling"
  | "enabling"
  | "disabling"
  | "reloading";

/** Per-plugin operation state */
export interface PluginOperationState {
  pluginId: string;
  status: PluginOperationStatus;
  error?: string;
}

/** Plugin store state */
export interface PluginState {
  // ---- Data ----
  /** All available plugins */
  plugins: PluginInfo[];
  /** Whether plugins are being loaded */
  loading: boolean;
  /** Error message if loading failed */
  error: string | null;
  /** Current plugin operations in progress */
  operations: PluginOperationState[];
  /** Whether the initial fetch has completed */
  isLoaded: boolean;

  // ---- Actions ----
  /** Fetch all plugins from the backend */
  fetchPlugins: () => Promise<void>;
  /** Enable a plugin by ID */
  enablePlugin: (id: string) => Promise<void>;
  /** Disable a plugin by ID */
  disablePlugin: (id: string) => Promise<void>;
  /** Reload a plugin by ID */
  reloadPlugin: (id: string) => Promise<void>;
  /** Uninstall a plugin by ID */
  uninstallPlugin: (id: string) => Promise<void>;
  /** Install a new plugin by ID */
  installPlugin: (id: string) => Promise<void>;
  /** Refresh plugin data from the backend */
  refreshPlugins: () => Promise<void>;
  /** Clear any error state */
  clearError: () => void;
}

// ===========================================================================
// Mock Data
// ===========================================================================

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

// ===========================================================================
// Helpers
// ===========================================================================

/**
 * Start an operation on a plugin, tracking its status.
 */
function startOperation(
  operations: PluginOperationState[],
  pluginId: string,
  status: PluginOperationStatus,
): PluginOperationState[] {
  // Remove any existing operation for this plugin
  const filtered = operations.filter((op) => op.pluginId !== pluginId);
  return [...filtered, { pluginId, status }];
}

/**
 * Complete an operation on a plugin.
 */
function completeOperation(
  operations: PluginOperationState[],
  pluginId: string,
): PluginOperationState[] {
  return operations.filter((op) => op.pluginId !== pluginId);
}

/**
 * Complete an operation with an error.
 */
function failOperation(
  operations: PluginOperationState[],
  pluginId: string,
  error: string,
): PluginOperationState[] {
  const filtered = operations.filter((op) => op.pluginId !== pluginId);
  return [...filtered, { pluginId, status: "idle" as PluginOperationStatus, error }];
}

// ===========================================================================
// Store
// ===========================================================================

export const usePluginStore = create<PluginState>()((set, get) => ({
  // ---- Initial State ----
  plugins: [],
  loading: false,
  error: null,
  operations: [],
  isLoaded: false,

  // ---- Actions ----

  fetchPlugins: async () => {
    set({ loading: true, error: null });

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 400));
        set({
          plugins: mockPlugins,
          loading: false,
          isLoaded: true,
        });
        return;
      }

      const response = await transport.invoke<PluginInfo[]>("get_plugins");

      if (response.success && response.data) {
        set({
          plugins: response.data,
          loading: false,
          isLoaded: true,
        });
      } else {
        set({
          error: response.error ?? "Failed to fetch plugins",
          loading: false,
          isLoaded: true,
        });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        error: message,
        loading: false,
        isLoaded: true,
      });
    }
  },

  enablePlugin: async (id: string) => {
    set((state) => ({
      operations: startOperation(state.operations, id, "enabling"),
      error: null,
    }));

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 500));
        set((state) => ({
          plugins: state.plugins.map((p) =>
            p.id === id ? { ...p, isInstalled: true } : p,
          ),
          operations: completeOperation(state.operations, id),
        }));
        return;
      }

      const response = await transport.invoke<{ ok: boolean }>("enable_plugin", {
        id,
      });

      if (response.success) {
        set((state) => ({
          plugins: state.plugins.map((p) =>
            p.id === id ? { ...p, isInstalled: true } : p,
          ),
          operations: completeOperation(state.operations, id),
        }));
      } else {
        set((state) => ({
          operations: failOperation(
            state.operations,
            id,
            response.error ?? "Failed to enable plugin",
          ),
        }));
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set((state) => ({
        operations: failOperation(state.operations, id, message),
      }));
    }
  },

  disablePlugin: async (id: string) => {
    set((state) => ({
      operations: startOperation(state.operations, id, "disabling"),
      error: null,
    }));

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 400));
        set((state) => ({
          plugins: state.plugins.map((p) =>
            p.id === id ? { ...p, isInstalled: false } : p,
          ),
          operations: completeOperation(state.operations, id),
        }));
        return;
      }

      const response = await transport.invoke<{ ok: boolean }>("disable_plugin", {
        id,
      });

      if (response.success) {
        set((state) => ({
          plugins: state.plugins.map((p) =>
            p.id === id ? { ...p, isInstalled: false } : p,
          ),
          operations: completeOperation(state.operations, id),
        }));
      } else {
        set((state) => ({
          operations: failOperation(
            state.operations,
            id,
            response.error ?? "Failed to disable plugin",
          ),
        }));
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set((state) => ({
        operations: failOperation(state.operations, id, message),
      }));
    }
  },

  reloadPlugin: async (id: string) => {
    set((state) => ({
      operations: startOperation(state.operations, id, "reloading"),
      error: null,
    }));

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 600));
        set((state) => ({
          operations: completeOperation(state.operations, id),
        }));
        return;
      }

      const response = await transport.invoke<{ ok: boolean }>("reload_plugin", {
        id,
      });

      if (response.success) {
        set((state) => ({
          operations: completeOperation(state.operations, id),
        }));
      } else {
        set((state) => ({
          operations: failOperation(
            state.operations,
            id,
            response.error ?? "Failed to reload plugin",
          ),
        }));
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set((state) => ({
        operations: failOperation(state.operations, id, message),
      }));
    }
  },

  uninstallPlugin: async (id: string) => {
    set((state) => ({
      operations: startOperation(state.operations, id, "uninstalling"),
      error: null,
    }));

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 800));
        set((state) => ({
          plugins: state.plugins.map((p) =>
            p.id === id
              ? { ...p, isInstalled: false, hasUpdate: false }
              : p,
          ),
          operations: completeOperation(state.operations, id),
        }));
        return;
      }

      const response = await transport.invoke<{ ok: boolean }>("uninstall_plugin", {
        id,
      });

      if (response.success) {
        set((state) => ({
          plugins: state.plugins.map((p) =>
            p.id === id
              ? { ...p, isInstalled: false, hasUpdate: false }
              : p,
          ),
          operations: completeOperation(state.operations, id),
        }));
      } else {
        set((state) => ({
          operations: failOperation(
            state.operations,
            id,
            response.error ?? "Failed to uninstall plugin",
          ),
        }));
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set((state) => ({
        operations: failOperation(state.operations, id, message),
      }));
    }
  },

  installPlugin: async (id: string) => {
    set((state) => ({
      operations: startOperation(state.operations, id, "installing"),
      error: null,
    }));

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 1200));
        set((state) => ({
          plugins: state.plugins.map((p) =>
            p.id === id
              ? { ...p, isInstalled: true, hasUpdate: false }
              : p,
          ),
          operations: completeOperation(state.operations, id),
        }));
        return;
      }

      const response = await transport.invoke<{ taskId: string }>("install_plugin", {
        id,
      });

      if (response.success) {
        // The backend will send a plugin:change event when installation completes
        set((state) => ({
          operations: completeOperation(state.operations, id),
        }));
      } else {
        set((state) => ({
          operations: failOperation(
            state.operations,
            id,
            response.error ?? "Failed to install plugin",
          ),
        }));
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set((state) => ({
        operations: failOperation(state.operations, id, message),
      }));
    }
  },

  refreshPlugins: async () => {
    await get().fetchPlugins();
  },

  clearError: () => {
    set({ error: null });
  },
}));

// ===========================================================================
// Selectors
// ===========================================================================

/** Select all plugins */
export const selectPlugins = (state: PluginState) => state.plugins;

/** Select only installed plugins */
export const selectInstalledPlugins = (state: PluginState) =>
  state.plugins.filter((p) => p.isInstalled);

/** Select only plugins with available updates */
export const selectUpdatablePlugins = (state: PluginState) =>
  state.plugins.filter((p) => p.hasUpdate);

/** Select the operation state for a specific plugin */
export const selectPluginOperation = (id: string) => (state: PluginState) =>
  state.operations.find((op) => op.pluginId === id) ?? null;

/** Select plugin loading state */
export const selectPluginLoading = (state: PluginState) => ({
  loading: state.loading,
  error: state.error,
  isLoaded: state.isLoaded,
});

export default usePluginStore;