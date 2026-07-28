/**
 * Main Application Store
 *
 * Zustand store managing global application state:
 * sidebar, routing, theme, loading, and task queue.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ThemeColor, ThemeMode } from "@/config/theme";
import { DEFAULT_THEME_COLOR, DEFAULT_THEME_MODE } from "@/config/theme";
import type { TaskInfo } from "@/types/api";

// ===========================================================================
// State Interface
// ===========================================================================

export interface AppState {
  // ---- Sidebar ----
  /** Whether the sidebar is collapsed */
  sidebarCollapsed: boolean;
  /** Whether the sidebar is being hovered (for expand-on-hover) */
  sidebarHovered: boolean;

  // ---- Route ----
  /** Current active route path */
  currentRoute: string;
  /** Previous route path (for transition direction) */
  previousRoute: string;

  // ---- Theme ----
  /** Current theme mode */
  themeMode: ThemeMode;
  /** Current theme color preset */
  themeColor: ThemeColor;
  /** Whether glass morphism effects are enabled */
  glassEffect: boolean;
  /** Whether reduced motion is active */
  reducedMotion: boolean;

  // ---- Loading ----
  /** Whether the app is in a global loading state */
  isGlobalLoading: boolean;
  /** Global loading message */
  globalLoadingMessage: string;

  // ---- Task Queue ----
  /** Active task queue items */
  tasks: TaskInfo[];
  /** Whether the task panel is visible */
  taskPanelOpen: boolean;

  // ---- Window ----
  /** Whether the app window is maximized */
  isMaximized: boolean;
  /** Whether the app window is focused */
  isFocused: boolean;

  // ---- Actions ----
  /** Toggle sidebar collapsed state */
  toggleSidebar: () => void;
  /** Set sidebar collapsed state explicitly */
  setSidebarCollapsed: (collapsed: boolean) => void;
  /** Set sidebar hover state */
  setSidebarHovered: (hovered: boolean) => void;
  /** Navigate to a route */
  navigateTo: (route: string) => void;
  /** Set theme mode */
  setThemeMode: (mode: ThemeMode) => void;
  /** Cycle to the next theme mode */
  cycleThemeMode: () => void;
  /** Set theme color preset */
  setThemeColor: (color: ThemeColor) => void;
  /** Toggle glass effect */
  toggleGlassEffect: () => void;
  /** Toggle reduced motion */
  toggleReducedMotion: () => void;
  /** Set global loading state */
  setGlobalLoading: (loading: boolean, message?: string) => void;
  /** Add a task to the queue */
  addTask: (task: TaskInfo) => void;
  /** Update a task in the queue */
  updateTask: (id: string, updates: Partial<TaskInfo>) => void;
  /** Remove a task from the queue */
  removeTask: (id: string) => void;
  /** Clear all completed/failed/cancelled tasks */
  clearFinishedTasks: () => void;
  /** Toggle the task panel */
  toggleTaskPanel: () => void;
  /** Set task panel visibility */
  setTaskPanelOpen: (open: boolean) => void;
  /** Set window maximized state */
  setIsMaximized: (maximized: boolean) => void;
  /** Set window focus state */
  setIsFocused: (focused: boolean) => void;
}

// ===========================================================================
// Route Definitions
// ===========================================================================

export const ROUTES = {
  GAME: "/",
  VERSIONS: "/versions",
  PLUGINS: "/plugins",
  ONLINE_MODS: "/online-mods",
  SETTINGS: "/settings",
} as const;

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];

// ===========================================================================
// Theme Mode Cycle Order
// ===========================================================================

const THEME_MODE_CYCLE: ThemeMode[] = ["system", "dark", "light"];

// ===========================================================================
// Store
// ===========================================================================

export const useAppStore = create<AppState>()(
  persist(
    (set, _get) => ({
      // ---- Initial State ----
      sidebarCollapsed: false,
      sidebarHovered: false,
      currentRoute: ROUTES.GAME,
      previousRoute: ROUTES.GAME,
      themeMode: DEFAULT_THEME_MODE,
      themeColor: DEFAULT_THEME_COLOR,
      glassEffect: true,
      reducedMotion: false,
      isGlobalLoading: false,
      globalLoadingMessage: "",
      tasks: [],
      taskPanelOpen: false,
      isMaximized: false,
      isFocused: true,

      // ---- Sidebar Actions ----
      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      setSidebarCollapsed: (collapsed: boolean) =>
        set({ sidebarCollapsed: collapsed }),

      setSidebarHovered: (hovered: boolean) =>
        set({ sidebarHovered: hovered }),

      // ---- Route Actions ----
      navigateTo: (route: string) =>
        set((state) => ({
          previousRoute: state.currentRoute,
          currentRoute: route,
        })),

      // ---- Theme Actions ----
      setThemeMode: (mode: ThemeMode) => set({ themeMode: mode }),

      cycleThemeMode: () =>
        set((state) => {
          const currentIndex = THEME_MODE_CYCLE.indexOf(state.themeMode);
          const nextIndex = (currentIndex + 1) % THEME_MODE_CYCLE.length;
          return { themeMode: THEME_MODE_CYCLE[nextIndex] };
        }),

      setThemeColor: (color: ThemeColor) => set({ themeColor: color }),

      toggleGlassEffect: () =>
        set((state) => ({ glassEffect: !state.glassEffect })),

      toggleReducedMotion: () =>
        set((state) => ({ reducedMotion: !state.reducedMotion })),

      // ---- Loading Actions ----
      setGlobalLoading: (loading: boolean, message?: string) =>
        set({
          isGlobalLoading: loading,
          globalLoadingMessage: message ?? "",
        }),

      // ---- Task Queue Actions ----
      addTask: (task: TaskInfo) =>
        set((state) => ({
          tasks: [...state.tasks, task],
        })),

      updateTask: (id: string, updates: Partial<TaskInfo>) =>
        set((state) => ({
          tasks: state.tasks.map((task) =>
            task.id === id ? { ...task, ...updates } : task
          ),
        })),

      removeTask: (id: string) =>
        set((state) => ({
          tasks: state.tasks.filter((task) => task.id !== id),
        })),

      clearFinishedTasks: () =>
        set((state) => ({
          tasks: state.tasks.filter(
            (task) =>
              task.status === "pending" || task.status === "running"
          ),
        })),

      toggleTaskPanel: () =>
        set((state) => ({ taskPanelOpen: !state.taskPanelOpen })),

      setTaskPanelOpen: (open: boolean) => set({ taskPanelOpen: open }),

      // ---- Window Actions ----
      setIsMaximized: (maximized: boolean) => set({ isMaximized: maximized }),

      setIsFocused: (focused: boolean) => set({ isFocused: focused }),
    }),
    {
      name: "euoracraft-app-store",
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        themeMode: state.themeMode,
        themeColor: state.themeColor,
        glassEffect: state.glassEffect,
        reducedMotion: state.reducedMotion,
      }),
    }
  )
);

// ===========================================================================
// Selectors
// ===========================================================================

/** Select only sidebar state */
export const selectSidebar = (state: AppState) => ({
  collapsed: state.sidebarCollapsed,
  hovered: state.sidebarHovered,
  toggle: state.toggleSidebar,
  setCollapsed: state.setSidebarCollapsed,
  setHovered: state.setSidebarHovered,
});

/** Select only theme state */
export const selectTheme = (state: AppState) => ({
  mode: state.themeMode,
  color: state.themeColor,
  glassEffect: state.glassEffect,
  reducedMotion: state.reducedMotion,
  setMode: state.setThemeMode,
  cycleMode: state.cycleThemeMode,
  setColor: state.setThemeColor,
  toggleGlass: state.toggleGlassEffect,
  toggleReducedMotion: state.toggleReducedMotion,
});

/** Select only task queue state */
export const selectTasks = (state: AppState) => ({
  tasks: state.tasks,
  panelOpen: state.taskPanelOpen,
  addTask: state.addTask,
  updateTask: state.updateTask,
  removeTask: state.removeTask,
  clearFinished: state.clearFinishedTasks,
  togglePanel: state.toggleTaskPanel,
  setPanelOpen: state.setTaskPanelOpen,
});

/** Select only window state */
export const selectWindow = (state: AppState) => ({
  isMaximized: state.isMaximized,
  isFocused: state.isFocused,
  setIsMaximized: state.setIsMaximized,
  setIsFocused: state.setIsFocused,
});