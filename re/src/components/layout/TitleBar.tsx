/**
 * TitleBar Component
 *
 * Custom window title bar for the Tauri desktop app.
 * Minecraft Block Brutalist design:
 * - 2.5rem height, bg-deepslate, border-b-2 border-stone
 * - NO glass, NO backdrop-blur, NO rounded corners
 * - Blocky navigation tabs with CSS border-bottom transitions
 * - Flat window controls (hover:bg-stone, close:hover:bg-lava)
 * - font-mono for all text
 * - data-tauri-drag-region for drag area
 */

import { useCallback, useMemo } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  Minus,
  Square,
  X,
  ListTodo,
  Sun,
  Moon,
  Monitor,
  Gamepad2,
  Boxes,
  Puzzle,
  Globe,
  Settings,
  PanelLeft,
  PanelRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { useAppStore } from "@/stores/appStore";
import { useTheme } from "@/hooks/useTheme";
import { ROUTES } from "@/stores/appStore";

// ---------------------------------------------------------------------------
// Navigation Tab Definitions
// ---------------------------------------------------------------------------

interface NavTab {
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV_TABS: NavTab[] = [
  { path: ROUTES.GAME, label: "GAME", icon: Gamepad2 },
  { path: ROUTES.VERSIONS, label: "VERSIONS", icon: Boxes },
  { path: ROUTES.PLUGINS, label: "PLUGINS", icon: Puzzle },
  { path: ROUTES.ONLINE_MODS, label: "MODS", icon: Globe },
  { path: ROUTES.SETTINGS, label: "SETTINGS", icon: Settings },
];

// ---------------------------------------------------------------------------
// Tauri Window API Helpers
// ---------------------------------------------------------------------------

async function getTauriWindow() {
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    return getCurrentWindow();
  } catch {
    return null;
  }
}

async function minimizeWindow() {
  const win = await getTauriWindow();
  await win?.minimize();
}

async function toggleMaximize() {
  const win = await getTauriWindow();
  if (!win) return;
  const isMax = await win.isMaximized();
  if (isMax) {
    await win.unmaximize();
  } else {
    await win.maximize();
  }
}

async function closeWindow() {
  const win = await getTauriWindow();
  await win?.close();
}

// ---------------------------------------------------------------------------
// Theme Mode Icon
// ---------------------------------------------------------------------------

function ThemeModeIcon({ mode }: { mode: string }) {
  if (mode === "dark") return <Moon className="size-4" />;
  if (mode === "light") return <Sun className="size-4" />;
  return <Monitor className="size-4" />;
}

// ---------------------------------------------------------------------------
// TitleBar Component
// ---------------------------------------------------------------------------

export function TitleBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar, taskPanelOpen, toggleTaskPanel, tasks } =
    useAppStore();
  const { mode, cycleMode } = useTheme();

  const activeTasks = useMemo(
    () => tasks.filter((t) => t.status === "pending" || t.status === "running"),
    [tasks]
  );

  // Handle navigation
  const handleNav = useCallback(
    (path: string) => {
      navigate(path);
    },
    [navigate]
  );

  return (
    <TooltipProvider delayDuration={400}>
      <header
        className="drag flex h-titlebar shrink-0 items-center justify-between bg-bg-deepslate border-b-2 border-border-stone select-none"
        data-tauri-drag-region
      >
        {/* ---- Left: Sidebar Toggle + App Name ---- */}
        <div className="no-drag flex items-center gap-3 pl-3">
          {/* Sidebar toggle */}
          <button
            onClick={toggleSidebar}
            className={cn(
              "flex items-center justify-center size-7",
              "text-text-secondary hover:text-text-primary",
              "hover:bg-bg-elevated",
              "transition-[transform,box-shadow] duration-[150ms]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-grass focus-visible:ring-offset-1 focus-visible:ring-offset-bg-deepslate"
            )}
            aria-label={sidebarCollapsed ? "展开侧栏" : "收起侧栏"}
          >
            {sidebarCollapsed ? (
              <PanelLeft className="size-4" />
            ) : (
              <PanelRight className="size-4" />
            )}
          </button>

          {/* App name */}
          <div className="flex items-center gap-2">
            <Gamepad2 className="size-4 text-grass" />
            <span className="font-mono text-sm font-semibold text-text-primary tracking-wider uppercase">
              EuoraCraft
            </span>
          </div>
        </div>

        {/* ---- Center: Navigation Tabs ---- */}
        <nav className="no-drag hidden md:flex items-center gap-0 absolute left-1/2 -translate-x-1/2">
          {NAV_TABS.map((tab) => {
            const isActive = location.pathname === tab.path;
            const Icon = tab.icon;

            return (
              <button
                key={tab.path}
                onClick={() => handleNav(tab.path)}
                className={cn(
                  "relative flex items-center gap-1.5 px-3 py-1.5",
                  "font-mono text-sm font-medium tracking-wider",
                  "border-2 border-transparent",
                  "transition-[transform,box-shadow,color,background-color,border-color] duration-[150ms]",
                  "hover:translate-y-[-1px]",
                  isActive
                    ? "text-grass border-b-2 border-b-grass"
                    : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
                )}
              >
                <Icon className="size-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>

        {/* ---- Right: Actions + Window Controls ---- */}
        <div className="no-drag flex items-center gap-0 pr-0">
          {/* Task queue button */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={toggleTaskPanel}
                className={cn(
                  "relative flex items-center justify-center size-8",
                  "text-text-secondary hover:text-text-primary",
                  "hover:bg-bg-elevated",
                  "transition-[transform,box-shadow,color,background-color] duration-[150ms]",
                  taskPanelOpen && "text-grass bg-bg-surface",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-grass focus-visible:ring-offset-1 focus-visible:ring-offset-bg-deepslate"
                )}
              >
                <ListTodo className="size-4" />
                {activeTasks.length > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 flex size-4 items-center justify-center bg-lava text-[10px] font-mono font-bold text-white">
                    {activeTasks.length > 9 ? "9+" : activeTasks.length}
                  </span>
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p>任务队列 {activeTasks.length > 0 && `(${activeTasks.length})`}</p>
            </TooltipContent>
          </Tooltip>

          {/* Theme toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={cycleMode}
                className={cn(
                  "flex items-center justify-center size-8",
                  "text-text-secondary hover:text-text-primary",
                  "hover:bg-bg-elevated",
                  "transition-[transform,box-shadow,color,background-color] duration-[150ms]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-grass focus-visible:ring-offset-1 focus-visible:ring-offset-bg-deepslate"
                )}
              >
                <ThemeModeIcon mode={mode} />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p>
                主题模式:{" "}
                {mode === "system" ? "跟随系统" : mode === "dark" ? "深色" : "浅色"}
              </p>
            </TooltipContent>
          </Tooltip>

          {/* Separator */}
          <div className="mx-1 h-4 w-px bg-border-stone" />

          {/* Window controls */}
          <WindowControlButton onClick={minimizeWindow} label="最小化">
            <Minus className="size-3.5" />
          </WindowControlButton>

          <WindowControlButton onClick={toggleMaximize} label="最大化/还原">
            <Square className="size-3" />
          </WindowControlButton>

          <WindowControlButton
            onClick={closeWindow}
            label="关闭"
            className="hover:bg-lava hover:text-white"
          >
            <X className="size-3.5" />
          </WindowControlButton>
        </div>
      </header>
    </TooltipProvider>
  );
}

// ---------------------------------------------------------------------------
// Window Control Button (internal)
// Flat, no rounded corners, no framer-motion scale
// ---------------------------------------------------------------------------

interface WindowControlButtonProps {
  onClick: () => void;
  label: string;
  children: React.ReactNode;
  className?: string;
}

function WindowControlButton({
  onClick,
  label,
  children,
  className,
}: WindowControlButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={onClick}
          className={cn(
            "flex items-center justify-center size-8",
            "text-text-secondary hover:text-text-primary",
            "hover:bg-bg-elevated",
            "transition-[transform,box-shadow,color,background-color] duration-[150ms]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-grass focus-visible:ring-offset-1 focus-visible:ring-offset-bg-deepslate",
            "active:shadow-[inset_2px_2px_0px_rgba(0,0,0,0.3)]",
            className
          )}
          aria-label={label}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <p>{label}</p>
      </TooltipContent>
    </Tooltip>
  );
}