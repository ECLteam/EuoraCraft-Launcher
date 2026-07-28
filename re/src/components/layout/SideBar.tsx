/**
 * SideBar Component
 *
 * Collapsible sidebar navigation with lucide-react icons.
 * Minecraft Block Brutalist design:
 * - Expanded: 16rem, Collapsed: 4rem
 * - bg-deepslate, border-r-2 border-stone
 * - NO glass, NO backdrop-blur
 * - Active indicator: border-l-2 border-grass (left edge), bg-surface
 * - CSS border-color transitions, NO framer-motion layoutId
 * - Snappy width animation via framer-motion (0.2s, ease [0.8,0,0.2,1])
 * - Hover expand when collapsed
 */

import { useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Gamepad2,
  Boxes,
  Puzzle,
  Globe,
  Settings,
  ChevronLeft,
  ChevronRight,
  PackageOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { useAppStore } from "@/stores/appStore";
import { ROUTES } from "@/stores/appStore";

// ---------------------------------------------------------------------------
// Navigation Item Definitions
// ---------------------------------------------------------------------------

interface NavItem {
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  shortcut: string;
}

const NAV_ITEMS: NavItem[] = [
  { path: ROUTES.GAME, label: "GAME", icon: Gamepad2, shortcut: "G" },
  { path: ROUTES.VERSIONS, label: "VERSIONS", icon: Boxes, shortcut: "V" },
  { path: ROUTES.PLUGINS, label: "PLUGINS", icon: Puzzle, shortcut: "P" },
  { path: ROUTES.ONLINE_MODS, label: "MODS", icon: Globe, shortcut: "M" },
  { path: ROUTES.SETTINGS, label: "SETTINGS", icon: Settings, shortcut: "S" },
];

// ---------------------------------------------------------------------------
// SideBar Component
// ---------------------------------------------------------------------------

export function SideBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    sidebarCollapsed,
    sidebarHovered,
    setSidebarCollapsed,
    setSidebarHovered,
  } = useAppStore();

  // The sidebar is effectively expanded when not collapsed, or when hovered in collapsed state
  const isExpanded = !sidebarCollapsed || sidebarHovered;

  // Handle navigation
  const handleNav = useCallback(
    (path: string) => {
      navigate(path);
    },
    [navigate]
  );

  // Toggle collapse
  const handleToggle = useCallback(() => {
    setSidebarCollapsed(!sidebarCollapsed);
  }, [sidebarCollapsed, setSidebarCollapsed]);

  return (
    <TooltipProvider delayDuration={300}>
      <motion.aside
        className={cn(
          "relative flex flex-col shrink-0 h-full overflow-hidden",
          "bg-bg-deepslate",
          "border-r-2 border-border-stone"
        )}
        initial={false}
        animate={{
          width: isExpanded ? "var(--spacing-sidebar)" : "var(--spacing-sidebar-collapsed)",
        }}
        transition={{
          duration: 0.35,
          ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
        }}
        onMouseEnter={() => sidebarCollapsed && setSidebarHovered(true)}
        onMouseLeave={() => sidebarCollapsed && setSidebarHovered(false)}
      >
        {/* ---- Navigation Items ---- */}
        <nav className="flex flex-col gap-1 px-2 pt-3 flex-1">
          {NAV_ITEMS.map((item) => {
            const isActive = location.pathname === item.path;
            const Icon = item.icon;

            return (
              <SidebarNavItem
                key={item.path}
                item={item}
                isActive={isActive}
                isExpanded={isExpanded}
                icon={<Icon className="size-5 shrink-0" />}
                onClick={() => handleNav(item.path)}
              />
            );
          })}
        </nav>

        {/* ---- Plugin Slot Area ---- */}
        <div className="px-2 pb-3">
          <div
            className={cn(
              "flex items-center gap-2 px-2 py-2",
              "border-2 border-dashed border-border-stone",
              "text-text-tertiary",
              isExpanded ? "justify-start" : "justify-center"
            )}
          >
            <PackageOpen className="size-4 shrink-0" />
            <AnimatePresence>
              {isExpanded && (
                <motion.span
                  className="font-mono text-xs whitespace-nowrap overflow-hidden tracking-wider uppercase"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
                >
                  PLUGIN SLOT
                </motion.span>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* ---- Collapse Toggle ---- */}
        <div className="px-2 pb-3">
          <button
            onClick={handleToggle}
            className={cn(
              "flex w-full items-center gap-2 px-2 py-2",
              "font-mono text-xs text-text-tertiary tracking-wider",
              "border-2 border-transparent",
              "hover:text-text-secondary hover:bg-bg-elevated",
              "transition-[transform,box-shadow,color,background-color] duration-[150ms]",
              "hover:translate-y-[-1px]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-grass focus-visible:ring-offset-1 focus-visible:ring-offset-bg-deepslate",
              !isExpanded && "justify-center"
            )}
          >
            <motion.div
              animate={{ rotate: isExpanded ? 0 : 180 }}
              transition={{ duration: 0.2, ease: [0.8, 0, 0.2, 1] }}
            >
              {isExpanded ? (
                <ChevronLeft className="size-4 shrink-0" />
              ) : (
                <ChevronRight className="size-4 shrink-0" />
              )}
            </motion.div>
            <AnimatePresence>
              {isExpanded && (
                <motion.span
                  className="whitespace-nowrap overflow-hidden uppercase"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
                >
                  COLLAPSE
                </motion.span>
              )}
            </AnimatePresence>
          </button>
        </div>
      </motion.aside>
    </TooltipProvider>
  );
}

// ---------------------------------------------------------------------------
// SidebarNavItem (internal)
// NO framer-motion layoutId. CSS border-color transition for active indicator.
// NO whileHover scale. Uses translate-y-[-1px] on hover instead.
// ---------------------------------------------------------------------------

interface SidebarNavItemProps {
  item: NavItem;
  isActive: boolean;
  isExpanded: boolean;
  icon: React.ReactNode;
  onClick: () => void;
}

function SidebarNavItem({
  item,
  isActive,
  isExpanded,
  icon,
  onClick,
}: SidebarNavItemProps) {
  const buttonContent = (
    <button
      onClick={onClick}
      className={cn(
        "relative flex w-full items-center gap-3 px-2 py-2.5",
        "font-mono text-sm font-medium tracking-wider",
        "border-2 border-transparent",
        "transition-[transform,box-shadow,color,background-color,border-color] duration-[150ms]",
        "hover:translate-y-[-1px]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-grass focus-visible:ring-offset-1 focus-visible:ring-offset-bg-deepslate",
        "active:translate-y-0 active:shadow-[inset_2px_2px_0px_rgba(0,0,0,0.3)]",
        isActive
          ? "bg-bg-surface text-grass border-l-2 border-l-grass"
          : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated",
        !isExpanded && "justify-center border-l-0"
      )}
    >
      {/* Icon */}
      {icon}

      {/* Label (shown when expanded) */}
      <AnimatePresence>
        {isExpanded && (
          <motion.span
            className="whitespace-nowrap overflow-hidden uppercase"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
          >
            {item.label}
          </motion.span>
        )}
      </AnimatePresence>

      {/* Shortcut badge */}
      {isExpanded && (
        <span className="ml-auto font-mono text-[10px] text-text-tertiary bg-bg-input border border-border-stone px-1.5 py-0.5">
          {item.shortcut}
        </span>
      )}
    </button>
  );

  // When collapsed, wrap in a tooltip
  if (!isExpanded) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{buttonContent}</TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          <p className="font-mono text-xs tracking-wider uppercase">{item.label}</p>
        </TooltipContent>
      </Tooltip>
    );
  }

  return buttonContent;
}