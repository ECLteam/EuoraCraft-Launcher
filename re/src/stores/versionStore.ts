/**
 * Version Store
 *
 * Zustand store managing Minecraft version state:
 * - Installed versions and available versions
 * - Version installation and deletion
 * - Launch progress tracking
 *
 * Uses the transport layer for backend communication and
 * provides mock data when running in showcase mode.
 */

import { create } from "zustand";
import { transport } from "@/api/transport";
import { isShowcaseMode } from "@/api/transport";
import type { MinecraftVersion, ScannedVersion, GameInstance } from "@/types/api";
import type { LaunchStage } from "@/config/game";

// ===========================================================================
// Types
// ===========================================================================

/** Launch progress state */
export interface LaunchProgress {
  /** Current launch stage */
  stage: LaunchStage;
  /** Progress percentage (0-100) */
  progress: number;
  /** Human-readable status message */
  message: string;
  /** Whether the game is currently running */
  isRunning: boolean;
  /** Game process ID (if available) */
  pid?: number;
}

/** Version store state */
export interface VersionState {
  // ---- Data ----
  /** Installed/scanned versions on the local machine */
  installedVersions: ScannedVersion[];
  /** Available versions from the Minecraft manifest */
  availableVersions: MinecraftVersion[];
  /** Game instances configured by the user */
  instances: GameInstance[];
  /** Currently selected version */
  selectedVersion: MinecraftVersion | ScannedVersion | null;
  /** Whether versions are being loaded */
  loading: boolean;
  /** Error message if loading failed */
  error: string | null;
  /** Launch progress tracking */
  launchProgress: LaunchProgress;
  /** Whether the initial fetch has completed */
  isLoaded: boolean;

  // ---- Actions ----
  /** Fetch installed versions from the local machine */
  fetchInstalledVersions: () => Promise<void>;
  /** Fetch available versions from the Minecraft manifest */
  fetchAvailableVersions: () => Promise<void>;
  /** Fetch game instances */
  fetchInstances: () => Promise<void>;
  /** Install a Minecraft version by ID */
  installVersion: (versionId: string) => Promise<void>;
  /** Delete an installed version by ID */
  deleteVersion: (versionId: string) => Promise<void>;
  /** Select a version by ID */
  selectVersion: (versionId: string) => void;
  /** Update launch progress */
  updateLaunchProgress: (progress: Partial<LaunchProgress>) => void;
  /** Reset launch progress to idle */
  resetLaunchProgress: () => void;
  /** Clear any error state */
  clearError: () => void;
}

// ===========================================================================
// Default Launch Progress
// ===========================================================================

function createDefaultLaunchProgress(): LaunchProgress {
  return {
    stage: "checking_java",
    progress: 0,
    message: "",
    isRunning: false,
  };
}

// ===========================================================================
// Mock Data
// ===========================================================================

const mockAvailableVersions: MinecraftVersion[] = [
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
    sha1: "snapshot-hash-24w44a",
    compliance: true,
  },
  {
    id: "1.19.4",
    type: "release",
    releaseTime: "2023-03-14T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.19.4.json",
    sha1: "version-hash-1.19.4",
    compliance: true,
  },
  {
    id: "1.18.2",
    type: "release",
    releaseTime: "2022-02-28T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.18.2.json",
    sha1: "version-hash-1.18.2",
    compliance: true,
  },
  {
    id: "1.16.5",
    type: "release",
    releaseTime: "2021-01-15T00:00:00+00:00",
    url: "https://piston-meta.mojang.com/v1/packages/example/1.16.5.json",
    sha1: "version-hash-1.16.5",
    compliance: true,
  },
];

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

const mockInstances: GameInstance[] = [
  {
    id: "instance-1",
    name: "EuoraCraft Survival",
    version: mockAvailableVersions[0],
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
    version: mockAvailableVersions[3],
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

// ===========================================================================
// Store
// ===========================================================================

export const useVersionStore = create<VersionState>()((set, _get) => ({
  // ---- Initial State ----
  installedVersions: [],
  availableVersions: [],
  instances: [],
  selectedVersion: null,
  loading: false,
  error: null,
  launchProgress: createDefaultLaunchProgress(),
  isLoaded: false,

  // ---- Actions ----

  fetchInstalledVersions: async () => {
    set({ loading: true, error: null });

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 300));
        set({
          installedVersions: mockInstalledVersions,
          loading: false,
          isLoaded: true,
        });
        return;
      }

      const response = await transport.invoke<ScannedVersion[]>(
        "get_installed_versions",
      );

      if (response.success && response.data) {
        set({
          installedVersions: response.data,
          loading: false,
          isLoaded: true,
        });
      } else {
        set({
          error: response.error ?? "Failed to fetch installed versions",
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

  fetchAvailableVersions: async () => {
    set({ loading: true, error: null });

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 500));
        set({
          availableVersions: mockAvailableVersions,
          loading: false,
          isLoaded: true,
        });
        return;
      }

      const response = await transport.invoke<MinecraftVersion[]>("get_versions");

      if (response.success && response.data) {
        set({
          availableVersions: response.data,
          loading: false,
          isLoaded: true,
        });
      } else {
        set({
          error: response.error ?? "Failed to fetch available versions",
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

  fetchInstances: async () => {
    set({ loading: true, error: null });

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 300));
        set({
          instances: mockInstances,
          loading: false,
        });
        return;
      }

      const response = await transport.invoke<GameInstance[]>("get_instances");

      if (response.success && response.data) {
        set({
          instances: response.data,
          loading: false,
        });
      } else {
        set({
          error: response.error ?? "Failed to fetch instances",
          loading: false,
        });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        error: message,
        loading: false,
      });
    }
  },

  installVersion: async (versionId: string) => {
    set({ error: null });

    try {
      if (isShowcaseMode()) {
        // Simulate installation progress
        set({
          launchProgress: {
            stage: "downloading_assets",
            progress: 0,
            message: `Preparing to install ${versionId}...`,
            isRunning: false,
          },
        });

        await new Promise((r) => setTimeout(r, 800));

        set({
          launchProgress: {
            stage: "downloading_libraries",
            progress: 30,
            message: "Downloading libraries...",
            isRunning: false,
          },
        });

        await new Promise((r) => setTimeout(r, 1000));

        set({
          launchProgress: {
            stage: "verifying_files",
            progress: 70,
            message: "Verifying files...",
            isRunning: false,
          },
        });

        await new Promise((r) => setTimeout(r, 600));

        set({
          launchProgress: {
            stage: "running",
            progress: 100,
            message: `Version ${versionId} installed successfully`,
            isRunning: false,
          },
        });

        // Add to installed versions
        const version = mockAvailableVersions.find((v) => v.id === versionId);
        if (version) {
          set((state) => ({
            installedVersions: [
              ...state.installedVersions,
              {
                id: version.id,
                type: version.type,
                path: `.minecraft/versions/${version.id}`,
                loaders: [],
                isModified: false,
                lastPlayed: Date.now(),
                playTime: 0,
              },
            ],
          }));
        }

        // Reset progress after a delay
        setTimeout(() => {
          set({ launchProgress: createDefaultLaunchProgress() });
        }, 2000);

        return;
      }

      const response = await transport.invoke<{ taskId: string }>(
        "install_version",
        { versionId },
      );

      if (!response.success) {
        set({
          error: response.error ?? `Failed to install version ${versionId}`,
        });
      }
      // The backend will emit progress events via the event system
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set({ error: message });
    }
  },

  deleteVersion: async (versionId: string) => {
    set({ loading: true, error: null });

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 400));
        set((state) => ({
          installedVersions: state.installedVersions.filter(
            (v) => v.id !== versionId,
          ),
          selectedVersion:
            state.selectedVersion &&
            "id" in state.selectedVersion &&
            state.selectedVersion.id === versionId
              ? null
              : state.selectedVersion,
          loading: false,
        }));
        return;
      }

      const response = await transport.invoke<{ ok: boolean }>(
        "delete_version",
        { versionId },
      );

      if (response.success) {
        set((state) => ({
          installedVersions: state.installedVersions.filter(
            (v) => v.id !== versionId,
          ),
          selectedVersion:
            state.selectedVersion &&
            "id" in state.selectedVersion &&
            state.selectedVersion.id === versionId
              ? null
              : state.selectedVersion,
          loading: false,
        }));
      } else {
        set({
          error: response.error ?? `Failed to delete version ${versionId}`,
          loading: false,
        });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set({ error: message, loading: false });
    }
  },

  selectVersion: (versionId: string) => {
    set((state) => {
      const installed = state.installedVersions.find((v) => v.id === versionId);
      if (installed) {
        return { selectedVersion: installed };
      }
      const available = state.availableVersions.find((v) => v.id === versionId);
      if (available) {
        return { selectedVersion: available };
      }
      return state;
    });
  },

  updateLaunchProgress: (progress: Partial<LaunchProgress>) => {
    set((state) => ({
      launchProgress: { ...state.launchProgress, ...progress },
    }));
  },

  resetLaunchProgress: () => {
    set({ launchProgress: createDefaultLaunchProgress() });
  },

  clearError: () => {
    set({ error: null });
  },
}));

// ===========================================================================
// Selectors
// ===========================================================================

/** Select all installed versions */
export const selectInstalledVersions = (state: VersionState) =>
  state.installedVersions;

/** Select all available versions */
export const selectAvailableVersions = (state: VersionState) =>
  state.availableVersions;

/** Select all game instances */
export const selectInstances = (state: VersionState) => state.instances;

/** Select the currently selected version */
export const selectSelectedVersion = (state: VersionState) =>
  state.selectedVersion;

/** Select launch progress */
export const selectLaunchProgress = (state: VersionState) =>
  state.launchProgress;

/** Select version loading state */
export const selectVersionLoading = (state: VersionState) => ({
  loading: state.loading,
  error: state.error,
  isLoaded: state.isLoaded,
});

/** Check if a specific version is installed */
export const selectIsVersionInstalled = (versionId: string) => (state: VersionState) =>
  state.installedVersions.some((v) => v.id === versionId);

export default useVersionStore;