/**
 * AppLayout Component
 *
 * Main application layout shell composing:
 * - TitleBar (top, 2.5rem)
 * - SideBar (left, collapsible 16rem/4rem)
 * - Main content area with blocky page transitions (Outlet)
 *
 * Minecraft Block Brutalist design system:
 * - bg-deepslate backgrounds, no glass, no backdrop-blur
 * - Sharp corners (rounded-[2px] max), border-2
 * - Snappy cubic-bezier(0.8, 0, 0.2, 1) transitions
 * - Block shadows: 3px 3px 0px rgba(0,0,0,0.3)
 */

import { Suspense, useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/stores/appStore";
import { TitleBar } from "@/components/layout/TitleBar";
import { SideBar } from "@/components/layout/SideBar";
import { TaskPanel } from "@/components/layout/TaskPanel";
import { initializeTheme } from "@/hooks/useTheme";
import { isShowcaseMode } from "@/api/transport";
import { mockTasks } from "@/api/transport/showcase";

// ---------------------------------------------------------------------------
// Minimum Window Size (for Tauri)
// ---------------------------------------------------------------------------

const MIN_WINDOW_WIDTH = 900;
const MIN_WINDOW_HEIGHT = 600;

// ---------------------------------------------------------------------------
// Blocky Page Transition Variants
// NO scale. NO spring. Snappy block-place feel.
// ---------------------------------------------------------------------------

const pageVariants = {
  initial: {
    opacity: 0,
    x: 16,
    scale: 0.97,
  },
  animate: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: {
      duration: 0.3,
      ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
    },
  },
  exit: {
    opacity: 0,
    x: -16,
    scale: 0.97,
    transition: {
      duration: 0.2,
      ease: [0.4, 0, 1, 1] as [number, number, number, number],
    },
  },
};

// ---------------------------------------------------------------------------
// Square Pixelated Spinner
// NO rounded-full. Square block with border-2, top border grass.
// Uses steps(8) animation for pixelated Minecraft feel.
// ---------------------------------------------------------------------------

function RouteLoadingFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-bg-deepslate">
      <div className="flex flex-col items-center gap-4">
        <div
          className="h-8 w-8 border-2 border-stone animate-block-spin"
          style={{ borderTopColor: "#5B8731" }}
        />
        <span className="font-mono text-xs text-text-tertiary tracking-wider uppercase">
          Loading...
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AppLayout Component
// ---------------------------------------------------------------------------

export function AppLayout() {
  const location = useLocation();
  const { navigateTo, addTask, tasks } = useAppStore();

  // Initialize theme on mount
  useEffect(() => {
    initializeTheme();
  }, []);

  // Update the current route in the store whenever location changes
  useEffect(() => {
    navigateTo(location.pathname);
  }, [location.pathname, navigateTo]);

  // Load demo tasks in showcase mode
  useEffect(() => {
    if (isShowcaseMode() && tasks.length === 0) {
      mockTasks.forEach((task) => addTask(task));
    }
  }, [addTask, tasks.length]);

  return (
    <div
      className="flex h-screen w-screen flex-col overflow-hidden bg-bg-deepslate text-text-primary"
      style={{
        minWidth: MIN_WINDOW_WIDTH,
        minHeight: MIN_WINDOW_HEIGHT,
      }}
    >
      {/* ---- Title Bar ---- */}
      <TitleBar />

      {/* ---- Body: Sidebar + Content ---- */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <SideBar />

        {/* Main Content Area */}
        <main className="flex-1 overflow-hidden bg-bg-deepslate">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              className="h-full w-full overflow-auto"
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
            >
              <Suspense fallback={<RouteLoadingFallback />}>
                <Outlet />
              </Suspense>
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Task Panel (slide-in from right) */}
      <TaskPanel />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Re-export for convenience
// ---------------------------------------------------------------------------

export { TitleBar, SideBar };