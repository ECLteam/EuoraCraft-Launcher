/**
 * GameLaunchBar Component
 *
 * Minecraft Block Brutalist launch bar.
 * Block shadows, font-mono, sharp corners, snappy transitions.
 * NO glass, NO blur, NO scale, NO rounded corners.
 */

import { motion } from "framer-motion";
import {
  Play,
  Settings,
  Loader2,
  Box,
  AlertCircle,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface VersionOption {
  id: string;
  label: string;
  type?: "release" | "snapshot" | "old_beta" | "old_alpha";
}

interface GameLaunchBarProps {
  versions?: VersionOption[];
  selectedVersionId?: string;
  onVersionSelect?: (versionId: string) => void;
  onSettingsClick?: () => void;
  onLaunch?: () => void;
  isLaunching?: boolean;
  disabled?: boolean;
  className?: string;
}

// ---------------------------------------------------------------------------
// Default Versions
// ---------------------------------------------------------------------------

const DEFAULT_VERSIONS: VersionOption[] = [
  { id: "1.21", label: "Minecraft 1.21", type: "release" },
  { id: "1.20.6", label: "Minecraft 1.20.6", type: "release" },
  { id: "1.20.4", label: "Minecraft 1.20.4", type: "release" },
  { id: "1.19.4", label: "Minecraft 1.19.4", type: "release" },
  { id: "1.18.2", label: "Minecraft 1.18.2", type: "release" },
  { id: "1.16.5", label: "Minecraft 1.16.5", type: "release" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function GameLaunchBar({
  versions = DEFAULT_VERSIONS,
  selectedVersionId,
  onVersionSelect,
  onSettingsClick,
  onLaunch,
  isLaunching = false,
  disabled = false,
  className,
}: GameLaunchBarProps) {
  const hasVersionSelected = !!selectedVersionId;
  const isDisabled = disabled || !hasVersionSelected;

  const snappyEase: [number, number, number, number] = [0.8, 0, 0.2, 1];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, ease: snappyEase, delay: 0.15 }}
    >
      <div
        className={cn(
          "border-2 border-[#7F7F7F26] bg-[#1A1A1A]",
          "shadow-[4px_4px_0px_rgba(0,0,0,0.3)]",
          className
        )}
      >
        <div className="p-4 space-y-3">
          {/* ---- Version Selector ---- */}
          <div className="flex items-center gap-2">
            <Select
              value={selectedVersionId}
              onValueChange={onVersionSelect}
            >
              <SelectTrigger
                className={cn(
                  "flex-1 h-9 font-mono text-xs",
                  "border-2 border-[#7F7F7F26] bg-[#1E1E1E] text-[#E8E8E8]",
                  "transition-[border-color,box-shadow] duration-[150ms]",
                  "hover:border-[#7F7F7F40]",
                  "focus:border-[#5B8731]",
                  "data-[state=open]:border-[#5B8731]"
                )}
              >
                <div className="flex items-center gap-2">
                  <Box className="size-3.5 text-[#555555] shrink-0" />
                  <SelectValue placeholder="Select a version..." />
                </div>
              </SelectTrigger>
              <SelectContent className="border-2 border-[#7F7F7F26] bg-[#1E1E1E] font-mono">
                {versions.map((v) => (
                  <SelectItem
                    key={v.id}
                    value={v.id}
                    className="text-xs text-[#E8E8E8] focus:bg-[#5B8731] focus:text-[#E8E8E8]"
                  >
                    {v.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Settings Button */}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className={cn(
                    "flex size-9 shrink-0 items-center justify-center",
                    "border-2 border-transparent bg-transparent",
                    "text-[#555555] hover:text-[#E8E8E8]",
                    "transition-[color,transform,box-shadow] duration-[150ms]",
                    "hover:translate-y-[-1px]",
                    "active:translate-y-0 active:shadow-[inset_2px_2px_0px_rgba(0,0,0,0.3)]"
                  )}
                  onClick={onSettingsClick}
                >
                  <Settings className="size-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent
                side="left"
                className="border-2 border-[#7F7F7F26] bg-[#1A1A1A] font-mono text-xs text-[#E8E8E8] shadow-[3px_3px_0px_rgba(0,0,0,0.3)]"
              >
                Version Settings
              </TooltipContent>
            </Tooltip>
          </div>

          {/* ---- Launch Button ---- */}
          <button
            type="button"
            disabled={isDisabled}
            onClick={onLaunch}
            className={cn(
              "w-full h-12 font-mono text-lg tracking-[0.15em] uppercase",
              "border-2 transition-[transform,box-shadow,background-color] duration-[150ms]",
              isDisabled
                ? "border-[#7F7F7F26] bg-[#1E1E1E] text-[#555555] cursor-not-allowed"
                : "border-[#5B8731] bg-[#5B8731] text-[#E8E8E8]",
              !isDisabled && "shadow-[4px_4px_0px_rgba(0,0,0,0.3)]",
              !isDisabled && "hover:translate-y-[-1px] hover:shadow-[6px_6px_0px_rgba(0,0,0,0.3)]",
              !isDisabled && "active:translate-y-0 active:shadow-[inset_2px_2px_0px_rgba(0,0,0,0.3)]",
              !isDisabled && isLaunching && "bg-[#5B8731CC] border-[#5B8731CC]"
            )}
          >
            {isLaunching ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2 className="size-4 animate-spin" />
                LAUNCHING...
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                <Play className="size-4" />
                LAUNCH
              </span>
            )}
          </button>

          {/* ---- No Version Warning ---- */}
          {!hasVersionSelected && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="flex items-center gap-1.5 font-mono text-[10px] text-[#FFAA00]"
            >
              <AlertCircle className="size-3" />
              Please select a version to launch
            </motion.div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default GameLaunchBar;